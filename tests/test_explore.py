"""探索 UI の集計（explore.py）のテスト。合成データのみ（実データ・実ページは使わない）。"""

import datetime as dt
import sqlite3

import pytest

from banei.db.schema import RACES_SCHEMA
from banei.export import explore

SEASON_2025 = "2025-06-01"  # 2025 シーズン（2025-04-01〜2026-03-31）


def horse(no, finish=None, status=None, popularity=None, age=5, sex="牡", weight=700):
    """出走馬 1 頭。status を省くと着順の数字を入れる（実データと同じ）。"""
    return {"no": no, "finish": finish, "status": status or str(finish),
            "popularity": popularity or no, "age": age, "sex": sex, "weight": weight}


def add_race(con, date, race_no, horses, win=None, place=None, moisture=1.2, weather="晴"):
    """1 レースを足す。win / place は {馬番: 払戻}。place が空ならそのレースは複勝の払戻なし。"""
    con.execute("INSERT INTO races VALUES (?,?,?,?,?,?,?)",
                (date, race_no, "テスト", 200, weather, moisture, "条件"))
    for h in horses:
        con.execute(
            "INSERT INTO results (race_date,race_no,horse_no,finish,status,horse_name,sex,age,"
            "weight_carried,popularity) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (date, race_no, h["no"], h["finish"], h["status"], f"馬{h['no']}", h["sex"],
             h["age"], h["weight"], h["popularity"]))
    for bet, pays in (("単勝", win or {}), ("複勝", place or {})):
        for no, amount in pays.items():
            con.execute("INSERT INTO payouts VALUES (?,?,?,?,?,NULL)",
                        (date, race_no, bet, str(no), amount))


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "banei.db"


@pytest.fixture
def con(db_path):
    # export.build は別の接続（読み取り専用）で開くので、書いたらすぐ見えるよう autocommit にする
    c = sqlite3.connect(db_path, isolation_level=None)
    c.executescript(RACES_SCHEMA)
    yield c
    c.close()


def sum_cells(cells):
    out = [0] * 6
    for m in cells.values():
        for i, v in enumerate(m):
            out[i] += v
    return out


class TestPopulation:
    def test_scratched_and_excluded_are_not_counted(self, con):
        add_race(con, SEASON_2025, 1,
                 [horse(1, 1), horse(2, 2), horse(3, status="取消"), horse(4, status="除外")],
                 win={1: 340}, place={1: 120, 2: 150})
        assert explore.population(con, 2025) == {2025: 2}
        assert sum_cells(explore.load_cells(con, 2025))[explore.N] == 2

    def test_stopped_and_disqualified_count_as_losing_runs(self, con):
        # 中止・失格は人気が付いていて馬券は外れ扱い。回収率の分母に入れる
        add_race(con, SEASON_2025, 1,
                 [horse(1, 1), horse(2, status="中止"), horse(3, status="失格")],
                 win={1: 200}, place={1: 110})
        n, win, top2, place, win_pay, place_pay = sum_cells(explore.load_cells(con, 2025))
        assert (n, win, top2, place) == (3, 1, 1, 1)
        assert (win_pay, place_pay) == (200, 110)

    def test_dead_heat_counts_both_winners(self, con):
        add_race(con, SEASON_2025, 1, [horse(1, 1), horse(2, 1), horse(3, 3)],
                 win={1: 150, 2: 260}, place={1: 110, 2: 130})
        n, win, top2, _, win_pay, _ = sum_cells(explore.load_cells(con, 2025))
        assert (n, win, top2, win_pay) == (3, 2, 2, 410)

    def test_place_follows_payouts_in_small_fields(self, con):
        # 7 頭以下は 2 着までしか複勝の払戻が無い。3 着は複勝率に入らない
        add_race(con, SEASON_2025, 1, [horse(i, i) for i in range(1, 8)],
                 win={1: 300}, place={1: 120, 2: 180})
        _, _, top2, place, _, place_pay = sum_cells(explore.load_cells(con, 2025))
        assert (top2, place, place_pay) == (2, 2, 300)

    def test_race_without_place_payouts_is_excluded(self, con):
        add_race(con, SEASON_2025, 1, [horse(1, 1), horse(2, 2), horse(3, 3)],
                 win={1: 140}, place={})
        assert explore.population(con, 2025) == {}
        assert explore.load_cells(con, 2025) == {}

    def test_unclosed_season_is_excluded(self, con):
        add_race(con, "2026-03-31", 1, [horse(1, 1)], win={1: 100}, place={1: 100})
        add_race(con, "2026-04-01", 1, [horse(1, 1)], win={1: 100}, place={1: 100})
        assert explore.population(con, 2025) == {2025: 1}

    def test_weight_diff_ignores_scratched_horses(self, con):
        # 取消馬が最も軽くても、重量差の基準は出走した馬の中で決める
        add_race(con, SEASON_2025, 1,
                 [horse(1, 1, weight=700), horse(2, 2, weight=720),
                  horse(3, status="取消", weight=650)],
                 win={1: 200}, place={1: 110, 2: 120})
        cells = explore.load_cells(con, 2025)
        w = [a.key for a in explore.AXES].index("weight_diff")
        assert sorted(key[1 + w] for key in cells) == [0, 2]  # 0kg と 11〜20kg

    def test_unexpected_axis_value_is_left_out_of_cells(self, con):
        # 想定外の値を黙って別の区分に入れない。母数には入るので検査 2 で止まる（Task 3）
        add_race(con, SEASON_2025, 1, [horse(1, 1), horse(2, 2)],
                 win={1: 200}, place={1: 110, 2: 120}, weather="霧")
        assert explore.population(con, 2025) == {2025: 2}
        assert explore.load_cells(con, 2025) == {}


class TestSeason:
    @pytest.mark.parametrize(("today", "expected"), [
        (dt.date(2026, 4, 30), 2024),
        (dt.date(2026, 5, 1), 2025),
        (dt.date(2026, 10, 13), 2025),
        (dt.date(2027, 3, 31), 2025),
    ])
    def test_through_season_closes_on_may_1(self, today, expected):
        assert explore.through_season(today) == expected

    def test_today_is_judged_in_jst(self, monkeypatch):
        # UTC では 4/30 でも JST では 5/1。ランナーのローカル時刻（UTC）に頼らない
        monkeypatch.setattr(
            explore, "_now", lambda: dt.datetime(2026, 4, 30, 15, 30, tzinfo=dt.UTC))
        assert explore.today_jst() == dt.date(2026, 5, 1)

    def test_bands_split_seasons_from_2023(self):
        assert [explore.band_of(s) for s in (2007, 2022, 2023, 2025)] == [2022, 2022, 2023, 2025]


class TestAxisLabels:
    @pytest.mark.parametrize(("key", "group", "label"), [
        ("popularity", [8, 9], "9〜10"),
        ("weight_diff", [0], "0kg"),
        ("weight_diff", [0, 1], "0〜10kg"),
        ("weight_diff", [3, 4], "21kg〜"),
        ("age", [0], "2歳"),
        ("age", [7, 8], "9歳〜"),
        ("sex", [1, 2], "牡・セン"),
        ("moisture", [0], "〜0.9"),
        ("moisture", [4, 5], "2.5〜"),
        # 両端が開いた軸を全部まとめても "None" にしない
        ("moisture", [0, 1, 2, 3, 4, 5], "すべて"),
        ("weather", [1, 2], "曇・雨・雪"),
        ("month", [0, 1], "4〜5月"),
        ("month", [8, 9], "12〜1月"),
    ])
    def test_label(self, key, group, label):
        axis = next(a for a in explore.AXES if a.key == key)
        assert axis.label(group) == label
