"""オッズパークからばんえい競馬（帯広）の確定オッズ（単勝・複勝）を収集する。

races テーブルにあるレースを新しい順に巡回し、odds テーブルへ保存する。
取得済みレースはスキップするため、中断しても再実行で続きから取得できる。

確定オッズは払戻金（÷100）との照合で完全一致を検証済み。
"""

import datetime as dt
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from banei.config import ODDS_DB, RACES_DB, REQUEST_INTERVAL
from banei.db.schema import ODDS_SCHEMA, connect, connect_readonly
from banei.net import Fetcher

URL = "https://www.oddspark.com/keiba/Odds.do"
PARAMS_BASE = {"sponsorCd": "04", "opTrackCd": "03"}  # ばんえい帯広

# これだけ連続で失敗したら中断する。相手サイトが 500 を返し続ける状態
# （データセンターの IP からの連続アクセスで発生する）で叩き続けても無意味なため。
MAX_CONSECUTIVE_FAILURES = 20


def parse_float(text: str) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    return float(m.group()) if m else None


def parse_odds_page(html: str) -> list[dict]:
    """単複オッズ表 → [{horse_no, horse_name, win_odds, place_min, place_max}]

    一覧は枠ごとに複数テーブルへ分割されることがあるため、
    該当ヘッダを持つ全テーブルを走査して結合する。
    """
    soup = BeautifulSoup(html, "html.parser")
    out = []
    seen = set()
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header = [re.sub(r"\s", "", c.get_text()) for c in rows[0].find_all(["th", "td"])]
        if "馬番" not in header or not any(h.startswith("単勝") for h in header):
            continue
        col = {}
        for i, name in enumerate(header):
            if name.startswith("単勝"):
                col["単勝"] = i
            elif name.startswith("複勝"):
                col["複勝"] = i
            else:
                col[name] = i
        for tr in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
            if len(cells) == len(header) - 1:
                cells = ["", *cells]  # 同枠2頭目は枠番セルが rowspan で省略される
            if len(cells) < len(header):
                continue
            horse_no = cells[col["馬番"]]
            if not horse_no.isdigit() or int(horse_no) in seen:
                continue
            seen.add(int(horse_no))
            place = cells[col["複勝"]] if "複勝" in col else ""
            pl = [parse_float(p) for p in place.split("-")] if "-" in place else [None, None]
            out.append({
                "horse_no": int(horse_no),
                "horse_name": cells[col.get("馬名", 2)],
                "win_odds": parse_float(cells[col["単勝"]]),
                "place_min": pl[0] if len(pl) > 0 else None,
                "place_max": pl[1] if len(pl) > 1 else None,
            })
    return out


def scrape(
    races_db_path: Path | str = RACES_DB,
    db_path: Path | str = ODDS_DB,
    interval: float = REQUEST_INTERVAL,
    since: str | None = None,
    limit: int | None = None,
    max_consecutive_failures: int = MAX_CONSECUTIVE_FAILURES,
) -> None:
    """未取得レースの単複確定オッズを収集する。

    since / limit で 1 回の実行を区切れる。日次運用では since で直近に絞り、
    過去分のバックフィルは limit で 1 回あたりのリクエスト数を抑える
    （未取得が 2 万件以上あるため、無制限に回すと数時間かかる）。

    連続で失敗したら中断する。相手サイトに拒否されている状態で叩き続けても
    データは取れず、負荷をかけるだけになるため。中断は例外ではなく正常終了に
    するので、呼び出し側（ワークフロー）はそこまでの成果を保存できる。
    """
    db = connect(db_path, ODDS_SCHEMA)

    races_db = connect_readonly(races_db_path)
    if since:
        all_races = races_db.execute(
            "SELECT race_date, race_no FROM races WHERE race_date >= ?"
            " ORDER BY race_date DESC, race_no", (since,)).fetchall()
    else:
        all_races = races_db.execute(
            "SELECT race_date, race_no FROM races ORDER BY race_date DESC, race_no").fetchall()
    races_db.close()
    have = {tuple(r) for r in db.execute("SELECT race_date, race_no FROM odds_meta")}
    targets = [r for r in all_races if tuple(r) not in have]
    if limit is not None:
        targets = targets[:limit]
    print(f"取得対象 {len(targets)} レース")

    fetcher = Fetcher(interval)
    done = 0
    failed = 0
    consecutive = 0
    for race_date, race_no in targets:
        params = dict(PARAMS_BASE, raceDy=race_date.replace("-", ""), raceNb=race_no)
        try:
            html = fetcher.get(URL, params)
        except requests.RequestException as e:
            failed += 1
            consecutive += 1
            print(f"  {race_date} {race_no}R: 取得失敗（スキップ）: {e}", file=sys.stderr)
            # 失敗したレースは odds_meta を書かないので、次回の実行で再度対象になる
            if consecutive >= max_consecutive_failures:
                print(f"連続 {consecutive} 件失敗したため中断する。"
                      "相手サイトが応答していない可能性が高い。", file=sys.stderr)
                break
            continue
        consecutive = 0
        rows = parse_odds_page(html)
        for r in rows:
            db.execute(
                "INSERT OR REPLACE INTO odds VALUES (?,?,?,?,?,?,?)",
                (race_date, race_no, r["horse_no"], r["horse_name"],
                 r["win_odds"], r["place_min"], r["place_max"]),
            )
        db.execute(
            "INSERT OR REPLACE INTO odds_meta VALUES (?,?,?,?)",
            (race_date, race_no, len(rows), dt.datetime.now().isoformat(timespec="seconds")),
        )
        db.commit()
        done += 1
        if done % 100 == 0:
            print(f"{done}/{len(targets)} 完了（現在 {race_date}）", flush=True)
    print(f"完了: 取得 {done} レース / 失敗 {failed} レース")
