"""騎手・調教師ページの集計（people.py）のテスト。合成データのみ（実データ・実ページは使わない）。"""

import datetime as dt
import json
import random
import sqlite3

import pytest

from banei import export
from banei.db.schema import RACES_SCHEMA
from banei.export import explore, people
from banei.export.aggregates import MIN_GROUP_SIZE, policy_violations

SEASON_2025 = "2025-06-01"  # 2025 シーズン（2025-04-01〜2026-03-31）
TODAY = dt.date(2026, 10, 14)  # 2025 シーズンまで締めている


def run(no, finish=None, status=None, popularity=None, jockey="騎手A", trainer="調教師甲"):
    """出走 1 頭。status を省くと着順の数字を入れる（実データと同じ）。人気を省くと馬番と同じ。"""
    return {"no": no, "finish": finish, "status": status or str(finish),
            "popularity": popularity or no, "jockey": jockey, "trainer": trainer}


def add_race(con, date, race_no, runs, win=None, place=None):
    """1 レースを足す。win / place は {馬番: 払戻}。place が空ならそのレースは複勝の払戻なし。"""
    con.execute("INSERT INTO races VALUES (?,?,?,?,?,?,?)",
                (date, race_no, "テスト", 200, "晴", 1.2, "条件"))
    for r in runs:
        con.execute(
            "INSERT INTO results (race_date,race_no,horse_no,finish,status,horse_name,sex,age,"
            "weight_carried,popularity,jockey,trainer) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (date, race_no, r["no"], r["finish"], r["status"], f"馬{r['no']}", "牡", 5, 700,
             r["popularity"], r["jockey"], r["trainer"]))
    for bet, pays in (("単勝", win or {}), ("複勝", place or {})):
        for no, amount in pays.items():
            con.execute("INSERT INTO payouts VALUES (?,?,?,?,?,NULL)",
                        (date, race_no, bet, str(no), amount))


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "banei.db"


@pytest.fixture
def con(db_path):
    # export.build は別の接続で開くので、書いたらすぐ見えるよう autocommit にする
    c = sqlite3.connect(db_path, isolation_level=None)
    c.execute("PRAGMA synchronous = OFF")
    c.executescript(RACES_SCHEMA)
    yield c
    c.close()


def add_two_races(con):
    """手で数えられる 2 レース（2025 シーズン）。

    1 レース目: 1 番人気（騎手A・調教師甲）が勝ち、2 番人気（騎手B・甲）2 着、3 番人気（騎手A・乙）
      3 着。3 頭立てなので複勝は 2 着まで
    2 レース目: 2 番人気（騎手A・甲）が勝ち、1 番人気（騎手B・乙）2 着、3 番人気（騎手B・乙）中止、
      4 番人気（騎手A・甲）取消
    """
    add_race(con, SEASON_2025, 1,
             [run(1, 1, jockey="騎手A", trainer="調教師甲"),
              run(2, 2, jockey="騎手B", trainer="調教師甲"),
              run(3, 3, jockey="騎手A", trainer="調教師乙")],
             win={1: 200}, place={1: 110, 2: 130})
    add_race(con, "2025-06-02", 1,
             [run(1, 2, popularity=1, jockey="騎手B", trainer="調教師乙"),
              run(2, 1, popularity=2, jockey="騎手A", trainer="調教師甲"),
              run(3, status="中止", popularity=3, jockey="騎手B", trainer="調教師乙"),
              run(4, status="取消", popularity=4, jockey="騎手A", trainer="調教師甲")],
             win={2: 450}, place={2: 160, 1: 120})


class TestLoad:
    def test_cells_by_role_and_key(self, con):
        add_two_races(con)
        data = people.load(con, 2025)
        # [N, WIN, TOP2, PLACE, WIN_PAY, PLACE_PAY] + 人気 1〜10 の出走数
        assert data.roles["jockey"][(2025, "騎手A")] == [
            3, 2, 2, 2, 650, 270, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
        # 中止は出走に入り、外れとして数える。取消は入らない
        assert data.roles["jockey"][(2025, "騎手B")] == [
            3, 0, 2, 2, 0, 250, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
        assert data.roles["trainer"][(2025, "調教師甲")][:6] == [3, 2, 3, 3, 650, 400]
        assert data.seasons[2025][:6] == [6, 2, 4, 4, 650, 520]

    def test_rates_are_season_win_rates_by_popularity(self, con):
        add_two_races(con)
        assert people.load(con, 2025).rates[2025][:4] == [0.5, 0.5, 0.0, 0.0]

    def test_dead_heat_counts_both_winners(self, con):
        add_race(con, SEASON_2025, 1, [run(1, 1), run(2, 1), run(3, 3, jockey="騎手B")],
                 win={1: 150, 2: 260}, place={1: 110, 2: 130})
        data = people.load(con, 2025)
        assert data.roles["jockey"][(2025, "騎手A")][:5] == [2, 2, 2, 2, 410]
        assert data.rates[2025][:2] == [1.0, 1.0]

    def test_unclosed_season_and_races_without_place_payouts_are_excluded(self, con):
        add_race(con, "2026-04-01", 1, [run(1, 1)], win={1: 100}, place={1: 100})
        add_race(con, SEASON_2025, 1, [run(1, 1), run(2, 2)], win={1: 140}, place={})
        data = people.load(con, 2025)
        assert data.roles == {"jockey": {}, "trainer": {}} and data.seasons == {}


class TestMetrics:
    def test_hand_counted_values(self, con):
        add_two_races(con)
        data = people.load(con, 2025)
        rates = data.rates[2025]
        a = data.roles["jockey"][(2025, "騎手A")]
        # 見込み = 人気 1（勝率 0.5）+ 人気 2（0.5）+ 人気 3（0）= 1.0
        assert people.metrics(a, people.expected(a, rates)) == {
            "n": 3, "win_rate": 66.7, "top2_rate": 66.7, "place_rate": 66.7,
            "win_roi": 216.7, "place_roi": 90.0, "wins": 2,
            "avg_popularity": 2.0, "expected_wins": 1.0, "wins_over_expected": 1.0,
        }
        b = data.roles["jockey"][(2025, "騎手B")]
        assert people.metrics(b, people.expected(b, rates))["wins_over_expected"] == -1.0
        t = data.roles["trainer"][(2025, "調教師甲")]  # 人気 1・2・2 で 2 勝
        m = people.metrics(t, people.expected(t, rates))
        assert (m["avg_popularity"], m["expected_wins"], m["wins_over_expected"]) == (
            1.67, 1.5, 0.5)


def vec(n, wins=0, popularity=1):
    """1 欄の集計値。n 出走がすべて同じ人気で、wins 回勝った。"""
    m = [0] * people.WIDTH
    m[explore.N], m[explore.WIN] = n, wins
    m[people.POP + popularity - 1] = n
    return m


def loaded(cells):
    """騎手の欄だけの Loaded。シーズン全体はその合計、人気 1 の勝率は 0.1 とする。"""
    seasons = {}
    for (season, _), m in cells.items():
        acc = seasons.setdefault(season, [0] * people.WIDTH)
        for i, v in enumerate(m):
            acc[i] += v
    rates = {s: [0.1] + [0.0] * 9 for s in seasons}
    return people.Loaded(roles={"jockey": cells, "trainer": {}}, seasons=seasons, rates=rates)


class TestPooled:
    @pytest.mark.parametrize(("counts", "expected"), [
        ({"A": 100, "B": 40}, set()),
        ({"A": 100, "B": 20, "C": 15}, {"B", "C"}),  # 35 件で足りる
        ({"A": 100, "B": 40, "C": 10}, {"B", "C"}),  # 10 件では足りず、少ない B を移す
        ({"A": 50, "B": 50, "C": 5}, {"A", "C"}),  # 同数なら略称の順
        ({"A": 10}, {"A"}),  # シーズン全体が 30 件未満（公開ポリシーの検査で止まる）
        ({}, set()),
    ])
    def test_pooled(self, counts, expected):
        assert people.pooled(counts) == expected

    def test_pool_is_never_a_single_person(self):
        # 1 人だけだと「その他」の値がその人の値になる
        rng = random.Random(0)
        for _ in range(500):
            counts = {f"P{i}": rng.choice([rng.randint(1, 29), rng.randint(30, 300)])
                      for i in range(rng.randint(1, 8))}
            if sum(counts.values()) < MIN_GROUP_SIZE:
                continue
            pool = people.pooled(counts)
            assert not pool or (len(pool) >= 2
                                and sum(counts[k] for k in pool) >= MIN_GROUP_SIZE)
            assert all(counts[k] >= MIN_GROUP_SIZE for k in counts if k not in pool)


class TestBuildRole:
    CELLS = {(2024, "A"): vec(40, 4), (2024, "B"): vec(5),
             (2025, "A"): vec(50, 5), (2025, "B"): vec(60, 6)}

    def test_small_season_goes_to_other_with_the_smallest_neighbour(self):
        data = loaded(self.CELLS)
        role = people.build_role(data.roles["jockey"], data)
        s2024, s2025 = role["seasons"]
        assert (s2024["season"], s2024["total"]["n"]) == (2024, 45)
        assert (s2024["other"]["people_count"], s2024["other"]["n"]) == (2, 45)
        assert s2025["other"] is None and s2025["total"]["n"] == 110
        a, b = role["people"]
        assert (a["key"], a["pooled_seasons"]) == ("A", [2024])
        assert [s["season"] for s in a["seasons"]] == [2025]
        assert (b["key"], b["pooled_seasons"]) == ("B", [2024])

    def test_career_excludes_pooled_seasons(self):
        # 入れると、通算から個人のシーズンを引いて「その他」にまとめた値が出る
        data = loaded(self.CELLS)
        a = people.build_role(data.roles["jockey"], data)["people"][0]
        assert (a["career"]["n"], a["career"]["wins"]) == (50, 5)
        assert (a["career"]["first_season"], a["career"]["last_season"]) == (2025, 2025)
        assert a["career"]["expected_wins"] == 5.0  # 50 出走 × 人気 1 の勝率 0.1

    def test_career_sums_published_seasons(self):
        data = loaded({(2024, "A"): vec(40, 4), (2025, "A"): vec(50, 5)})
        c = people.build_role(data.roles["jockey"], data)["people"][0]["career"]
        assert (c["n"], c["wins"], c["expected_wins"]) == (90, 9, 9.0)
        assert (c["first_season"], c["last_season"]) == (2024, 2025)

    def test_person_with_every_season_pooled_has_no_career(self):
        data = loaded({(2024, "A"): vec(10), (2024, "B"): vec(25)})
        role = people.build_role(data.roles["jockey"], data)
        assert [p["career"] for p in role["people"]] == [None, None]

    def test_pooling_is_decided_per_season(self):
        # 新人はデビューした年だけ「その他」に入り、翌シーズンからは個人の欄に載る
        data = loaded({(2024, "A"): vec(100), (2024, "新人"): vec(10), (2024, "B"): vec(90),
                       (2025, "A"): vec(100), (2025, "新人"): vec(40), (2025, "B"): vec(90)})
        role = people.build_role(data.roles["jockey"], data)
        newbie = next(p for p in role["people"] if p["key"] == "新人")
        assert newbie["pooled_seasons"] == [2024]
        assert [s["season"] for s in newbie["seasons"]] == [2025]


class TestBuildRoles:
    def test_no_closed_seasons_gives_none(self, con):
        add_race(con, "2026-05-10", 1, [run(1, 1), run(2, 2)],
                 win={1: 300}, place={1: 110, 2: 120})
        assert people.build_roles(con, 2025) == (None, [])

    def test_unexpected_popularity_is_reported(self, con):
        add_race(con, SEASON_2025, 1, [run(1, 1), run(2, 2, popularity=11)],
                 win={1: 300}, place={1: 110, 2: 120})
        _, problems = people.build_roles(con, 2025)
        # 騎手・調教師の両方で、欄の合計 1 が対象出走数 2 と合わない
        assert len(problems) == 2 and all("対象出走数 2" in p for p in problems)

    def test_missing_popularity_is_reported(self, con):
        add_race(con, SEASON_2025, 1, [run(1, 1), run(2, 2)],
                 win={1: 300}, place={1: 110, 2: 120})
        con.execute("UPDATE results SET popularity = NULL WHERE horse_no = 2")
        assert len(people.build_roles(con, 2025)[1]) == 2

    def test_missing_jockey_is_reported_for_jockeys_only(self, con):
        add_race(con, SEASON_2025, 1, [run(1, 1), run(2, 2, jockey="")],
                 win={1: 300}, place={1: 110, 2: 120})
        _, problems = people.build_roles(con, 2025)
        assert len(problems) == 1 and "騎手" in problems[0]

    def test_tiny_season_is_a_policy_violation_not_a_crash(self, con):
        # 6 出走しかないシーズンは全員を「その他」にしても 30 件に届かない
        add_two_races(con)
        roles, problems = people.build_roles(con, 2025)
        assert problems == []
        rows = people.flatten({"roles": roles})
        # 役割ごとに シーズン全体 1 +「その他」1。個人の欄と通算は無い
        assert len(rows) == 4
        assert any("下限" in p for p in policy_violations("people", rows))


def write_names(tmp_path, text):
    path = tmp_path / "people.toml"
    path.write_text(text, encoding="utf-8")
    return path


def role_people(spec):
    """build_pages に渡す役割の JSON（使う所だけ）。

    spec は {略称: (個人の欄のシーズン, まとめたシーズン)}。
    """
    return {"seasons": [], "people": [
        {"key": k, "seasons": [{"season": s} for s in pub], "pooled_seasons": list(pool),
         "career": None}
        for k, (pub, pool) in spec.items()]}


class TestNames:
    def test_reads_people(self, tmp_path):
        path = write_names(tmp_path, """
[[person]]
name = "正式名一"
jockey = "正式名"
trainer = "正式名"
source = "https://example.invalid/ (2026-10-14 確認)"
""")
        assert people.load_names(path) == ([people.Person("正式名一", "正式名", "正式名")], [])

    @pytest.mark.parametrize("body", [
        'name = "名"\njockey = "略"',  # 出典が無い（推測で埋めない）
        'name = "名"\nsource = "s"',  # 略称が無い
        'name = ""\njockey = "略"\nsource = "s"',  # 空の名前
        'name = "名"\njokey = "略"\nsource = "s"',  # キーの綴り違い
        'name = "名"\njockey = 1\nsource = "s"',  # 文字列でない
    ])
    def test_rejects_incomplete_rows(self, tmp_path, body):
        names, problems = people.load_names(write_names(tmp_path, f"[[person]]\n{body}\n"))
        assert names == [] and len(problems) == 1

    def test_rejects_duplicate_keys(self, tmp_path):
        path = write_names(tmp_path, """
[[person]]
name = "一"
jockey = "略"
source = "s"
[[person]]
name = "二"
jockey = "略"
source = "s"
""")
        _, problems = people.load_names(path)
        assert len(problems) == 1 and "二重" in problems[0]

    def test_same_key_in_two_roles_is_not_a_duplicate(self, tmp_path):
        path = write_names(
            tmp_path, '[[person]]\nname = "一"\njockey = "略"\ntrainer = "略"\nsource = "s"\n')
        assert people.load_names(path)[1] == []

    @pytest.mark.parametrize("text", ["[[person]\n", "person = 1\n"])
    def test_unreadable_table_is_reported(self, tmp_path, text):
        names, problems = people.load_names(write_names(tmp_path, text))
        assert names == [] and len(problems) == 1 and "people.toml" in problems[0]

    def test_missing_file_is_reported(self, tmp_path):
        assert people.load_names(tmp_path / "none.toml")[1]

    def test_empty_table_is_fine(self, tmp_path):
        assert people.load_names(write_names(tmp_path, "# 空\n")) == ([], [])

    def test_repository_table_is_valid(self):
        # コミットする対応表が読めること（読めないと export が止まる）
        assert people.load_names(people.NAMES_PATH)[1] == []


class TestPages:
    ROLES = {
        "jockey": role_people({"鈴木恵": ([2024, 2025], []), "藤野俊": ([2025], []),
                               "林　豊": ([2010], [])}),
        "trainer": role_people({"藤野俊": ([2025], []), "西弘美": ([2020], [2025])}),
    }

    def build(self, names):
        return people.build_pages(self.ROLES, names, 2025)

    def test_listed_person_gets_one_page_for_both_roles(self):
        pages, problems, warnings = self.build([people.Person("藤野俊介", "藤野俊", "藤野俊")])
        assert problems == []
        assert next(p for p in pages if p["slug"] == "藤野俊") == {
            "slug": "藤野俊", "name": "藤野俊介", "name_confirmed": True,
            "jockey": "藤野俊", "trainer": "藤野俊", "active": True}
        assert not any("藤野俊" in w for w in warnings)

    def test_unlisted_key_gets_a_page_under_the_abbreviation_with_a_warning(self):
        pages, problems, warnings = self.build([])
        assert problems == []
        p = next(p for p in pages if p["slug"] == "鈴木恵")
        assert (p["name"], p["name_confirmed"]) == ("鈴木恵", False)
        assert any("「鈴木恵」" in w for w in warnings)

    def test_unlisted_same_key_in_both_roles_is_one_page(self):
        # 騎手から調教師に移った新人を表に足す前でも、URL が重複して export が止まらない
        pages, problems, warnings = self.build([])
        same = [p for p in pages if p["slug"] == "藤野俊"]
        assert problems == [] and len(same) == 1
        assert (same[0]["jockey"], same[0]["trainer"]) == ("藤野俊", "藤野俊")
        assert sum("「藤野俊」" in w for w in warnings) == 1

    def test_slug_drops_spaces(self):
        pages, _, _ = self.build([])
        assert "林豊" in {p["slug"] for p in pages}

    def test_active_means_ran_in_the_latest_closed_season(self):
        # 西弘美は 2025 に「その他」にまとめられたが、出走はしている
        pages, _, _ = self.build([])
        assert {p["slug"]: p["active"] for p in pages} == {
            "鈴木恵": True, "藤野俊": True, "林豊": False, "西弘美": True}

    def test_pages_are_sorted_by_slug(self):
        pages, _, _ = self.build([])
        assert [p["slug"] for p in pages] == sorted(p["slug"] for p in pages)

    def test_slug_collision_is_reported(self):
        # 表で騎手だけの人とした「藤野俊」と、表に無い調教師「藤野俊」が同じ URL になる
        _, problems, _ = self.build([people.Person("騎手の人", "藤野俊", None)])
        assert len(problems) == 1 and "/people/藤野俊/" in problems[0]

    def test_table_entry_without_data_makes_no_page(self):
        pages, _, _ = self.build([people.Person("未来の新人", "新人", None)])
        assert "新人" not in {p["slug"] for p in pages}

    def test_renaming_changes_only_the_name(self):
        a, _, _ = self.build([people.Person("名前一", "鈴木恵", None)])
        b, _, _ = self.build([people.Person("名前二", "鈴木恵", None)])
        assert [p["slug"] for p in a] == [p["slug"] for p in b]


def add_season(con, season, n_races=40, start_no=1):
    """1 シーズン分。騎手A・B と調教師甲・乙が n_races 回ずつ出走する。"""
    for i in range(n_races):
        add_race(con, f"{season}-05-{i % 28 + 1:02d}", start_no + i // 28,
                 [run(1, 1, jockey="騎手A", trainer="調教師甲"),
                  run(2, 2, jockey="騎手B", trainer="調教師乙")],
                 win={1: 340}, place={1: 120, 2: 150})


def add_extra_race(con, date):
    """騎手A・B が 1 回ずつ出走するレースを 1 つ足す（締めたシーズンの補完の再現などに使う）。"""
    add_race(con, date, 1, [run(1, 1), run(2, 2, jockey="騎手B", trainer="調教師乙")],
             win={1: 340}, place={1: 120, 2: 150})


@pytest.fixture
def big(con):
    for season in (2023, 2024, 2025):
        add_season(con, season)
    add_extra_race(con, "2026-05-10")  # 締めていない 2026 シーズン。入らないこと
    return con


@pytest.fixture
def names(tmp_path, monkeypatch):
    """騎手A と調教師甲だけ正式名を付けた対応表。export から使われるものも差し替える。"""
    path = tmp_path / "people.toml"
    path.write_text('[[person]]\nname = "正式名一"\njockey = "騎手A"\nsource = "テスト"\n'
                    '[[person]]\nname = "正式名二"\ntrainer = "調教師甲"\nsource = "テスト"\n',
                    encoding="utf-8")
    monkeypatch.setattr(people, "NAMES_PATH", path)
    return path


def read(out_dir):
    return json.loads((out_dir / "people.json").read_text(encoding="utf-8"))


class TestBuild:
    def test_payload(self, big, names):
        payload, problems, warnings = people.build(big, TODAY)
        assert problems == []
        assert payload["through_season"] == 2025
        jockeys = payload["roles"]["jockey"]
        assert [s["season"] for s in jockeys["seasons"]] == [2023, 2024, 2025]
        a = next(p for p in jockeys["people"] if p["key"] == "騎手A")
        assert (a["career"]["n"], a["career"]["wins"]) == (120, 120)  # 締めていない 2026 は入らない
        assert {p["slug"]: p["name"] for p in payload["pages"]} == {
            "騎手A": "正式名一", "騎手B": "騎手B", "調教師甲": "正式名二", "調教師乙": "調教師乙"}
        assert warnings == ["対応表に無い略称「調教師乙」（調教師）。略称のままページを作る",
                            "対応表に無い略称「騎手B」（騎手）。略称のままページを作る"]
        # 生成時刻を入れない。入れると毎日内容が変わり、検査 3 が成り立たない
        assert "generated_at" not in json.dumps(payload, ensure_ascii=False)

    def test_flatten_covers_every_row(self, big, names):
        payload, _, _ = people.build(big, TODAY)
        # 役割ごとに シーズン全体 3 + 2 人 ×（シーズン 3 + 通算 1）
        assert len(people.flatten(payload)) == 2 * (3 + 2 * 4)

    def test_nothing_without_closed_seasons(self, con, names):
        add_extra_race(con, "2026-05-10")
        assert people.build(con, TODAY) == (None, [], [])


class TestExport:
    """export に組み込まれ、締めたシーズンの変化（検査 3）と公開ポリシー違反で止まること。"""

    def test_people_json_is_written(self, big, db_path, tmp_path, names):
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        assert read(out_dir)["through_season"] == 2025

    def test_rerun_on_same_data_passes_check_3(self, big, db_path, tmp_path, names):
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        export.run(db_path, out_dir, today=dt.date(2026, 12, 1))  # 毎日回しても通る

    def test_new_closed_season_passes_check_3(self, big, db_path, tmp_path, names):
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        add_season(big, 2026, start_no=3)
        export.run(db_path, out_dir, today=dt.date(2027, 5, 1))
        assert read(out_dir)["through_season"] == 2026

    def test_changed_closed_season_stops_export(self, big, db_path, tmp_path, names):
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        before = (out_dir / "people.json").read_text(encoding="utf-8")
        add_extra_race(big, "2024-09-01")  # 締めた 2024 シーズンに、後から 1 レース補完された
        with pytest.raises(export.PolicyError, match="people: 締めたシーズン（2025 まで）が同じ"):
            export.run(db_path, out_dir, today=TODAY)
        assert (out_dir / "people.json").read_text(encoding="utf-8") == before

    def test_changed_closed_season_stops_export_when_through_advances(
        self, big, db_path, tmp_path, names
    ):
        # 補完で止まったまま 5/1 を迎えても、締めの進んだ版に素通りしない
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        add_extra_race(big, "2024-09-01")
        add_season(big, 2026, start_no=3)
        with pytest.raises(export.PolicyError,
                           match="people: 締めたシーズン（2025 まで）の内容が前回"):
            export.run(db_path, out_dir, today=dt.date(2027, 5, 1))

    def test_rewound_through_season_stops_export(self, big, db_path, tmp_path, names):
        out_dir = tmp_path / "out"
        add_season(big, 2026, start_no=3)
        export.run(db_path, out_dir, today=dt.date(2027, 5, 1))
        with pytest.raises(export.PolicyError, match="people: 締めが 2026 から 2025 に戻っている"):
            export.run(db_path, out_dir, today=TODAY)

    @pytest.mark.parametrize("text", [
        "{壊れた",
        '{"through_season": "2025", "roles": {}}',
        '{"through_season": 2025}',
        '{"through_season": 2025, "roles": []}',
    ])
    def test_unreadable_previous_output_stops_export(
        self, big, db_path, tmp_path, names, text
    ):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "people.json").write_text(text, encoding="utf-8")
        with pytest.raises(export.PolicyError, match="people: 前回の出力を読めない"):
            export.run(db_path, out_dir, today=TODAY)
        assert (out_dir / "people.json").read_text(encoding="utf-8") == text

    def test_renaming_in_the_table_passes_check_3(self, big, db_path, tmp_path, names):
        # 表示名は比べない。対応表の修正で export を止めないため
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        names.write_text(names.read_text(encoding="utf-8").replace("正式名一", "正式名三"),
                         encoding="utf-8")
        export.run(db_path, out_dir, today=TODAY)
        assert "正式名三" in {p["name"] for p in read(out_dir)["pages"]}

    def test_broken_pooling_stops_export(self, big, db_path, tmp_path, names, monkeypatch):
        # 2025 シーズンに 5 回だけ乗った騎手C
        for i in range(5):
            add_race(big, f"2025-07-{i + 1:02d}", 1,
                     [run(1, 1, jockey="騎手C"), run(2, 2, jockey="騎手B", trainer="調教師乙")],
                     win={1: 340}, place={1: 120, 2: 150})
        export.run(db_path, tmp_path / "ok", today=TODAY)  # まとめる処理が正しければ通る
        # まとめる処理が壊れても、書き出し前の公開ポリシーの検査で止まる
        monkeypatch.setattr(people, "pooled", lambda counts: set())
        with pytest.raises(export.PolicyError, match=r"people\[\d+\]: 集約件数 5 が下限"):
            export.run(db_path, tmp_path / "out", today=TODAY)
        assert not (tmp_path / "out").exists() or not any((tmp_path / "out").rglob("*.json"))

    def test_pages_are_checked_for_identifying_keys(self, big, db_path, names, monkeypatch):
        real = people.build_pages

        def leaky(*args):
            pages, problems, warnings = real(*args)
            return [*pages, {"slug": "x", "horse_name": "馬"}], problems, warnings

        monkeypatch.setattr(people, "build_pages", leaky)
        with pytest.raises(export.PolicyError, match="horse_name"):
            export.build(db_path, today=TODAY)

    def test_broken_names_table_stops_export(self, big, db_path, names):
        names.write_text("[[person]\n", encoding="utf-8")
        with pytest.raises(export.PolicyError, match="people.toml"):
            export.build(db_path, today=TODAY)

    def test_warnings_are_printed(self, big, db_path, names, capsys):
        export.build(db_path, today=TODAY)
        assert "警告: 対応表に無い略称「騎手B」" in capsys.readouterr().err
