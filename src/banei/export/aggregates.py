"""公開してよい集計だけを生成する。

**このモジュールは公開データの唯一の出口。** ここを通ったものだけがサイトのビルド入力に
なる（docs/architecture.md §3.4）。生データ（個別レースの着順・オッズ・払戻）が漏れると
「そのページを全部集めれば元の DB が復元できる」状態になり、方針が壊れる。

守るための仕組み:

- 出力レコードに個体を特定するキー（race_date / race_no / horse_no など）を入れない
- 各行は件数列（`n` または `n_` で始まる整数列）を持ち、MIN_GROUP_SIZE 件以上であること
- 上記を `policy_violations()` が検査し、**書き出し時に違反があれば例外で止まる**
  （テストだけだと `banei export` を直接叩いたときに素通りするため）

新しい集計を足すときは `AGGREGATES` に登録するだけでよい。検査は自動で対象に含まれる。
"""

import sqlite3
from collections.abc import Callable
from pathlib import Path

from banei.config import RACES_DB

# これ未満の件数しかないグループは公開しない。
# 集約先が小さいと個々のレース・馬の値がそのまま読み取れてしまうため。
MIN_GROUP_SIZE = 30

# 出力に含めてはいけないキー。個別のレース・馬・組番を指すもの。
FORBIDDEN_KEYS = frozenset({
    "race_date", "race_no", "horse_no", "horse_id", "horse_name",
    "combination", "bet_type", "time_str", "margin", "status",
})


def policy_violations(name: str, rows: list[dict], check_group_size: bool = True) -> list[str]:
    """公開ポリシー違反を列挙する。空リストなら合格。

    件数列を必須にしているのは、集約の粒度が細かすぎないことを機械的に確かめるため。
    列名の規約は「`n` そのもの、または `n_` で始まる整数列」で、**すべて** が
    MIN_GROUP_SIZE 以上であること（1 つでも小さい列があれば、その粒度で個体の値が読める）。

    `check_group_size=False` はサイト全体のサマリ専用。あちらの `n_jockeys` などは
    グループの大きさではなく実体の個数（騎手は 51 人しかいない）なので、
    グループサイズの規則を当てると意味を成さない。個体特定キーの検査は同じように行う。
    """
    problems = []
    for i, row in enumerate(rows):
        bad = FORBIDDEN_KEYS & row.keys()
        if bad:
            problems.append(f"{name}[{i}]: 個体を特定するキー {sorted(bad)} が含まれている")
        if not check_group_size:
            continue
        counts = [
            v for k, v in row.items()
            if (k == "n" or k.startswith("n_")) and isinstance(v, int) and not isinstance(v, bool)
        ]
        if not counts:
            problems.append(f"{name}[{i}]: 件数列（n または n_*）が無い")
        elif min(counts) < MIN_GROUP_SIZE:
            problems.append(
                f"{name}[{i}]: 集約件数 {min(counts)} が下限 {MIN_GROUP_SIZE} 未満")
    return problems


def _rows(con: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def summary(con: sqlite3.Connection) -> dict:
    """サイト全体のサマリ。個別レースを指す情報は含まない。"""
    n_races, period_start, period_end = con.execute(
        "SELECT COUNT(*), MIN(race_date), MAX(race_date) FROM races").fetchone()
    n_runs, n_horses, n_jockeys, n_trainers = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT horse_name), COUNT(DISTINCT jockey),"
        " COUNT(DISTINCT trainer) FROM results").fetchone()
    return {
        "n_races": n_races,
        "n_runs": n_runs,
        "n_horses": n_horses,
        "n_jockeys": n_jockeys,
        "n_trainers": n_trainers,
        "period_start": period_start,
        "period_end": period_end,
    }


def moisture_vs_time(con: sqlite3.Connection) -> list[dict]:
    """馬場水分ごとの勝ちタイム。水分が高いほど砂が締まって速くなる。"""
    return _rows(con, """
        SELECT CAST(ROUND(ra.moisture) AS INTEGER) AS moisture,
               COUNT(*) AS n_wins,
               ROUND(AVG(r.time_sec), 1) AS avg_win_sec,
               ROUND(MIN(r.time_sec), 1) AS fastest_sec
        FROM results r JOIN races ra USING (race_date, race_no)
        WHERE r.finish = 1 AND r.time_sec IS NOT NULL AND ra.moisture IS NOT NULL
        GROUP BY 1 HAVING COUNT(*) >= ?
        ORDER BY 1
    """, (MIN_GROUP_SIZE,))


def popularity_performance(con: sqlite3.Connection) -> list[dict]:
    """人気別の勝率と単勝回収率。市場の効率性を示す基礎データ。"""
    return _rows(con, """
        SELECT r.popularity,
               COUNT(*) AS n,
               ROUND(100.0 * SUM(CASE WHEN r.finish = 1 THEN 1 ELSE 0 END) / COUNT(*), 1)
                 AS win_rate,
               ROUND(100.0 * SUM(CASE WHEN r.finish = 1 THEN p.amount ELSE 0 END)
                     / (COUNT(*) * 100.0), 1) AS roi
        FROM results r
        LEFT JOIN payouts p ON p.race_date = r.race_date AND p.race_no = r.race_no
             AND p.bet_type = '単勝' AND CAST(p.combination AS INTEGER) = r.horse_no
        WHERE r.popularity IS NOT NULL
        GROUP BY 1 HAVING COUNT(*) >= ?
        ORDER BY 1
    """, (MIN_GROUP_SIZE,))


def weight_handicap(con: sqlite3.Connection) -> list[dict]:
    """レース内の積載重量差ごとの勝率。ばんえい特有のハンデの効き方。"""
    return _rows(con, """
        WITH d AS (
            SELECT r.finish,
                   r.weight_carried - MIN(r.weight_carried) OVER (
                       PARTITION BY r.race_date, r.race_no) AS wc_diff
            FROM results r
            WHERE r.weight_carried IS NOT NULL AND r.status NOT IN ('取消', '除外')
        )
        SELECT wc_diff AS weight_diff_kg,
               COUNT(*) AS n,
               ROUND(100.0 * SUM(CASE WHEN finish = 1 THEN 1 ELSE 0 END) / COUNT(*), 1)
                 AS win_rate
        FROM d
        GROUP BY 1 HAVING COUNT(*) >= ?
        ORDER BY 1
    """, (MIN_GROUP_SIZE,))


def monthly_activity(con: sqlite3.Connection) -> list[dict]:
    """年ごとのレース数。データの厚みを示す。"""
    return _rows(con, """
        SELECT CAST(substr(race_date, 1, 4) AS INTEGER) AS year,
               COUNT(*) AS n_races
        FROM races
        GROUP BY 1 HAVING COUNT(*) >= ?
        ORDER BY 1
    """, (MIN_GROUP_SIZE,))


# 出力名 → 集計関数。テストはここを走査して全出力を検査する。
AGGREGATES: dict[str, Callable[[sqlite3.Connection], list[dict]]] = {
    "moisture_vs_time": moisture_vs_time,
    "popularity_performance": popularity_performance,
    "weight_handicap": weight_handicap,
    "monthly_activity": monthly_activity,
}


def connect(db_path: Path | str = RACES_DB) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
