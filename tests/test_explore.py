"""探索 UI の集計（explore.py）のテスト。合成データのみ（実データ・実ページは使わない）。"""

import datetime as dt
import json
import sqlite3

import pytest

from banei import export
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
    # 1 行ごとに fsync すると big の用意だけで数秒かかる。使い捨ての DB なので同期を切る
    c.execute("PRAGMA synchronous = OFF")
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

    @pytest.mark.parametrize("axis", explore.AXES, ids=lambda a: a.key)
    def test_every_range_label_decodes_back(self, axis):
        # 前回の出力の区分を表示名から戻すので、隣り合う区分のまとまりの表示名は軸の中で重複しない
        n = axis.n_bins
        ranges = [list(range(i, j + 1)) for i in range(n) for j in range(i, n)]
        assert len({axis.label(r) for r in ranges}) == len(ranges)
        groups = [[0], list(range(1, n))]
        assert axis.decode([axis.label(g) for g in groups]) == groups

    @pytest.mark.parametrize("labels", [["1", "3"], ["x"], [1], None, [["1"]]])
    def test_decode_rejects_what_is_not_a_partition(self, labels):
        assert explore.AXES[0].decode(labels) is None


TODAY = dt.date(2026, 10, 13)  # 2025 シーズンまで締めている


def add_season(con, season, n_races=40, start_no=1):
    """1 シーズン分の均一なレース。各表のマスが期間帯ごとに 30 件以上になる。"""
    for i in range(n_races):
        add_race(con, f"{season}-05-{i % 28 + 1:02d}", start_no + i // 28,
                 [horse(1, 1, weight=700), horse(2, 2, weight=710)],
                 win={1: 340}, place={1: 120, 2: 150})


@pytest.fixture
def big(con):
    for season in (2021, 2022, 2023, 2024, 2025):
        add_season(con, season)
    # 締めていない 2026 シーズン。入らないこと
    add_race(con, "2026-05-10", 1, [horse(1, 1), horse(2, 2)],
             win={1: 340}, place={1: 120, 2: 150})
    return con


def add_rare_third_favorite(con):
    """2025 シーズンにだけ 3 番人気（馬番 3）が 5 回出る。期間帯 2025 で 30 件に届かない。"""
    for i in range(5):
        add_race(con, f"2025-07-{i + 1:02d}", 1, [horse(1, 1), horse(3, 2)],
                 win={1: 300}, place={1: 110, 3: 140})


class TestBuild:
    def test_builds_every_table(self, big):
        out, problems = explore.build(big, TODAY)
        assert problems == []
        assert len(out) == 36
        assert {"explore/popularity", "explore/popularity__moisture"} <= set(out)

    def test_periods_and_metrics(self, big):
        out, _ = explore.build(big, TODAY)
        t = out["explore/popularity"]
        assert t["axes"] == ["popularity"] and t["through_season"] == 2025
        all_, recent = t["periods"]["all"], t["periods"]["recent3"]
        assert (all_["first_season"], all_["last_season"]) == (2021, 2025)
        assert (recent["first_season"], recent["last_season"]) == (2023, 2025)
        # 5 シーズン × 40 レース × 2 頭。締めていない 2026 は入らない
        assert all_["total"]["n"] == 400
        assert recent["total"]["n"] == 240
        assert all_["cells"] == [
            {"popularity": "1", "n": 200, "win_rate": 100.0, "top2_rate": 100.0,
             "place_rate": 100.0, "win_roi": 340.0, "place_roi": 120.0},
            {"popularity": "2", "n": 200, "win_rate": 0.0, "top2_rate": 100.0,
             "place_rate": 100.0, "win_roi": 0.0, "place_roi": 150.0},
        ]
        assert "margins" not in all_

    def test_two_axis_table_has_margins_matching_cells(self, big):
        out, _ = explore.build(big, TODAY)
        p = out["explore/popularity__weight_diff"]["periods"]["all"]
        assert [(c["popularity"], c["weight_diff"], c["n"]) for c in p["cells"]] == [
            ("1", "0kg", 200), ("2", "1〜10kg", 200)]
        assert [m["n"] for m in p["margins"]["popularity"]] == [200, 200]
        assert [m["n"] for m in p["margins"]["weight_diff"]] == [200, 200]
        assert p["total"]["n"] == 400

    def test_small_band_cell_is_merged_not_dropped(self, big):
        # 消すと引き算で割り出せるので、隣とまとめて全出走を残す
        add_rare_third_favorite(big)
        out, problems = explore.build(big, TODAY)
        assert problems == []
        t = out["explore/popularity"]
        assert t["bins"]["popularity"][:2] == ["1", "2〜3"]
        assert t["periods"]["all"]["total"]["n"] == 410

    def test_flatten_covers_cells_margins_and_total(self, big):
        out, _ = explore.build(big, TODAY)
        rows = explore.flatten(out["explore/popularity__weight_diff"])
        # 2 期間 ×（マス 2 + 人気の全体 2 + 重量差の全体 2 + 合計 1）
        assert len(rows) == 14

    def test_nothing_is_built_without_closed_seasons(self, con):
        add_race(con, "2026-05-10", 1, [horse(1, 1), horse(2, 2)],
                 win={1: 340}, place={1: 120, 2: 150})
        assert explore.build(con, TODAY) == ({}, [])


class TestBuildChecks:
    """検査 1・2。違反を作ったら必ず報告されること。"""

    def test_check_1_catches_a_small_cell(self, big, monkeypatch):
        # まとめ方が壊れても、書き出し前の検査 1 で止まること
        monkeypatch.setattr(explore, "merge_bins",
                            identity_merge)
        add_rare_third_favorite(big)
        _, problems = explore.build(big, TODAY)
        assert any("0 か 30 以上" in p for p in problems)

    def test_check_2_catches_an_unexpected_axis_value(self, big):
        add_race(big, "2025-08-01", 1, [horse(1, 1), horse(2, 2)],
                 win={1: 300}, place={1: 110, 2: 120}, weather="霧")
        _, problems = explore.build(big, TODAY)
        assert problems and all("対象出走数" in p for p in problems)

    def test_band_total_below_floor_is_reported(self, con):
        # 期間帯の合計そのものが 30 件未満だと、まとめても規則を満たせない
        for season in (2022, 2023, 2024):
            add_season(con, season)
        for i in range(10):  # 2025 シーズンは 10 レース × 2 頭 = 20 出走しかない
            add_race(con, f"2025-05-{i + 1:02d}", 1, [horse(1, 1), horse(2, 2)],
                     win={1: 300}, place={1: 110, 2: 120})
        out, problems = explore.build(con, TODAY)
        assert out == {}
        assert len(problems) == 36 and all("まとめても" in p for p in problems)

    def test_misconfigured_first_recent_season_is_reported(self, big, monkeypatch):
        monkeypatch.setattr(explore, "FIRST_RECENT_SEASON", 2024)
        out, problems = explore.build(big, TODAY)
        assert out == {} and "FIRST_RECENT_SEASON" in problems[0]


def identity_merge(counts, n_bins, floor, start=None):
    """まとめ方が壊れた状態（何もまとめない）。"""
    return [[[b] for b in range(n)] for n in n_bins]


def merge_second_and_third(counts, n_bins, floor, start=None):
    """10 区分の軸の 2 番目と 3 番目をまとめる（過去の版でまとめる必要があった状態を作る）。"""
    return [[[0], [1, 2], *([b] for b in range(3, n))] if n == 10 else [[b] for b in range(n)]
            for n in n_bins]


def read(out_dir, name):
    return json.loads((out_dir / f"explore/{name}.json").read_text(encoding="utf-8"))


class TestExport:
    """export に組み込まれ、違反があれば書き出し全体が止まること。"""

    def test_tables_are_written_under_explore(self, big, db_path, tmp_path):
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        files = sorted(p.name for p in (out_dir / "explore").glob("*.json"))
        assert len(files) == 36 and "popularity__moisture.json" in files
        t = read(out_dir, "popularity")
        assert t["through_season"] == 2025
        # 生成時刻を入れない。入れると毎日内容が変わり、検査 3 が成り立たない
        assert "generated_at" not in json.dumps(t)

    def test_rerun_on_same_data_passes_check_3(self, big, db_path, tmp_path):
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        export.run(db_path, out_dir, today=dt.date(2026, 12, 1))  # 毎日回しても通る

    def test_changed_closed_season_stops_export(self, big, db_path, tmp_path):
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        before = (out_dir / "explore/popularity.json").read_text(encoding="utf-8")
        # 締めた 2024 シーズンに、後から 1 レース補完された
        add_race(big, "2024-09-01", 1, [horse(1, 1), horse(2, 2)],
                 win={1: 340}, place={1: 120, 2: 150})
        with pytest.raises(export.PolicyError, match="締めたシーズン"):
            export.run(db_path, out_dir, today=TODAY)
        assert (out_dir / "explore/popularity.json").read_text(encoding="utf-8") == before

    def test_new_closed_season_passes_check_3(self, big, db_path, tmp_path):
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        add_season(big, 2026, start_no=3)
        export.run(db_path, out_dir, today=dt.date(2027, 5, 1))
        assert read(out_dir, "popularity")["through_season"] == 2026

    def test_rewound_through_season_stops_export(self, big, db_path, tmp_path):
        out_dir = tmp_path / "out"
        add_season(big, 2026, start_no=3)
        export.run(db_path, out_dir, today=dt.date(2027, 5, 1))
        with pytest.raises(export.PolicyError, match="戻っている"):
            export.run(db_path, out_dir, today=TODAY)

    def test_unreadable_previous_output_stops_export(self, big, db_path, tmp_path):
        out_dir = tmp_path / "out"
        (out_dir / "explore").mkdir(parents=True)
        (out_dir / "explore/popularity.json").write_text("{壊れた", encoding="utf-8")
        with pytest.raises(export.PolicyError, match="読めない"):
            export.run(db_path, out_dir, today=TODAY)
        assert (out_dir / "explore/popularity.json").read_text(encoding="utf-8") == "{壊れた"

    def test_explore_violation_stops_all_output(self, big, db_path, tmp_path, monkeypatch):
        monkeypatch.setattr(explore, "merge_bins", identity_merge)
        add_rare_third_favorite(big)
        out_dir = tmp_path / "out"
        with pytest.raises(export.PolicyError, match="0 か 30 以上"):
            export.run(db_path, out_dir, today=TODAY)
        assert not out_dir.exists() or not any(out_dir.rglob("*.json"))

    def test_policy_checker_also_runs_on_tables(self, big, db_path, monkeypatch):
        # 個体キーが混ざったら、explore の中の検査とは別に既存の検査でも止まる
        real = explore.flatten
        monkeypatch.setattr(
            explore, "flatten", lambda p: [*real(p), {"race_date": "2025-05-01", "n": 99}])
        with pytest.raises(export.PolicyError, match="race_date"):
            export.build(db_path, today=TODAY)

    def test_bins_never_get_finer_across_versions(self, big, db_path, tmp_path, monkeypatch):
        # 前回の版でまとめた区分を分け直すと、版と版の差でどの版でも検査していない切れ端が出る
        out_dir = tmp_path / "out"
        with monkeypatch.context() as m:
            m.setattr(explore, "merge_bins", merge_second_and_third)
            export.run(db_path, out_dir, today=TODAY)
        assert read(out_dir, "popularity")["bins"]["popularity"][:2] == ["1", "2〜3"]
        add_season(big, 2026, start_no=3)
        export.run(db_path, out_dir, today=dt.date(2027, 5, 1))
        assert read(out_dir, "popularity")["bins"]["popularity"][:2] == ["1", "2〜3"]

    def test_finer_bins_than_previous_stop_export(self, big, db_path, tmp_path, monkeypatch):
        # 検査 4: まとめ方が前回の区分を無視しても、書き出し前に止まる
        out_dir = tmp_path / "out"
        with monkeypatch.context() as m:
            m.setattr(explore, "merge_bins", merge_second_and_third)
            export.run(db_path, out_dir, today=TODAY)
        add_season(big, 2026, start_no=3)
        monkeypatch.setattr(explore, "merge_bins", identity_merge)
        with pytest.raises(export.PolicyError, match="細かく"):
            export.run(db_path, out_dir, today=dt.date(2027, 5, 1))

    def test_changed_closed_season_stops_export_when_through_advances(self, big, db_path, tmp_path):
        # 4 月に締めた 2024 シーズンが補完されて止まったまま 5/1 を迎えても、素通りしない
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        add_race(big, "2024-09-01", 1, [horse(1, 1), horse(2, 2)],
                 win={1: 340}, place={1: 120, 2: 150})
        add_season(big, 2026, start_no=3)
        with pytest.raises(export.PolicyError, match="締めたシーズン（2025 まで）"):
            export.run(db_path, out_dir, today=dt.date(2027, 5, 1))

    @pytest.mark.parametrize("through", ['"2025"', "null", "true"])
    def test_malformed_previous_through_season_stops_export(
        self, big, db_path, tmp_path, through
    ):
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        path = out_dir / "explore/popularity.json"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace('"through_season": 2025', f'"through_season": {through}'),
                        encoding="utf-8")
        with pytest.raises(export.PolicyError, match="読めない"):
            export.run(db_path, out_dir, today=TODAY)

    def test_undecodable_previous_bins_stop_export(self, big, db_path, tmp_path):
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        path = out_dir / "explore/popularity.json"
        t = json.loads(path.read_text(encoding="utf-8"))
        t["bins"]["popularity"][0] = "1番人気"
        path.write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(export.PolicyError, match="読めない"):
            export.run(db_path, out_dir, today=TODAY)
