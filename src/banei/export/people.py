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

import datetime as dt
import json
import sqlite3
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from banei.export import explore
from banei.export.aggregates import MIN_GROUP_SIZE
from banei.export.explore import WIN, N

ROLES = ("jockey", "trainer")
ROLE_NAMES = {"jockey": "騎手", "trainer": "調教師"}
NAMES_PATH = Path(__file__).with_name("people.toml")
OUTPUT = "people"  # 出力名（web/src/data/people.json）
NAME_FIELDS = frozenset({"name", "jockey", "trainer", "source"})

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


@dataclass(frozen=True)
class Person:
    """対応表の 1 行。jockey / trainer は DB の略称（その役割でなければ None）。"""

    name: str
    jockey: str | None
    trainer: str | None

    def keys(self) -> dict[str, str]:
        return {role: key for role, key in zip(ROLES, (self.jockey, self.trainer), strict=True)
                if key}


def load_names(path: Path) -> tuple[list[Person], list[str]]:
    """対応表を読む。戻り値は (人, 違反)。違反があると表示が誤るので export を止める。

    出典（source）の無い行は受け付けない。確かめていない名前を推測で入れないため。
    """
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        return [], [f"people.toml を読めない（{e!r}）"]
    rows = data.get("person", [])
    if not isinstance(rows, list):
        return [], ["people.toml: [[person]] の並びになっていない"]
    out: list[Person] = []
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for i, row in enumerate(rows, start=1):
        where = f"people.toml の {i} 人目"
        if not isinstance(row, dict) or set(row) - NAME_FIELDS:
            problems.append(f"{where}: 使えるキーは {sorted(NAME_FIELDS)} だけ")
            continue
        if not all(isinstance(v, str) and v.strip() for v in row.values()):
            problems.append(f"{where}: 値は空でない文字列にする")
            continue
        if not {"name", "source"} <= set(row) or not {"jockey", "trainer"} & set(row):
            problems.append(f"{where}: name と source、jockey か trainer の少なくとも一方が要る")
            continue
        person = Person(row["name"], row.get("jockey"), row.get("trainer"))
        for role, key in person.keys().items():
            if (role, key) in seen:
                problems.append(
                    f"people.toml: {ROLE_NAMES[role]}の略称「{key}」が二重に登録されている")
            seen.add((role, key))
        out.append(person)
    return out, problems


def slug_of(key: str) -> str:
    """URL の名前。DB の略称から空白（全角を含む）を除いたもの。対応表を直しても変わらない。"""
    return "".join(key.split())


def build_pages(
    roles: dict, names: list[Person], through: int
) -> tuple[list[dict], list[str], list[str]]:
    """表示用のページの一覧。戻り値は (ページ, 違反, 警告)。

    対応表の人は 1 人 1 ページ（騎手と調教師を兼ねた人もまとめる）。表に無い略称は略称のまま
    ページにして警告する（5/1 に新人が出ても export を止めない）。騎手と調教師で同じ略称が
    表に無ければ同じ人として 1 ページにする（既知の兼任 8 人はすべてそう）。
    現役（active）は、最新の締めたシーズンに出走がある（「その他」にまとめた場合も含む）こと。
    """
    present = {role: {p["key"]: p for p in roles[role]["people"]} for role in ROLES}

    def ran_in(role: str, key: str) -> bool:
        p = present[role][key]
        return through in p["pooled_seasons"] or any(s["season"] == through for s in p["seasons"])

    def page(name: str, confirmed: bool, keys: dict[str, str]) -> dict:
        return {
            "slug": slug_of(keys.get("jockey") or keys["trainer"]),
            "name": name,
            "name_confirmed": confirmed,
            "jockey": keys.get("jockey"),
            "trainer": keys.get("trainer"),
            "active": any(ran_in(role, key) for role, key in keys.items()),
        }

    pages: list[dict] = []
    claimed: set[tuple[str, str]] = set()
    for person in names:
        keys = {role: key for role, key in person.keys().items() if key in present[role]}
        if keys:
            claimed |= set(keys.items())
            pages.append(page(person.name, True, keys))
    unlisted: dict[str, dict[str, str]] = {}
    for role in ROLES:
        for key in present[role]:
            if (role, key) not in claimed:
                unlisted.setdefault(key, {})[role] = key
    warnings = [
        f"対応表に無い略称「{key}」（{'・'.join(ROLE_NAMES[r] for r in keys)}）。"
        "略称のままページを作る"
        for key, keys in sorted(unlisted.items())
    ]
    pages += [page(key, False, keys) for key, keys in sorted(unlisted.items())]
    pages.sort(key=lambda p: p["slug"])
    problems = [
        f"people: URL「/people/{slug}/」が重複する。同一人物なら対応表で 1 行にまとめる"
        for slug, n in sorted(Counter(p["slug"] for p in pages).items()) if n > 1
    ]
    return pages, problems, warnings


def _plain(obj):
    """JSON に書いて読み戻したもの。前回の出力（JSON から読んだもの）と同じ形で比べるため。"""
    return json.loads(json.dumps(obj, ensure_ascii=False))


def _previous(previous_dir: Path | None) -> tuple[dict | None, list[str]]:
    """前回の出力。無ければ（初回）None。読めない・形が想定外なら、上書きせず止めるため違反にする。"""
    if previous_dir is None:
        return None, []
    path = previous_dir / f"{OUTPUT}.json"
    if not path.exists():
        return None, []
    unreadable = f"{OUTPUT}: 前回の出力を読めない（{{}}）。中身を確かめるまで上書きしない"
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
        through, roles = prev["through_season"], prev["roles"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        return None, [unreadable.format(repr(e))]
    if type(through) is not int:
        return None, [unreadable.format(f"締め {through!r} が整数でない")]
    if not isinstance(roles, dict):
        return None, [unreadable.format("roles が辞書でない")]
    return prev, []


def _history_problems(
    con: sqlite3.Connection, roles: dict, through: int, prev: dict
) -> list[str]:
    """検査 3: 締めたシーズンの集計（roles）が前回の出力から変わっていない。

    締めが同じなら roles が同じこと。締めが進んだときも、今の DB から前回の締めで作り直して
    前回と比べる（止めて調べている最中に 5/1 が来ても、保留中の修正が素通りしない）。
    変わっていれば修正・補完があったということで、その差は小さな集計の漏れになる。
    表示（pages）は比べない。対応表の修正で止めないため。
    """
    prev_through = prev["through_season"]
    if prev_through > through:
        return [f"{OUTPUT}: 締めが {prev_through} から {through} に戻っている"]
    if prev_through == through:
        if _plain(roles) != prev["roles"]:
            return [f"{OUTPUT}: 締めたシーズン（{through} まで）が同じなのに内容が変わった。"
                    "過去のデータが修正・補完された可能性がある"]
        return []
    again, _ = build_roles(con, prev_through)
    if again is None or _plain(again) != prev["roles"]:
        return [f"{OUTPUT}: 締めたシーズン（{prev_through} まで）の内容が前回の出力と違う。"
                "過去のデータが修正・補完された可能性がある"]
    return []


def build(
    con: sqlite3.Connection,
    today: dt.date,
    previous_dir: Path | None = None,
    names_path: Path | None = None,
) -> tuple[dict | None, list[str], list[str]]:
    """人のページの JSON を作る。戻り値は (中身, 違反, 警告)。

    締めたシーズンの出走が無ければ中身は None。previous_dir に前回の出力があれば検査 3。
    names_path を省くと NAMES_PATH（呼ぶときに読むので、テストは monkeypatch で差し替えられる）。
    """
    through = explore.through_season(today)
    roles, problems = build_roles(con, through)
    if roles is None:
        return None, problems, []
    prev, found = _previous(previous_dir)
    problems += found
    if prev is not None:
        problems += _history_problems(con, roles, through, prev)
    names, found = load_names(names_path or NAMES_PATH)
    problems += found
    pages, found, warnings = build_pages(roles, names, through)
    problems += found
    return {"through_season": through, "roles": roles, "pages": pages}, problems, warnings
