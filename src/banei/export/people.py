"""騎手・調教師ページの集計。

設計: docs/superpowers/specs/2026-10-14-people-pages-design.md

- 対象の出走・締め・指標の定義は探索 UI と同じ（explore.py のものを使う）。定義が 2 か所に
  分かれると、探索 UI と人のページの数字が食い違う
- 単位は 役割（騎手・調教師）× DB の略称 × シーズン。2007 シーズンから 1 シーズンずつ載せる。
  最初の版で締めたシーズンまでを一度に出すので、版の差で切り出されるのは新しいシーズンだけ
- 30 件未満の人・シーズンは消さずに「その他」にまとめる（pooled）。消すと、シーズンの合計からの
  引き算で値が割り出せる
- 平均人気と見込み勝ち数は、人気別の出走数（10 個）の重み付き合計。この種の値を増やすと人気別の
  内訳が連立方程式で割り出せるようになるので、2 つより増やさない
"""

import sqlite3
from dataclasses import dataclass

from banei.export import explore
from banei.export.explore import WIN, N

ROLES = ("jockey", "trainer")
ROLE_NAMES = {"jockey": "騎手", "trainer": "調教師"}

# 1 欄の集計値: explore と同じ [N, WIN, TOP2, PLACE, WIN_PAY, PLACE_PAY] に続けて、人気 1〜10 の
# 出走数。すべて整数で持つ（足し合わせても誤差が出ず、毎回同じ値になる。検査 3 の前提）
POPULARITIES = range(1, 11)
POP = 6
WIDTH = POP + len(POPULARITIES)

Cells = dict[tuple[int, str], list[int]]  # (シーズン, 略称) → 集計値


@dataclass(frozen=True)
class Loaded:
    roles: dict[str, Cells]  # 役割 → (シーズン, 略称) → 集計値
    seasons: dict[int, list[int]]  # シーズン → そのシーズン全体の集計値
    rates: dict[int, list[float]]  # シーズン → 人気 1〜10 の勝率（見込み勝ち数の重み）


def _add(acc: list[int], m: list[int]) -> None:
    for i, v in enumerate(m):
        acc[i] += v


def load(con: sqlite3.Connection, through: int) -> Loaded:
    """締めたシーズン（through まで）の出走を、役割・略称・シーズンごとに集計する。

    人気が 1〜10 以外の出走と、略称が空の出走は入れない。母数（explore.population）には
    入るので、検査 2（欄の合計 = 対象出走数）で止まる。黙って除くと集計が歪む。
    """
    sql = explore.STARTERS + f"""
    SELECT s.season, s.jockey, s.trainer, s.popularity, {explore.RUN_VALUES}
    FROM s
    {explore.PAYOUTS}
    """
    roles: dict[str, Cells] = {role: {} for role in ROLES}
    seasons: dict[int, list[int]] = {}
    wins: dict[int, list[int]] = {}  # シーズン → 人気 1〜10 の勝ち数
    for season, jockey, trainer, popularity, *values in con.execute(
            sql, {"end": explore.season_end(through)}):
        if popularity not in POPULARITIES:
            continue
        run = [1, *values, *([0] * len(POPULARITIES))]
        run[POP + popularity - 1] = 1
        _add(seasons.setdefault(season, [0] * WIDTH), run)
        wins.setdefault(season, [0] * len(POPULARITIES))[popularity - 1] += run[WIN]
        for role, key in zip(ROLES, (jockey, trainer), strict=True):
            if key:
                _add(roles[role].setdefault((season, key), [0] * WIDTH), run)
    rates = {
        season: [w / n if n else 0.0 for w, n in zip(wins[season], m[POP:], strict=True)]
        for season, m in seasons.items()
    }
    return Loaded(roles, seasons, rates)


def expected(m: list[int], rates: list[float]) -> float:
    """見込み勝ち数。人気ごとの出走数 × そのシーズン全体のその人気の勝率 の合計。"""
    return sum(m[POP + i] * r for i, r in enumerate(rates))


def metrics(m: list[int], exp: float) -> dict:
    """1 欄の指標。率と回収率は探索 UI と同じ。

    見込みとの差は、表に出す見込み勝ち数（丸めた値）から出す。
    """
    e = round(exp, 1)
    return {
        **explore.metrics(m),
        "wins": m[WIN],
        "avg_popularity": round(sum(p * m[POP + p - 1] for p in POPULARITIES) / m[N], 2),
        "expected_wins": e,
        "wins_over_expected": round(m[WIN] - e, 1),
    }
