"""収集したデータの検証。

日次収集の直後に走らせ、異常があれば非ゼロ終了してワークフローを失敗させる。
相手サイトの HTML 構造が変わってパーサが壊れた場合、ここで止まる。

閾値と不変条件は 2007-04〜2026-08 の実データ（33,493 レース / 307,849 行）から
導出している。推測ではないので、正常なデータで誤検知しない:

- 1 レースの出走頭数は 4〜10 頭（余裕をみて 1〜20 を許容）
- 1 開催日のレース数は 3〜12（中止で 0 の日も 6 日ある）
- **同着があるため着順の重複は異常ではない**（1着が複数のレースが 37 存在する）
- **取消・除外馬は win_odds が NULL**（617 行）。異常なのはレース内の全馬が NULL の場合だけ
- 開催日の間隔は最大 34 日（長期休催）

ml エクストラに依存しない（日次スクレイプのジョブから呼ぶため）。
"""

import sqlite3
from pathlib import Path

from banei.config import ODDS_DB, RACES_DB

# (説明, 違反行を返す SQL)。1 行でも返れば異常。
ERROR_CHECKS: list[tuple[str, str]] = [
    ("races に対応しない results が存在する",
     """SELECT s.race_date, s.race_no, s.horse_no FROM results s
        WHERE NOT EXISTS (SELECT 1 FROM races r
                          WHERE r.race_date=s.race_date AND r.race_no=s.race_no)"""),
    ("results が 1 行も無いレースが存在する",
     """SELECT r.race_date, r.race_no FROM races r
        WHERE NOT EXISTS (SELECT 1 FROM results s
                          WHERE s.race_date=r.race_date AND s.race_no=r.race_no)"""),
    ("horse_name が空の results が存在する",
     "SELECT race_date, race_no, horse_no FROM results WHERE horse_name IS NULL OR horse_name=''"),
    ("単勝払戻が無いレースが存在する",
     """SELECT r.race_date, r.race_no FROM races r
        WHERE NOT EXISTS (SELECT 1 FROM payouts p
                          WHERE p.race_date=r.race_date AND p.race_no=r.race_no
                            AND p.bet_type='単勝')"""),
    ("払戻金が 0 円以下または欠損している",
     "SELECT race_date, race_no, bet_type FROM payouts WHERE amount IS NULL OR amount<=0"),
    ("出走頭数が 1〜20 頭の範囲外のレースが存在する",
     """SELECT race_date, race_no, COUNT(*) n FROM results
        GROUP BY 1,2 HAVING n<1 OR n>20"""),
    ("race_no が 1〜15 の範囲外",
     "SELECT race_date, race_no FROM races WHERE race_no<1 OR race_no>15"),
    ("着順が 1〜20 の範囲外",
     "SELECT race_date, race_no, horse_no, finish FROM results"
     " WHERE finish IS NOT NULL AND (finish<1 OR finish>20)"),
    ("距離が 100〜1000m の範囲外",
     "SELECT race_date, race_no, distance_m FROM races"
     " WHERE distance_m IS NULL OR distance_m<100 OR distance_m>1000"),
    ("馬場水分が 0〜20 の範囲外または欠損",
     "SELECT race_date, race_no, moisture FROM races"
     " WHERE moisture IS NULL OR moisture<0 OR moisture>20"),
    ("馬齢が 2〜25 の範囲外",
     "SELECT race_date, race_no, horse_no, age FROM results"
     " WHERE age IS NOT NULL AND (age<2 OR age>25)"),
    ("積載重量が 300〜1200kg の範囲外",
     "SELECT race_date, race_no, horse_no, weight_carried FROM results"
     " WHERE weight_carried IS NOT NULL AND (weight_carried<300 OR weight_carried>1200)"),
    ("性別が 牡/牝/セン 以外",
     "SELECT DISTINCT sex FROM results WHERE sex IS NOT NULL AND sex NOT IN ('牡','牝','セン')"),
    ("scraped_days.n_races が 0〜15 の範囲外",
     "SELECT race_date, n_races FROM scraped_days WHERE n_races<0 OR n_races>15"),
]

# odds.db が ATTACH されている場合のみ実行する
ODDS_ERROR_CHECKS: list[tuple[str, str]] = [
    ("レース内の全馬で単勝オッズが欠損している（取消・除外だけなら正常）",
     """SELECT race_date, race_no FROM o.odds
        GROUP BY 1,2
        HAVING SUM(CASE WHEN win_odds IS NULL OR win_odds<=0 THEN 1 ELSE 0 END)=COUNT(*)"""),
    ("複勝オッズの下限が上限を上回っている",
     """SELECT race_date, race_no, horse_no FROM o.odds
        WHERE place_min IS NOT NULL AND place_max IS NOT NULL AND place_min>place_max"""),
    # 票が入らなかった組番はオッズが付かず NULL になる（実データで確認済み）。
    # 異常なのは負の値と、レース内の全組番が NULL のとき（パース失敗の兆候）。
    ("組み合わせオッズが負の値",
     "SELECT race_date, race_no, bet_type, combination FROM o.combo_odds WHERE odds < 0"),
    ("券種内の全組番でオッズが欠損している",
     """SELECT race_date, race_no, bet_type FROM o.combo_odds
        GROUP BY 1,2,3 HAVING SUM(CASE WHEN odds IS NULL THEN 1 ELSE 0 END)=COUNT(*)"""),
]

# (説明, 値を返す SQL, 異常と判定する条件)
WARNING_CHECKS: list[tuple[str, str]] = [
    ("直近の開催日でレースが 1 件も保存されていない（中止なら正常）",
     """SELECT race_date, n_races FROM scraped_days
        WHERE n_races=0 AND race_date >= date('now','-60 days')"""),
]

# 開催間隔の実績最大は 34 日。長期休催を誤検知しないよう余裕をみる。
STALE_DAYS = 45


def _violations(con: sqlite3.Connection, sql: str, limit: int = 5):
    rows = con.execute(sql).fetchall()
    return len(rows), rows[:limit]


def run(
    races_db_path: Path | str = RACES_DB,
    odds_db_path: Path | str | None = ODDS_DB,
    verbose: bool = True,
) -> int:
    """検証を実行し、異常があれば 1 を返す。"""
    con = sqlite3.connect(f"file:{Path(races_db_path)}?mode=ro", uri=True)
    checks = list(ERROR_CHECKS)
    if odds_db_path and Path(odds_db_path).exists():
        con.execute("ATTACH ? AS o", (f"file:{Path(odds_db_path)}?mode=ro",))
        checks += ODDS_ERROR_CHECKS

    errors = 0
    for label, sql in checks:
        n, sample = _violations(con, sql)
        if n:
            errors += 1
            print(f"NG  {label}: {n} 件")
            for row in sample:
                print(f"      {row}")
        elif verbose:
            print(f"ok  {label}")

    warnings = 0
    for label, sql in WARNING_CHECKS:
        n, sample = _violations(con, sql)
        if n:
            warnings += 1
            print(f"警告 {label}: {n} 件")
            for row in sample:
                print(f"      {row}")

    latest, days = con.execute(
        "SELECT MAX(race_date), CAST(julianday('now')-julianday(MAX(race_date)) AS INT)"
        " FROM races").fetchone()
    if days is not None and days > STALE_DAYS:
        warnings += 1
        print(f"警告 最新レースが {days} 日前（{latest}）。収集が止まっている可能性がある")

    n_races, n_results = con.execute(
        "SELECT (SELECT COUNT(*) FROM races), (SELECT COUNT(*) FROM results)").fetchone()
    con.close()

    print(f"--- races {n_races} / results {n_results} / 最新 {latest}")
    if errors:
        print(f"検証失敗: {errors} 件の異常")
        return 1
    print(f"検証成功（警告 {warnings} 件）")
    return 0
