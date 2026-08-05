"""オッズパークから組み合わせ券種の確定オッズを収集して odds.db に保存する。

券種と betType の対応（払戻金との照合で確認済み）:
  馬単=5 / 馬複=6 / ワイド=7(レンジ) / 三連単=8(1着馬ごとに1頁) / 三連複=9

組番の表記は payouts テーブルに合わせる:
  順序あり（馬単・三連単）は着順どおり "8-2", "8-2-4"
  順序なし（馬複・ワイド・三連複）は昇順 "2-8", "2-4-8"

三連単は 1 着馬ごとに 1 リクエスト必要なため重い。期間を絞って実行すること。
"""

import datetime as dt
import re
from pathlib import Path

from bs4 import BeautifulSoup

from banei.config import ODDS_DB, RACES_DB, REQUEST_INTERVAL
from banei.db.schema import ODDS_SCHEMA, connect, connect_readonly
from banei.net import Fetcher

URL = "https://www.oddspark.com/keiba/Odds.do"
PARAMS_BASE = {"sponsorCd": "04", "opTrackCd": "03", "viewType": "0"}

TYPES = {
    "umatan":     {"bet_type": "馬単",   "betType": "5", "ordered": True},
    "umaren":     {"bet_type": "馬複",   "betType": "6", "ordered": False},
    "wide":       {"bet_type": "ワイド", "betType": "7", "ordered": False},
    "sanrentan":  {"bet_type": "三連単", "betType": "8", "ordered": True},
    "sanrenpuku": {"bet_type": "三連複", "betType": "9", "ordered": False},
}

DEFAULT_TYPES = "umatan,umaren,wide,sanrenpuku"


def norm_combo(nums: list[str], ordered: bool) -> str:
    return "-".join(nums if ordered else sorted(nums, key=int))


def parse_matrix(html: str, ordered: bool) -> dict[str, tuple[float, float | None]]:
    """馬単・馬複・ワイド・三連複のマトリクス表 → {組番: (odds, odds_max)}"""
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for tb in soup.find_all("table"):
        rows = tb.find_all("tr")
        if not rows:
            continue
        headers = [c.get_text(strip=True) for c in rows[0].find_all("th")]
        if not headers or not all(re.fullmatch(r"\d+(-\d+)?", h) for h in headers):
            continue
        for tr in rows[1:]:
            pairs, cur = [], None
            for c in tr.find_all(["th", "td"]):
                if c.name == "th":
                    cur = c.get_text(strip=True)
                elif cur is not None:
                    pairs.append((cur, c.get_text(" ", strip=True)))
                    cur = None
            for j, (partner, text) in enumerate(pairs):
                if j >= len(headers) or not text:
                    continue
                nums = headers[j].split("-") + [partner]
                vals = re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))
                if not vals:
                    continue
                out[norm_combo(nums, ordered)] = (
                    float(vals[0]), float(vals[1]) if len(vals) > 1 else None)
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
                out["-".join(m.groups())] = (float(v.group()), None)
    return out


def scrape(
    types: str = DEFAULT_TYPES,
    since: str | None = None,
    races_db_path: Path | str = RACES_DB,
    db_path: Path | str = ODDS_DB,
    interval: float = REQUEST_INTERVAL,
) -> None:
    """組み合わせ券種の確定オッズを収集する。types はカンマ区切り（TYPES のキー）。"""
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
    fetcher = Fetcher(interval)
    done = 0
    for race_date, race_no in all_races:
        for t in selected:
            if (race_date, race_no, t["bet_type"]) in have:
                continue
            base = dict(PARAMS_BASE, raceDy=race_date.replace("-", ""),
                        raceNb=race_no, betType=t["betType"])
            combos: dict[str, tuple[float, float | None]] = {}
            if t["betType"] == "8":
                for hn in horse_nos.get((race_date, race_no), []):
                    combos.update(parse_sanrentan_page(fetcher.get(URL, dict(base, horseNb=hn))))
            else:
                combos = parse_matrix(fetcher.get(URL, base), t["ordered"])
            for comb, (o, omax) in combos.items():
                db.execute("INSERT OR REPLACE INTO combo_odds VALUES (?,?,?,?,?,?)",
                           (race_date, race_no, t["bet_type"], comb, o, omax))
            db.execute("INSERT OR REPLACE INTO combo_meta VALUES (?,?,?,?,?)",
                       (race_date, race_no, t["bet_type"], len(combos),
                        dt.datetime.now().isoformat(timespec="seconds")))
            db.commit()
        done += 1
        if done % 100 == 0:
            print(f"{done}/{len(all_races)} レース完了（現在 {race_date}）", flush=True)
    print(f"完了: {done} レース")
