"""検証ロジックのテスト。

正常データが通ることだけでなく、**異常を注入したときに実際に落ちること**を確認する。
検知しない検証器は無いのと同じなので、こちらが本体。
"""

import sqlite3

import pytest

from banei import validate
from banei.db.schema import ODDS_SCHEMA, RACES_SCHEMA


def build_races_db(path):
    con = sqlite3.connect(path)
    con.executescript(RACES_SCHEMA)
    con.execute("INSERT INTO races VALUES ('2026-08-03',1,'テストＣ１',200,'曇',3.2,'条件')")
    for horse_no, finish in ((1, 1), (2, 2)):
        con.execute(
            "INSERT INTO results (race_date,race_no,horse_no,horse_id,bracket,finish,status,"
            "horse_name,affiliation,sex,age,weight_carried,jockey,trainer,horse_weight,"
            "horse_weight_diff,time_str,time_sec,margin,popularity)"
            " VALUES ('2026-08-03',1,?,NULL,?,?,?,?,'ばんえい','牡',5,700,'騎手','調教',"
            "950,10,'1:05.4',65.4,'',1)",
            (horse_no, horse_no, finish, str(finish), f"テストホース{horse_no}"),
        )
    con.execute("INSERT INTO payouts VALUES ('2026-08-03',1,'単勝','1',340,1)")
    con.execute("INSERT INTO scraped_days VALUES ('2026-08-03',1,'2026-08-04T00:00:00')")
    con.commit()
    con.close()


def build_odds_db(path):
    con = sqlite3.connect(path)
    con.executescript(ODDS_SCHEMA)
    con.execute("INSERT INTO odds VALUES ('2026-08-03',1,1,'テストホース1',3.4,1.1,1.9)")
    con.execute("INSERT INTO odds VALUES ('2026-08-03',1,2,'テストホース2',5.6,2.0,3.1)")
    con.commit()
    con.close()


@pytest.fixture
def dbs(tmp_path):
    races, odds = tmp_path / "banei.db", tmp_path / "odds.db"
    build_races_db(races)
    build_odds_db(odds)
    return races, odds


def corrupt(path, sql):
    con = sqlite3.connect(path)
    con.execute(sql)
    con.commit()
    con.close()


def test_valid_data_passes(dbs):
    races, odds = dbs
    assert validate.run(races, odds, verbose=False) == 0


def test_passes_without_odds_db(dbs, tmp_path):
    races, _ = dbs
    assert validate.run(races, tmp_path / "missing.db", verbose=False) == 0


class TestDetectsRaceAnomalies:
    """レース結果側の異常。いずれも検知して 1 を返さなければならない。"""

    @pytest.mark.parametrize(("label", "sql"), [
        ("孤立した results",
         "INSERT INTO results (race_date,race_no,horse_no,horse_name,sex,age,weight_carried)"
         " VALUES ('2026-08-04',9,1,'孤児','牡',5,700)"),
        ("results が無いレース",
         "INSERT INTO races VALUES ('2026-08-05',1,'空',200,'曇',3.2,'条件')"),
        ("horse_name が空", "UPDATE results SET horse_name='' WHERE horse_no=1"),
        ("単勝払戻の欠落", "DELETE FROM payouts WHERE bet_type='単勝'"),
        ("払戻金が 0 円", "UPDATE payouts SET amount=0"),
        ("race_no が範囲外", "UPDATE races SET race_no=99"),
        ("着順が範囲外", "UPDATE results SET finish=99 WHERE horse_no=1"),
        ("距離が範囲外", "UPDATE races SET distance_m=5000"),
        ("馬場水分が欠損", "UPDATE races SET moisture=NULL"),
        ("馬齢が範囲外", "UPDATE results SET age=99 WHERE horse_no=1"),
        ("積載重量が範囲外", "UPDATE results SET weight_carried=99 WHERE horse_no=1"),
        ("性別が想定外", "UPDATE results SET sex='X' WHERE horse_no=1"),
        ("n_races が範囲外", "UPDATE scraped_days SET n_races=99"),
    ])
    def test_detected(self, dbs, label, sql):
        races, odds = dbs
        corrupt(races, sql)
        assert validate.run(races, odds, verbose=False) == 1, f"{label} を検知できていない"


class TestDetectsOddsAnomalies:
    def test_all_win_odds_missing_in_a_race(self, dbs):
        races, odds = dbs
        corrupt(odds, "UPDATE odds SET win_odds=NULL")
        assert validate.run(races, odds, verbose=False) == 1

    def test_place_range_inverted(self, dbs):
        races, odds = dbs
        corrupt(odds, "UPDATE odds SET place_min=9.9, place_max=1.0 WHERE horse_no=1")
        assert validate.run(races, odds, verbose=False) == 1

    def test_combo_odds_negative(self, dbs):
        races, odds = dbs
        corrupt(odds, "INSERT INTO combo_odds VALUES ('2026-08-03',1,'馬連複','1-2',-1,NULL)")
        assert validate.run(races, odds, verbose=False) == 1

    def test_all_combinations_missing_odds(self, dbs):
        # 券種内の全組番が NULL ならパース失敗の兆候
        races, odds = dbs
        corrupt(odds, "INSERT INTO combo_odds VALUES ('2026-08-03',1,'馬連複','1-2',NULL,NULL)")
        assert validate.run(races, odds, verbose=False) == 1


@pytest.fixture
def combo_dbs(dbs):
    """2026-08-03 1R に、払戻と整合する馬連複・ワイドの組み合わせオッズを足す。

    ワイドの払戻はオッズ範囲の内側に来ることが多い（実データで約半数）ので、
    下限とも上限とも一致しない値にしてある。
    """
    races, odds = dbs
    corrupt(races, "INSERT INTO payouts VALUES ('2026-08-03',1,'馬連複','1-2',430,1)")
    corrupt(races, "INSERT INTO payouts VALUES ('2026-08-03',1,'ワイド','1-2',190,1)")
    for bet_type in ("馬連複", "ワイド"):
        corrupt(odds, f"INSERT INTO combo_meta VALUES ('2026-08-03',1,'{bet_type}',2,'x')")
    corrupt(odds, "INSERT INTO combo_odds VALUES ('2026-08-03',1,'馬連複','1-2',4.3,NULL)")
    corrupt(odds, "INSERT INTO combo_odds VALUES ('2026-08-03',1,'馬連複','1-3',12.3,NULL)")
    corrupt(odds, "INSERT INTO combo_odds VALUES ('2026-08-03',1,'ワイド','1-2',1.8,2.0)")
    corrupt(odds, "INSERT INTO combo_odds VALUES ('2026-08-03',1,'ワイド','1-3',3.1,3.5)")
    return races, odds


class TestComboOddsMatchPayouts:
    """組み合わせオッズを払戻と照合する（オッズ × 100 = 払戻）。

    2026-08-06 にマトリクスの列ずれで別の組番のオッズが記録されていたのを、
    払戻との手作業の照合で見つけた（2026-08-03 4R 馬複 6-10 が 4.3 のはずが 9.7）。
    検証に組み込んで照合漏れをなくす。
    """

    def test_consistent_odds_pass(self, combo_dbs):
        races, odds = combo_dbs
        assert validate.run(races, odds, verbose=False) == 0

    @pytest.mark.parametrize(("label", "sql"), [
        ("列ずれで別の値が入った",
         "UPDATE combo_odds SET odds=9.7 WHERE bet_type='馬連複' AND combination='1-2'"),
        ("的中組番のオッズが NULL",
         "UPDATE combo_odds SET odds=NULL WHERE bet_type='馬連複' AND combination='1-2'"),
        ("的中組番の行が無い",
         "DELETE FROM combo_odds WHERE bet_type='馬連複' AND combination='1-2'"),
        ("ワイドの払戻がオッズ範囲より下",
         "UPDATE combo_odds SET odds=2.5, odds_max=3.0"
         " WHERE bet_type='ワイド' AND combination='1-2'"),
        ("ワイドの払戻がオッズ範囲より上",
         "UPDATE combo_odds SET odds=1.0, odds_max=1.5"
         " WHERE bet_type='ワイド' AND combination='1-2'"),
    ])
    def test_mismatch_detected(self, combo_dbs, label, sql):
        races, odds = combo_dbs
        corrupt(odds, sql)
        assert validate.run(races, odds, verbose=False) == 1, f"{label} を検知できていない"

    def test_dead_heat_race_is_excluded(self, combo_dbs):
        """同着レースは払戻が複数組番に分割されるのでオッズと一致しない。正常。

        1〜3 着の同着は 148 レースあり、分割払戻はすべてこれで説明できる。
        """
        races, odds = combo_dbs
        corrupt(races, "UPDATE results SET finish=1 WHERE horse_no=2")
        corrupt(races, "UPDATE payouts SET amount=215 WHERE bet_type='馬連複'")
        assert validate.run(races, odds, verbose=False) == 0

    def test_special_payout_without_winning_tickets(self, combo_dbs):
        """的中票が無いときの特払い（70 円・組番は空）は照合しない。2011〜2017 に 8 件ある。"""
        races, odds = combo_dbs
        corrupt(races, "INSERT INTO payouts VALUES ('2026-08-03',1,'三連複','',70,NULL)")
        corrupt(odds, "INSERT INTO combo_meta VALUES ('2026-08-03',1,'三連複',1,'x')")
        corrupt(odds, "INSERT INTO combo_odds VALUES ('2026-08-03',1,'三連複','1-2-3',85.0,NULL)")
        assert validate.run(races, odds, verbose=False) == 0

    def test_unfetched_bet_type_is_not_checked(self, combo_dbs):
        # 組み合わせオッズはバックフィル中。未取得の券種まで照合すると全部落ちる
        races, odds = combo_dbs
        corrupt(races, "INSERT INTO payouts VALUES ('2026-08-03',1,'馬連単','1-2',1030,1)")
        assert validate.run(races, odds, verbose=False) == 0


class TestAcceptsLegitimatePatterns:
    """実データに存在する正常パターンを異常扱いしないこと。"""

    def test_dead_heat_is_not_an_error(self, dbs):
        # 同着は 19 年間で 37 レース存在する
        races, odds = dbs
        corrupt(races, "UPDATE results SET finish=1 WHERE horse_no=2")
        assert validate.run(races, odds, verbose=False) == 0

    def test_scratched_horse_without_odds(self, dbs):
        # 取消・除外馬は win_odds が NULL になる（全馬 NULL でなければ正常）
        races, odds = dbs
        corrupt(races, "UPDATE results SET finish=NULL, status='取消' WHERE horse_no=2")
        corrupt(odds, "UPDATE odds SET win_odds=NULL, place_min=NULL, place_max=NULL"
                      " WHERE horse_no=2")
        assert validate.run(races, odds, verbose=False) == 0

    def test_combination_without_votes_is_not_an_error(self, dbs):
        """票が入らなかった組番はオッズが付かず NULL になる。異常ではない。

        2026-07-20 1R 馬連単 7-9 / 9-7 が実際に 0.0 と表示されていた。
        """
        races, odds = dbs
        corrupt(odds, "INSERT INTO combo_odds VALUES ('2026-08-03',1,'馬連複','1-2',12.3,NULL)")
        corrupt(odds, "INSERT INTO combo_odds VALUES ('2026-08-03',1,'馬連複','1-3',NULL,NULL)")
        assert validate.run(races, odds, verbose=False) == 0

    def test_cancelled_meeting_is_only_a_warning(self, dbs):
        # 中止で n_races=0 の開催日は 6 日実在する
        races, odds = dbs
        corrupt(races, "INSERT INTO scraped_days VALUES ('2026-08-04',0,'2026-08-05T00:00:00')")
        assert validate.run(races, odds, verbose=False) == 0
