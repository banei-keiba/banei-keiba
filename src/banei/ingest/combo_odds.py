"""オッズパークから組み合わせ券種の確定オッズを収集して odds.db に保存する。

券種と betType の対応（払戻金との照合で確認済み）:
  馬連単=5 / 馬連複=6 / ワイド=7(レンジ) / 三連単=8(1着馬ごとに1頁) / 三連複=9

券種名も組番の表記も payouts テーブルに合わせてあるので、そのまま結合できる:
  順序あり（馬連単・三連単）は着順どおり "8-2", "8-2-4"
  順序なし（馬連複・ワイド・三連複）は昇順 "2-8", "2-4-8"

三連単は 1 着馬ごとに 1 リクエスト必要なため重い。期間を絞って実行すること。
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
PARAMS_BASE = {"sponsorCd": "04", "opTrackCd": "03", "viewType": "0"}

# bet_type は payouts テーブル（keiba.go.jp 由来）の呼び方に揃える。
# オッズパークは「馬単 / 馬複」だが keiba.go.jp は「馬連単 / 馬連複」で、
# 揃えないと combo_odds と payouts の結合が黙って空振りする。
TYPES = {
    "umatan":     {"bet_type": "馬連単", "betType": "5", "ordered": True},
    "umaren":     {"bet_type": "馬連複", "betType": "6", "ordered": False},
    "wide":       {"bet_type": "ワイド", "betType": "7", "ordered": False},
    "sanrentan":  {"bet_type": "三連単", "betType": "8", "ordered": True},
    "sanrenpuku": {"bet_type": "三連複", "betType": "9", "ordered": False},
}

DEFAULT_TYPES = "umatan,umaren,wide,sanrenpuku"

# これだけ連続で失敗したら中断する。拒否されている状態で叩き続けても無意味なため。
MAX_CONSECUTIVE_FAILURES = 20


def norm_combo(nums: list[str], ordered: bool) -> str:
    return "-".join(nums if ordered else sorted(nums, key=int))


def _odds_value(text: str) -> float | None:
    """オッズ文字列を数値にする。0 は「票が入らずオッズが付かない」の意味なので NULL。

    パリミュチュエルなので最低でも 1.0 倍。0 は値が無いことの表現であり、
    実際に 2026-07-20 1R の馬連単 7-9 / 9-7 が 0.0 と表示されていた。
    単勝オッズで取消馬が NULL になるのと同じ扱いにする。
    """
    v = float(text)
    return v if v > 0 else None


def parse_matrix(html: str, ordered: bool) -> dict[str, tuple[float, float | None]]:
    """馬単・馬複・ワイド・三連複のマトリクス表 → {組番: (odds, odds_max)}

    表は三角形に組まれていて、**列は「n 番目のセル」ではなく grid 上の位置で決まる**。

      ヘッダ行:  <th colspan=2>1</th><th colspan=2>2</th>...  ← 1列 = grid 2 マス
      本文行:    <th>相手馬番</th><td>オッズ</td>  が 1 列ぶん
                 <td colspan=2></td>              で列を丸ごと空ける

    さらに、三角形が空けた右下の領域に**後続列のヘッダが `<th colspan=2>` として
    差し込まれる**（10頭立てなら 9 列目がここに出る）。

    セルの並び順で列を決めると、空セルが入った行から先が丸ごとずれる。
    2026-08-06 にこれで実際にオッズと組番の対応が壊れていたのを確認している
    （2026-08-03 4R 馬複 6-10 が 9.7 と記録されていたが、払戻から正しくは 4.3）。
    """
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for tb in soup.find_all("table"):
        rows = tb.find_all("tr")
        if not rows:
            continue

        # grid 位置 → その列の 1 頭目（三連複なら "1-2" のように 2 頭）
        col_first: dict[int, str] = {}
        pos = 0
        for c in rows[0].find_all(["th", "td"]):
            col_first[pos // 2] = c.get_text(strip=True)
            pos += int(c.get("colspan", 1))
        if not col_first or not all(
                re.fullmatch(r"\d+(-\d+)?", v) for v in col_first.values()):
            continue

        for tr in rows[1:]:
            cells = tr.find_all(["th", "td"])
            pos = 0
            i = 0
            while i < len(cells):
                cell = cells[i]
                span = int(cell.get("colspan", 1))
                nxt = cells[i + 1] if i + 1 < len(cells) else None

                if cell.name == "th" and span == 1 and nxt is not None and nxt.name == "td":
                    first = col_first.get(pos // 2)
                    text = nxt.get_text(" ", strip=True)
                    if first and text:
                        vals = re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))
                        if vals:
                            nums = first.split("-") + [cell.get_text(strip=True)]
                            out[norm_combo(nums, ordered)] = (
                                _odds_value(vals[0]),
                                _odds_value(vals[1]) if len(vals) > 1 else None)
                    pos += span + int(nxt.get("colspan", 1))
                    i += 2
                    continue

                if cell.name == "th" and span >= 2:
                    # 三角形の空き領域に差し込まれた後続列のヘッダ
                    col_first[pos // 2] = cell.get_text(strip=True)

                pos += span
                i += 1
    return out


def parse_sanrentan_page(html: str) -> dict[str, tuple[float, None]]:
    """三連単ページ（1着馬固定）の "1 → 2 → 3" リスト → {組番: (odds, None)}"""
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for tb in soup.find_all("table"):
        for tr in tb.find_all("tr"):
            th = tr.find("th")
            td = tr.find("td")
            if th is None or td is None:
                continue
            m = re.fullmatch(r"(\d+)\s*→\s*(\d+)\s*→\s*(\d+)",
                             th.get_text(" ", strip=True).replace("\xa0", " "))
            if not m:
                continue
            v = re.search(r"\d+(?:\.\d+)?", td.get_text(strip=True).replace(",", ""))
            if v:
                out["-".join(m.groups())] = (_odds_value(v.group()), None)
    return out


def scrape(
    types: str = DEFAULT_TYPES,
    since: str | None = None,
    races_db_path: Path | str = RACES_DB,
    db_path: Path | str = ODDS_DB,
    interval: float = REQUEST_INTERVAL,
    limit: int | None = None,
    max_consecutive_failures: int = MAX_CONSECUTIVE_FAILURES,
) -> None:
    """組み合わせ券種の確定オッズを収集する。types はカンマ区切り（TYPES のキー）。

    limit は**レース数**の上限（マトリクス4券種なら 1 レース 4 リクエスト）。
    全期間だと 13 万リクエスト・37 時間かかるので、必ず区切って回すこと。

    取得に失敗したレースは combo_meta を書かずに飛ばすので、次回の実行で再度対象になる。
    連続で失敗したら中断する（例外ではなく正常終了。そこまでの成果を保存できるようにするため）。
    """
    selected = [TYPES[t] for t in types.split(",")]

    db = connect(db_path, ODDS_SCHEMA)
    races_db = connect_readonly(races_db_path)
    if since:
        all_races = races_db.execute(
            "SELECT race_date, race_no FROM races WHERE race_date >= ?"
            " ORDER BY race_date DESC, race_no", (since,)).fetchall()
    else:
        all_races = races_db.execute(
            "SELECT race_date, race_no FROM races ORDER BY race_date DESC, race_no").fetchall()
    # 三連単の1着馬指定に使う馬番一覧（取消・除外は発売対象外の可能性があるが頁は存在する）
    horse_nos: dict[tuple[str, int], list[int]] = {}
    for rd, rn, hn in races_db.execute(
            "SELECT race_date, race_no, horse_no FROM results"
            " WHERE status NOT IN ('取消','除外')"):
        horse_nos.setdefault((rd, rn), []).append(hn)
    races_db.close()

    have = {tuple(r) for r in db.execute("SELECT race_date, race_no, bet_type FROM combo_meta")}
    # 未取得の券種が 1 つでも残っているレースだけを対象にしてから limit を当てる。
    # 取得済みレースを数に含めると、実際にはほとんど進まない実行になってしまう。
    targets = [
        (rd, rn) for rd, rn in all_races
        if any((rd, rn, t["bet_type"]) not in have for t in selected)
    ]
    if limit is not None:
        targets = targets[:limit]
    print(f"取得対象 {len(targets)} レース × 最大 {len(selected)} 券種")

    fetcher = Fetcher(interval)
    done = 0
    failed = 0
    consecutive = 0
    aborted = False
    for race_date, race_no in targets:
        if aborted:
            break
        for t in selected:
            if (race_date, race_no, t["bet_type"]) in have:
                continue
            base = dict(PARAMS_BASE, raceDy=race_date.replace("-", ""),
                        raceNb=race_no, betType=t["betType"])
            combos: dict[str, tuple[float, float | None]] = {}
            try:
                if t["betType"] == "8":
                    for hn in horse_nos.get((race_date, race_no), []):
                        combos.update(
                            parse_sanrentan_page(fetcher.get(URL, dict(base, horseNb=hn))))
                else:
                    combos = parse_matrix(fetcher.get(URL, base), t["ordered"])
            except requests.RequestException as e:
                failed += 1
                consecutive += 1
                print(f"  {race_date} {race_no}R {t['bet_type']}: 取得失敗（スキップ）: {e}",
                      file=sys.stderr)
                if consecutive >= max_consecutive_failures:
                    print(f"連続 {consecutive} 件失敗したため中断する。"
                          "相手サイトが応答していない可能性が高い。", file=sys.stderr)
                    aborted = True
                    break
                continue
            consecutive = 0
            for comb, (o, omax) in combos.items():
                db.execute("INSERT OR REPLACE INTO combo_odds VALUES (?,?,?,?,?,?)",
                           (race_date, race_no, t["bet_type"], comb, o, omax))
            db.execute("INSERT OR REPLACE INTO combo_meta VALUES (?,?,?,?,?)",
                       (race_date, race_no, t["bet_type"], len(combos),
                        dt.datetime.now().isoformat(timespec="seconds")))
            db.commit()
        done += 1
        if done % 100 == 0:
            print(f"{done}/{len(targets)} レース完了（現在 {race_date}）", flush=True)
    print(f"完了: {done} レース / 失敗 {failed} 件")
