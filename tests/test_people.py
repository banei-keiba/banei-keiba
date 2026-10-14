"""騎手・調教師ページの集計（people.py）のテスト。合成データのみ（実データ・実ページは使わない）。"""

import datetime as dt
import random
import sqlite3

import pytest

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
