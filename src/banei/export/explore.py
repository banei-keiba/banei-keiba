"""探索 UI 用のクロス表。

設計: docs/superpowers/specs/2026-10-13-explore-ui-design.md

- 対象は締めたシーズンまでの出走。シーズンは 4/1〜翌 3/31 で、締めは 5/1。
  日次収集が直近 30 日を取り直すので、取りこぼしが埋まるのを待ってから締める。
  毎日実行しても、出力は締めが進む年 1 回しか変わらない
- 各表は対象の出走をもれなく分ける。マスを消すと、別に公開した合計との引き算で値が
  割り出せるため、規則を満たさない区分は隣とまとめる（merge.py）
- 規則は「期間帯ごとに全マスが 0 件か 30 件以上」。期間帯は版と版の差で切り出される単位
"""

import datetime as dt
import itertools
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from banei.config import JST
from banei.export.aggregates import MIN_GROUP_SIZE
from banei.export.merge import merge_bins, regroup, violations

# 初回公開（2025 シーズンまで）の直近 3 シーズンの始まり。これより前のシーズンは
# 1 つの期間帯にまとめる。版の差で切り出される単位を決めているので、後から変えては
# いけない（変えると、過去の版との差で 30 件未満の集計が切り出せてしまう）。
FIRST_RECENT_SEASON = 2023
RECENT_SEASONS = 3
CLOSE_MONTH = 5  # この月の 1 日に前シーズンを締める
SEASON_START_MONTH = 4

# 各マスの集計値の並び。merge.regroup で要素ごとに足し合わせるのでリストで持つ
N, WIN, TOP2, PLACE, WIN_PAY, PLACE_PAY = range(6)


@dataclass(frozen=True)
class Axis:
    key: str  # JSON のキーと URL
    name: str  # 表示名
    sql: str  # 基本区分の番号（0 始まり）。想定外の値は NULL
    bins: tuple[tuple[str | None, str | None], ...] = ()  # 範囲の軸: (下限, 上限)
    names: tuple[str, ...] = ()  # 名義の軸: 区分名
    unit: str = ""

    @property
    def n_bins(self) -> int:
        return len(self.bins) or len(self.names)

    def label(self, group: list[int]) -> str:
        """まとめた区分の表示名。範囲の軸は「先頭の下限〜末尾の上限」、名義の軸は「・」でつなぐ。"""
        if self.names:
            return "・".join(self.names[i] for i in group)
        lo, hi = self.bins[group[0]][0], self.bins[group[-1]][1]
        if lo is None and hi is None:
            return "すべて"
        if lo == hi:
            return f"{lo}{self.unit}"
        if hi is None:
            return f"{lo}{self.unit}〜"
        if lo is None:
            return f"〜{hi}{self.unit}"
        return f"{lo}〜{hi}{self.unit}"


def _each(values) -> tuple[tuple[str, str], ...]:
    return tuple((str(v), str(v)) for v in values)


# 並びは URL 上の軸の順でもある。同じ組み合わせが 2 つの URL にならないよう固定する。
# まとめるときは隣とだけまとめるので、名義の軸も並び順に意味がある。
AXES: tuple[Axis, ...] = (
    Axis("popularity", "人気",
         "CASE WHEN s.popularity BETWEEN 1 AND 10 THEN s.popularity - 1 END",
         bins=_each(range(1, 11))),
    # horse_no は aggregates.FORBIDDEN_KEYS に当たる（生データの個体キーと同じ名前を使わない）
    Axis("post", "馬番",
         "CASE WHEN s.horse_no BETWEEN 1 AND 10 THEN s.horse_no - 1 END",
         bins=_each(range(1, 11))),
    Axis("weight_diff", "重量差",
         "CASE WHEN s.wd = 0 THEN 0 WHEN s.wd <= 10 THEN 1 WHEN s.wd <= 20 THEN 2"
         " WHEN s.wd <= 30 THEN 3 WHEN s.wd > 30 THEN 4 END",
         bins=(("0", "0"), ("1", "10"), ("11", "20"), ("21", "30"), ("31", None)),
         unit="kg"),
    Axis("age", "馬齢",
         "CASE WHEN s.age BETWEEN 2 AND 9 THEN s.age - 2 WHEN s.age >= 10 THEN 8 END",
         bins=(*_each(range(2, 10)), ("10", None)), unit="歳"),
    # セン を 牡 の隣に置く
    Axis("sex", "性別",
         "CASE s.sex WHEN '牝' THEN 0 WHEN '牡' THEN 1 WHEN 'セン' THEN 2 END",
         names=("牝", "牡", "セン")),
    Axis("moisture", "馬場水分",
         "CASE WHEN ra.moisture < 0 THEN NULL WHEN ra.moisture < 1.0 THEN 0"
         " WHEN ra.moisture < 1.5 THEN 1 WHEN ra.moisture < 2.0 THEN 2"
         " WHEN ra.moisture < 2.5 THEN 3 WHEN ra.moisture < 3.0 THEN 4"
         " WHEN ra.moisture >= 3.0 THEN 5 END",
         bins=((None, "0.9"), ("1.0", "1.4"), ("1.5", "1.9"), ("2.0", "2.4"),
               ("2.5", "2.9"), ("3.0", None))),
    Axis("weather", "天候",
         "CASE WHEN ra.weather = '晴' THEN 0 WHEN ra.weather = '曇' THEN 1"
         " WHEN ra.weather IN ('小雨', '雨', '小雪', '雪') THEN 2 END",
         names=("晴", "曇", "雨・雪")),
    # シーズン順（4 月 = 0 … 3 月 = 11）。3 月と 4 月は隣ではない
    Axis("month", "月",
         "(CAST(substr(s.race_date, 6, 2) AS INTEGER) + 8) % 12",
         bins=_each([*range(4, 13), 1, 2, 3]), unit="月"),
)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def today_jst() -> dt.date:
    return _now().astimezone(JST).date()


def through_season(today: dt.date) -> int:
    """締めたシーズンのうち最新のもの。Y 年 5/1 からは Y-1 シーズン（Y-1/4/1〜Y/3/31）まで。"""
    return today.year - 1 if today.month >= CLOSE_MONTH else today.year - 2


def band_of(season: int) -> int:
    """期間帯。FIRST_RECENT_SEASON より前は 1 つにまとめ、以後は 1 シーズンずつ。"""
    return max(season, FIRST_RECENT_SEASON - 1)


# 対象の出走: 取消・除外を除く（中止・失格は馬券が外れ扱いなので含める）。
# 複勝の払戻が無いレースは複勝の指標が定義できないので除く（3〜4 頭立ての数レース）。
# 重量差はこの範囲（取消・除外を除いた出走馬）の中で最も軽い馬との差。
_STARTERS = """
WITH s AS (
  SELECT r.*,
         CAST(substr(r.race_date, 1, 4) AS INTEGER)
           - (CAST(substr(r.race_date, 6, 2) AS INTEGER) < 4) AS season,
         r.weight_carried - MIN(r.weight_carried)
           OVER (PARTITION BY r.race_date, r.race_no) AS wd
  FROM results r
  WHERE COALESCE(r.status, '') NOT IN ('取消', '除外')
    AND r.race_date < :end
    AND EXISTS (SELECT 1 FROM payouts p
                WHERE p.race_date = r.race_date AND p.race_no = r.race_no
                  AND p.bet_type = '複勝')
)
"""


def _end(through: int) -> str:
    return f"{through + 1}-{SEASON_START_MONTH:02d}-01"


def population(con: sqlite3.Connection, through: int) -> dict[int, int]:
    """シーズンごとの対象出走数。軸の値に関係なく数える（検査 2 の基準）。"""
    rows = con.execute(_STARTERS + "SELECT season, COUNT(*) FROM s GROUP BY season",
                       {"end": _end(through)})
    return dict(rows.fetchall())


def load_cells(con: sqlite3.Connection, through: int) -> dict[tuple[int, ...], list[int]]:
    """(シーズン, 各軸の基本区分…) → 集計値 [N, WIN, TOP2, PLACE, WIN_PAY, PLACE_PAY]。

    軸の値が想定外（NULL）の出走は入れない。黙って別の区分に入れると集計が歪むので、
    検査 2（マスの合計 = 対象出走数）で止める。
    """
    axis_cols = ", ".join(f"{a.sql} AS {a.key}" for a in AXES)
    sql = _STARTERS + f"""
    SELECT s.season, {axis_cols},
           COALESCE(s.finish = 1, 0), COALESCE(s.finish <= 2, 0),
           pp.amount IS NOT NULL, COALESCE(pw.amount, 0), COALESCE(pp.amount, 0)
    FROM s
    JOIN races ra ON ra.race_date = s.race_date AND ra.race_no = s.race_no
    LEFT JOIN payouts pw ON pw.race_date = s.race_date AND pw.race_no = s.race_no
         AND pw.bet_type = '単勝' AND CAST(pw.combination AS INTEGER) = s.horse_no
    LEFT JOIN payouts pp ON pp.race_date = s.race_date AND pp.race_no = s.race_no
         AND pp.bet_type = '複勝' AND CAST(pp.combination AS INTEGER) = s.horse_no
    """
    cells: dict[tuple[int, ...], list[int]] = {}
    k = len(AXES)
    for row in con.execute(sql, {"end": _end(through)}):
        season, idx, values = row[0], row[1:1 + k], row[1 + k:]
        if any(v is None for v in idx):
            continue
        acc = cells.setdefault((season, *idx), [0] * 6)
        acc[N] += 1
        for i, v in enumerate(values, start=WIN):
            acc[i] += v
    return cells


# 1 軸 8 表 + 2 軸 28 表
TABLES: tuple[tuple[Axis, ...], ...] = (
    *((a,) for a in AXES),
    *itertools.combinations(AXES, 2),
)


def table_name(axes: tuple[Axis, ...]) -> str:
    return "explore/" + "__".join(a.key for a in axes)


def _add(acc: list[int], m: list[int]) -> None:
    for i, v in enumerate(m):
        acc[i] += v


def _metrics(m: list[int]) -> dict:
    n = m[N]
    return {
        "n": n,
        "win_rate": round(100 * m[WIN] / n, 1),
        "top2_rate": round(100 * m[TOP2] / n, 1),
        "place_rate": round(100 * m[PLACE] / n, 1),
        # 払戻は 100 円あたりなので、払戻合計 ÷ (n × 100 円) × 100% = 払戻合計 ÷ n
        "win_roi": round(m[WIN_PAY] / n, 1),
        "place_roi": round(m[PLACE_PAY] / n, 1),
    }


def _period_payload(axes, groups, merged, lo: int, hi: int) -> dict:
    total = [0] * 6
    for m in merged.values():
        _add(total, m)
    out = {
        "first_season": lo,
        "last_season": hi,
        "total": _metrics(total) if total[N] else None,
        # 0 件のマスは入れない（画面では「—」）
        "cells": [
            {**{a.key: a.label(groups[i][key[i]]) for i, a in enumerate(axes)}, **_metrics(m)}
            for key, m in sorted(merged.items())
        ],
    }
    if len(axes) == 2:
        # 全体の行と列。まとめた区分でのマスの合計なので、新たな数字は出ない
        out["margins"] = {}
        for i, a in enumerate(axes):
            side: dict[int, list[int]] = {}
            for key, m in merged.items():
                _add(side.setdefault(key[i], [0] * 6), m)
            out["margins"][a.key] = [
                {a.key: a.label(groups[i][g]), **_metrics(m)} for g, m in sorted(side.items())]
    return out


def build_table(
    axes: tuple[Axis, ...],
    base: dict[tuple[int, ...], list[int]],
    pop: dict[int, int],
    through: int,
) -> tuple[dict, list[str]]:
    """1 つの表を作る。戻り値は (JSON にする中身, 検査 1・2 の違反)。

    区分をまとめ切れない（ある期間帯の合計そのものが 30 件未満）ときは ValueError。
    """
    name = table_name(axes)
    pos = [AXES.index(a) for a in axes]
    by_season: dict[int, dict[tuple[int, ...], list[int]]] = {}
    for (season, *idx), m in base.items():
        key = tuple(idx[p] for p in pos)
        _add(by_season.setdefault(season, {}).setdefault(key, [0] * 6), m)

    # まとめ方は期間帯ごとの出走数で決め、両方の期間で同じものを使う
    bands = sorted({band_of(s) for s in pop})
    counts: dict[tuple[int, ...], list[int]] = {}
    for season, cells in by_season.items():
        b = bands.index(band_of(season))
        for key, m in cells.items():
            counts.setdefault(key, [0] * len(bands))[b] += m[N]
    groups = merge_bins(counts, [a.n_bins for a in axes], floor=MIN_GROUP_SIZE)

    # 検査 1: まとめた後、どの期間帯でも全マスが 0 か 30 以上
    problems = [
        f"{name}: 期間帯 {bands[b]} のマス {key} が {n} 件（0 か {MIN_GROUP_SIZE} 以上が必要）"
        for n, b, key in violations(regroup(counts, groups), MIN_GROUP_SIZE)
    ]

    spans = {"all": (min(pop), through), "recent3": (through - RECENT_SEASONS + 1, through)}
    periods = {}
    for period, (lo, hi) in spans.items():
        summed: dict[tuple[int, ...], list[int]] = {}
        for season, cells in by_season.items():
            if lo <= season <= hi:
                for key, m in cells.items():
                    _add(summed.setdefault(key, [0] * 6), m)
        merged = regroup(summed, groups)
        # 検査 2: マスの合計が対象出走数と一致する（もれなく分けている）
        expected = sum(n for s, n in pop.items() if lo <= s <= hi)
        got = sum(m[N] for m in merged.values())
        if got != expected:
            problems.append(f"{name}（{period}）: マスの合計 {got} が対象出走数 {expected} と"
                            "一致しない（軸の値が想定外の出走がある）")
        periods[period] = _period_payload(axes, groups, merged, lo, hi)

    payload = {
        "axes": [a.key for a in axes],
        "through_season": through,
        "bins": {a.key: [a.label(g) for g in groups[i]] for i, a in enumerate(axes)},
        "periods": periods,
    }
    return payload, problems


def build(con: sqlite3.Connection, today: dt.date) -> tuple[dict[str, dict], list[str]]:
    """全表を作る。戻り値は ({出力名: 中身}, 違反の一覧)。

    締めたシーズンの出走が 1 件も無ければ何も作らない（テスト用の小さな DB など）。
    """
    through = through_season(today)
    if through - RECENT_SEASONS + 1 < FIRST_RECENT_SEASON:
        return {}, [f"直近 {RECENT_SEASONS} シーズンが {FIRST_RECENT_SEASON} より前から始まる"
                    f"（締め {through}）。FIRST_RECENT_SEASON の設定か日付が誤っている"]
    pop = population(con, through)
    if not pop:
        return {}, []
    base = load_cells(con, through)
    out: dict[str, dict] = {}
    problems: list[str] = []
    for axes in TABLES:
        name = table_name(axes)
        try:
            payload, found = build_table(axes, base, pop, through)
        except ValueError as e:
            problems.append(f"{name}: {e}")
            continue
        out[name] = payload
        problems += found
    return out, problems


def flatten(payload: dict) -> list[dict]:
    """公開ポリシーの検査（aggregates.policy_violations）にかける行。マス・全体の行と列・合計。"""
    rows: list[dict] = []
    for p in payload["periods"].values():
        rows += p["cells"]
        for side in p.get("margins", {}).values():
            rows += side
        if p["total"] is not None:
            rows.append(p["total"])
    return rows


def previous_problems(name: str, payload: dict, previous_dir: Path) -> list[str]:
    """検査 3: 締めたシーズンが同じなのに、前回の出力と内容が違えば違反。

    締めたシーズンのデータが後から変わった（修正・取りこぼしの補完）ことを意味する。
    その差は小さな集計の漏れになるので、人が判断するまで公開しない（CLAUDE.md の手順）。
    前回の出力が無い（初回）・締めが進んだ場合は通す。読めない・締めが戻った場合は止める。
    """
    path = previous_dir / f"{name}.json"
    if not path.exists():
        return []
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
        prev_through = prev["through_season"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        return [f"{name}: 前回の出力を読めない（{e!r}）。中身を確かめるまで上書きしない"]
    through = payload["through_season"]
    if through < prev_through:
        return [f"{name}: 締めが {prev_through} から {through} に戻っている"]
    if through == prev_through and prev != payload:
        return [f"{name}: 締めたシーズン（{through} まで）が同じなのに内容が変わった。"
                "過去のデータが修正・補完された可能性がある"]
    return []
