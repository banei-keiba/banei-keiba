"""keiba.go.jp からばんえい競馬（帯広・babaCode=3）のレース結果を収集する。

取得済みの開催日は scraped_days テーブルで管理し、再実行時はスキップする。
中断してもそのまま再実行すれば続きから取得できる。
"""

import datetime as dt
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from banei.config import RACES_DB, REQUEST_INTERVAL
from banei.db.schema import RACES_SCHEMA, connect
from banei.net import Fetcher

BASE = "https://www.keiba.go.jp/KeibaWeb"
BABA_CODE = 3  # 帯広（ばんえい）


def month_range(start: str, end: str) -> Iterator[tuple[int, int]]:
    """'YYYY-MM' から 'YYYY-MM' までの (年, 月) を順に返す。"""
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    while (y, m) <= (ey, em):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def parse_int(text: str) -> int | None:
    m = re.search(r"-?\d+", text.replace(",", ""))
    return int(m.group()) if m else None


def parse_time(text: str) -> float | None:
    """'1:23.4' / '23.4' を秒に変換する。"""
    m = re.match(r"(?:(\d+):)?(\d+)\.(\d)", text.strip())
    if not m:
        return None
    minutes = int(m.group(1) or 0)
    return minutes * 60 + int(m.group(2)) + int(m.group(3)) / 10


def get_race_dates(fetcher: Fetcher, year: int, month: int) -> list[str]:
    """月間開催スケジュールから帯広の開催日 (YYYY-MM-DD) を返す。"""
    html = fetcher.get(
        f"{BASE}/MonthlyConveneInfo/MonthlyConveneInfoTop",
        {"k_year": year, "k_month": month},
    )
    soup = BeautifulSoup(html, "html.parser")
    dates = set()
    for a in soup.find_all("a", href=True):
        if "RaceList" not in a["href"]:
            continue
        qs = parse_qs(urlparse(a["href"]).query)
        if qs.get("k_babaCode") == [str(BABA_CODE)] and "k_raceDate" in qs:
            dates.add(qs["k_raceDate"][0].replace("/", "-"))
    return sorted(dates)


def get_race_nos(fetcher: Fetcher, date: str) -> list[int]:
    """1 開催日のレース番号一覧。"""
    html = fetcher.get(
        f"{BASE}/TodayRaceInfo/RaceList",
        {"k_raceDate": date.replace("-", "/"), "k_babaCode": BABA_CODE},
    )
    soup = BeautifulSoup(html, "html.parser")
    nos = set()
    for a in soup.find_all("a", href=True):
        if "RaceMarkTable" in a["href"]:
            qs = parse_qs(urlparse(a["href"]).query)
            if "k_raceNo" in qs:
                nos.add(int(qs["k_raceNo"][0]))
    return sorted(nos)


def parse_result_page(html: str) -> dict | None:
    """成績ページから レース情報・着順・払戻 を抜き出す。結果未確定なら None。"""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return None
    header = [
        re.sub(r"\s", "", th.get_text())
        for th in tables[0].find_all("tr")[0].find_all(["th", "td"])
    ]
    if "着順" not in header or "馬名" not in header:
        return None
    col = {name: i for i, name in enumerate(header)}

    h3 = soup.find("h3")
    race = {
        "name": h3.get_text(strip=True) if h3 else None,
        "distance_m": None,
        "weather": None,
        "moisture": None,
        "conditions": None,
    }
    for el in soup.find_all(["p", "div", "li"]):
        text = el.get_text(" ", strip=True)
        if "天候" in text and len(text) < 200:
            race["conditions"] = text
            if m := re.search(r"(\d+)ｍ", text):
                race["distance_m"] = int(m.group(1))
            if m := re.search(r"天候：(\S+)", text):
                race["weather"] = m.group(1)
            if m := re.search(r"馬場：([\d.]+)", text):
                race["moisture"] = float(m.group(1))
            break

    def cell(cells, name):
        i = col.get(name)
        return cells[i].get_text(" ", strip=True) if i is not None and i < len(cells) else ""

    results = []
    for tr in tables[0].find_all("tr")[1:]:
        cells = tr.find_all("td")
        if not cells:
            continue
        horse_no = parse_int(cell(cells, "馬番"))
        if horse_no is None:
            continue
        horse_id = None
        i_name = col.get("馬名")
        if i_name is not None and i_name < len(cells):
            a = cells[i_name].find("a", href=True)
            if a and (m := re.search(r"k_lineageLoginCode=(\d+)", a["href"])):
                horse_id = m.group(1)
        sex_age = cell(cells, "性齢")
        weight = cell(cells, "馬体重（増減）")
        jockey = re.sub(r"[（(].*", "", cell(cells, "騎手（所属）")).strip()
        jockey = jockey.lstrip("☆★▲△◇◆")  # 減量騎手マーク
        finish_raw = cell(cells, "着順")
        margin = cell(cells, "着差")
        # 中止・失格などは着順欄が空で着差欄に理由が入る
        status = finish_raw if finish_raw else ("" if margin in ("", "―") else margin)
        wm = re.match(r"(\d+)\s*(?:\(([+-]?\d+)\))?", weight)
        results.append({
            "horse_no": horse_no,
            "horse_id": horse_id,
            "bracket": parse_int(cell(cells, "枠")),
            "finish": parse_int(finish_raw) if finish_raw.isdigit() else None,
            "status": status,
            "horse_name": cell(cells, "馬名"),
            "affiliation": cell(cells, "所属"),
            "sex": sex_age.split()[0] if sex_age else None,
            "age": parse_int(sex_age),
            "weight_carried": parse_int(cell(cells, "積載重量")),
            "jockey": jockey,
            "trainer": cell(cells, "調教師"),
            "horse_weight": int(wm.group(1)) if wm else None,
            "horse_weight_diff": int(wm.group(2)) if wm and wm.group(2) else None,
            "time_str": cell(cells, "タイム"),
            "time_sec": parse_time(cell(cells, "タイム")),
            "margin": margin,
            "popularity": parse_int(cell(cells, "人気")),
        })
    if not any(r["finish"] for r in results):
        return None  # 全馬着順なし＝未確定または中止

    payouts = []
    bet_type = None
    for table in tables[1:]:
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(cells) == 4:
                bet_type, combo, amount, pop = cells
            elif len(cells) == 3 and bet_type:
                combo, amount, pop = cells
            else:
                continue
            if "円" not in amount:
                continue
            payouts.append({
                "bet_type": bet_type,
                "combination": combo,
                "amount": parse_int(amount),
                "popularity": parse_int(pop),
            })

    return {"race": race, "results": results, "payouts": payouts}


def save_race(db: sqlite3.Connection, date: str, race_no: int, parsed: dict) -> None:
    race = parsed["race"]
    db.execute(
        "INSERT OR REPLACE INTO races VALUES (?,?,?,?,?,?,?)",
        (date, race_no, race["name"], race["distance_m"],
         race["weather"], race["moisture"], race["conditions"]),
    )
    for r in parsed["results"]:
        db.execute(
            "INSERT OR REPLACE INTO results (race_date, race_no, horse_no, horse_id,"
            " bracket, finish, status, horse_name, affiliation, sex, age,"
            " weight_carried, jockey, trainer, horse_weight, horse_weight_diff,"
            " time_str, time_sec, margin, popularity)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (date, race_no, r["horse_no"], r["horse_id"], r["bracket"], r["finish"], r["status"],
             r["horse_name"], r["affiliation"], r["sex"], r["age"],
             r["weight_carried"], r["jockey"], r["trainer"],
             r["horse_weight"], r["horse_weight_diff"],
             r["time_str"], r["time_sec"], r["margin"], r["popularity"]),
        )
    for p in parsed["payouts"]:
        db.execute(
            "INSERT OR REPLACE INTO payouts VALUES (?,?,?,?,?,?)",
            (date, race_no, p["bet_type"], p["combination"], p["amount"], p["popularity"]),
        )


def scrape(
    start: str,
    end: str,
    db_path: Path | str = RACES_DB,
    interval: float = REQUEST_INTERVAL,
) -> None:
    """start('YYYY-MM') から end('YYYY-MM') までのレース結果を収集する。"""
    fetcher = Fetcher(interval)
    db = connect(db_path, RACES_SCHEMA)
    today = dt.date.today().isoformat()

    for year, month in month_range(start, end):
        dates = get_race_dates(fetcher, year, month)
        print(f"{year}-{month:02d}: 開催 {len(dates)} 日")
        for date in dates:
            if date >= today:
                print(f"  {date}: 未来日のためスキップ")
                continue
            if db.execute("SELECT 1 FROM scraped_days WHERE race_date=?", (date,)).fetchone():
                print(f"  {date}: 取得済み")
                continue
            race_nos = get_race_nos(fetcher, date)
            saved = 0
            for no in race_nos:
                html = fetcher.get(
                    f"{BASE}/TodayRaceInfo/RaceMarkTable",
                    {"k_raceDate": date.replace("-", "/"),
                     "k_raceNo": no, "k_babaCode": BABA_CODE},
                )
                parsed = parse_result_page(html)
                if parsed is None:
                    print(f"  {date} {no}R: 結果なし（中止/未確定）")
                    continue
                save_race(db, date, no, parsed)
                saved += 1
            db.execute(
                "INSERT OR REPLACE INTO scraped_days VALUES (?,?,?)",
                (date, saved, dt.datetime.now().isoformat(timespec="seconds")),
            )
            db.commit()
            print(f"  {date}: {saved}/{len(race_nos)} レース保存")
    db.close()
    print("完了")
