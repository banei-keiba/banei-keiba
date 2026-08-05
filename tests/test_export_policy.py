"""公開データの出口が実際に塞がっているかのテスト。

生データが 1 度でも公開側に出ると取り返しがつかないので、
「違反を作ったら止まる」ことを確かめるのがこのテストの本題。
"""

import sqlite3

import pytest

from banei import export
from banei.db.schema import RACES_SCHEMA
from banei.export.aggregates import AGGREGATES, MIN_GROUP_SIZE, policy_violations


def build_db(path, n_races=40):
    """ポリシーを満たすだけの件数がある最小 DB を作る。"""
    con = sqlite3.connect(path)
    con.executescript(RACES_SCHEMA)
    for i in range(n_races):
        date = f"2026-01-{i % 28 + 1:02d}"
        con.execute("INSERT INTO races VALUES (?,?,?,?,?,?,?)",
                    (date, i, "テストＣ１", 200, "曇", 3.0, "条件"))
        for horse_no in (1, 2):
            con.execute(
                "INSERT INTO results (race_date,race_no,horse_no,bracket,finish,status,"
                "horse_name,affiliation,sex,age,weight_carried,jockey,trainer,"
                "horse_weight,horse_weight_diff,time_str,time_sec,margin,popularity)"
                " VALUES (?,?,?,?,?,?,?,'ばんえい','牡',5,?, '騎手','調教',950,10,"
                "'1:05.4',65.4,'',?)",
                (date, i, horse_no, horse_no, horse_no, str(horse_no),
                 f"馬{horse_no}", 700 + horse_no * 10, horse_no),
            )
        con.execute("INSERT INTO payouts VALUES (?,?,'単勝','1',340,1)", (date, i))
    con.commit()
    con.close()


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "banei.db"
    build_db(p)
    return p


class TestPolicyChecker:
    """検査器そのものが違反を捕まえるか。"""

    def test_clean_rows_pass(self):
        assert policy_violations("t", [{"moisture": 1, "n": 100}]) == []

    @pytest.mark.parametrize("key", [
        "race_date", "race_no", "horse_no", "horse_id", "horse_name",
        "combination", "bet_type", "time_str", "margin", "status",
    ])
    def test_identifying_key_rejected(self, key):
        problems = policy_violations("t", [{key: "x", "n": 100}])
        assert problems, f"{key} を検知できていない"
        assert key in problems[0]

    def test_missing_count_column_rejected(self):
        problems = policy_violations("t", [{"moisture": 1, "avg": 2.0}])
        assert problems and "件数列" in problems[0]

    def test_group_below_minimum_rejected(self):
        problems = policy_violations("t", [{"moisture": 1, "n": MIN_GROUP_SIZE - 1}])
        assert problems and "下限" in problems[0]

    def test_group_at_minimum_passes(self):
        assert policy_violations("t", [{"moisture": 1, "n": MIN_GROUP_SIZE}]) == []

    def test_all_count_columns_must_clear_the_floor(self):
        # 1 つでも小さい件数列があれば、その粒度で個体の値が読めてしまう
        problems = policy_violations("t", [{"n": 1000, "n_sub": 2}])
        assert problems and "下限" in problems[0]

    def test_group_size_check_can_be_skipped_but_keys_still_checked(self):
        # サマリ用。件数の下限は当てないが、個体特定キーは通さない
        assert policy_violations("t", [{"n_jockeys": 51}], check_group_size=False) == []
        problems = policy_violations(
            "t", [{"n_jockeys": 51, "horse_name": "馬"}], check_group_size=False)
        assert problems and "horse_name" in problems[0]

    def test_bool_is_not_a_count(self):
        # True は int のサブクラスなので、件数列と誤認しないこと
        problems = policy_violations("t", [{"n_flag": True, "moisture": 1}])
        assert problems and "件数列" in problems[0]


class TestBuildEnforcesPolicy:
    """書き出し時に実際に止まるか。テストではなく実行時の防御。"""

    def test_clean_build_succeeds(self, db):
        out = export.build(db)
        assert set(out) == {"summary", *AGGREGATES}

    def test_leaky_aggregate_aborts_build(self, db, monkeypatch):
        monkeypatch.setitem(
            AGGREGATES, "leaky",
            lambda con: [{"race_date": "2026-01-01", "race_no": 1, "n": 999}])
        with pytest.raises(export.PolicyError, match="race_date"):
            export.build(db)

    def test_too_granular_aggregate_aborts_build(self, db, monkeypatch):
        monkeypatch.setitem(AGGREGATES, "granular", lambda con: [{"moisture": 1, "n": 1}])
        with pytest.raises(export.PolicyError, match="下限"):
            export.build(db)

    def test_no_files_written_when_policy_fails(self, db, tmp_path, monkeypatch):
        out_dir = tmp_path / "out"
        monkeypatch.setitem(AGGREGATES, "leaky", lambda con: [{"horse_name": "馬", "n": 99}])
        with pytest.raises(export.PolicyError):
            export.run(db, out_dir)
        assert not out_dir.exists() or list(out_dir.iterdir()) == []


class TestRealAggregates:
    """本番の集計定義がポリシーを満たしているか。"""

    def test_all_outputs_clean(self, db):
        out = export.build(db)
        for name, payload in out.items():
            rows = payload if isinstance(payload, list) else [payload]
            assert policy_violations(name, rows, check_group_size=(name != "summary")) == []

    def test_every_aggregate_is_covered(self, db):
        # AGGREGATES に足した集計が出力されないまま放置されないこと
        out = export.build(db)
        assert set(AGGREGATES) <= set(out)

    def test_written_files_are_valid_json(self, db, tmp_path):
        import json
        out_dir = tmp_path / "out"
        export.run(db, out_dir)
        for path in out_dir.glob("*.json"):
            json.loads(path.read_text(encoding="utf-8"))
