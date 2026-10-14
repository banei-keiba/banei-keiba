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
from banei.export.aggregates import MIN_GROUP_SIZE
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


def pooled(counts: dict[str, int]) -> set[str]:
    """1 シーズン分の {略称: 出走数} から「その他」にまとめる略称。

    30 件未満の人を入れ、「その他」が 1〜29 件なら、残りで出走数の最も少ない人（同数なら略称の順）を
    30 件以上になるまで移す。シーズン全体が 30 件以上なら、空でない「その他」は必ず 2 人以上になる
    （1 人だとその人の値が出る）。全体が 30 件未満なら全員を入れても届かないが、そのまま返す
    （公開ポリシーの検査で止まる）。
    """
    pool = {k for k, n in counts.items() if n < MIN_GROUP_SIZE}
    while 0 < sum(counts[k] for k in pool) < MIN_GROUP_SIZE:
        rest = [k for k in counts if k not in pool]
        if not rest:
            break
        pool.add(min(rest, key=lambda k: (counts[k], k)))
    return pool


def build_role(cells: Cells, data: Loaded) -> dict:
    """1 つの役割の JSON。シーズンごとの全体と「その他」、人ごとのシーズンの欄と通算。

    まとめ方はシーズンごとに独立に決める。締めたシーズンの顔ぶれは、データが変わらない限り
    後から変わらない。通算は個人の欄に載せたシーズンだけの合計（まとめたシーズンを含めると、
    通算から個人の欄を引いて「その他」にまとめた値が出る）。
    """
    by_season: dict[int, dict[str, list[int]]] = {}
    for (season, key), m in cells.items():
        by_season.setdefault(season, {})[key] = m
    seasons_out = []
    acc: dict[str, dict] = {}
    for season in sorted(data.seasons):
        rates = data.rates[season]
        here = by_season.get(season, {})
        pool = pooled({k: m[N] for k, m in here.items()})
        other = [0] * WIDTH
        for k in pool:
            _add(other, here[k])
        total = data.seasons[season]
        seasons_out.append({
            "season": season,
            "total": metrics(total, expected(total, rates)),
            "other": ({"people_count": len(pool), **metrics(other, expected(other, rates))}
                      if pool else None),
        })
        for key in sorted(here):
            p = acc.setdefault(key, {"seasons": [], "pooled_seasons": [],
                                     "sum": [0] * WIDTH, "expected": 0.0})
            if key in pool:
                p["pooled_seasons"].append(season)
                continue
            e = expected(here[key], rates)
            p["seasons"].append({"season": season, **metrics(here[key], e)})
            _add(p["sum"], here[key])
            p["expected"] += e
    people_out = []
    for key in sorted(acc):
        p = acc[key]
        career = None
        if p["seasons"]:
            career = {"first_season": p["seasons"][0]["season"],
                      "last_season": p["seasons"][-1]["season"],
                      **metrics(p["sum"], p["expected"])}
        people_out.append({"key": key, "seasons": p["seasons"],
                           "pooled_seasons": p["pooled_seasons"], "career": career})
    return {"seasons": seasons_out, "people": people_out}


def completeness(role: str, cells: Cells, population: dict[int, int]) -> list[str]:
    """検査 2: シーズンごとに、欄の出走数の合計が対象出走数と一致する（もれなく分けている）。"""
    got: dict[int, int] = {}
    for (season, _), m in cells.items():
        got[season] = got.get(season, 0) + m[N]
    name = ROLE_NAMES[role]
    return [
        f"people（{name}）: {season} シーズンの欄の合計 {got.get(season, 0)} が対象出走数 {n} と"
        f"一致しない（人気が 1〜10 以外か、{name}の無い出走がある）"
        for season, n in sorted(population.items()) if got.get(season, 0) != n
    ]


def build_roles(con: sqlite3.Connection, through: int) -> tuple[dict | None, list[str]]:
    """締めたシーズン（through まで）の集計。戻り値は (役割 → JSON, 検査 2 の違反)。

    締めたシーズンの出走が 1 件も無ければ (None, [])（テスト用の小さな DB など。探索 UI と同じ）。
    """
    population = explore.population(con, through)
    if not population:
        return None, []
    data = load(con, through)
    problems: list[str] = []
    roles = {}
    for role in ROLES:
        problems += completeness(role, data.roles[role], population)
        roles[role] = build_role(data.roles[role], data)
    return roles, problems


def flatten(payload: dict) -> list[dict]:
    """公開ポリシーの検査（aggregates.policy_violations）にかける行。roles の全行。"""
    rows: list[dict] = []
    for role in payload["roles"].values():
        for s in role["seasons"]:
            rows.append(s["total"])
            if s["other"] is not None:
                rows.append(s["other"])
        for p in role["people"]:
            rows += p["seasons"]
            if p["career"] is not None:
                rows.append(p["career"])
    return rows
