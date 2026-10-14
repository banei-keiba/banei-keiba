"""騎手・調教師ページの集計（people.py）のテスト。合成データのみ（実データ・実ページは使わない）。"""

import datetime as dt
import sqlite3

import pytest

from banei.db.schema import RACES_SCHEMA
from banei.export import people

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
