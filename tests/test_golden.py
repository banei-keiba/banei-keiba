"""保存 HTML → 期待レコードのゴールデンテスト。

フィクスチャは実 HTML ではなく構造を再現した合成 HTML（tests/fixtures/README.md 参照）。
検証対象はこちらのパーサのロジックであり、相手サイトの構造変更は `banei validate` で検知する。
"""

from pathlib import Path

import pytest

from banei.ingest.combo_odds import parse_matrix, parse_sanrentan_page
from banei.ingest.odds import parse_odds_page
from banei.ingest.results import parse_result_page

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def parsed():
    return parse_result_page(fixture("result_page.html"))


@pytest.fixture(scope="module")
def odds_rows():
    return parse_odds_page(fixture("odds_page.html"))


@pytest.fixture(scope="module")
def matrix_unordered():
    return parse_matrix(fixture("combo_matrix.html"), ordered=False)


@pytest.fixture(scope="module")
def sanrentan():
    return parse_sanrentan_page(fixture("sanrentan_page.html"))


class TestResultPageRace:
    def test_name_from_h3(self, parsed):
        assert parsed["race"]["name"] == "テスト記念Ｃ１－３"

    def test_distance_from_conditions(self, parsed):
        assert parsed["race"]["distance_m"] == 200

    def test_weather(self, parsed):
        assert parsed["race"]["weather"] == "曇"

    def test_moisture(self, parsed):
        assert parsed["race"]["moisture"] == pytest.approx(3.2)

    def test_conditions_kept_raw(self, parsed):
        assert "電話投票コード" in parsed["race"]["conditions"]


class TestResultPageHorses:
    def test_all_rows_parsed(self, parsed):
        assert [r["horse_no"] for r in parsed["results"]] == [1, 2, 3]

    def test_winner(self, parsed):
        r = parsed["results"][0]
        assert r == {
            "horse_no": 1,
            "horse_id": "20190001234",
            "bracket": 1,
            "finish": 1,
            "status": "1",
            "horse_name": "テストホースア",
            "affiliation": "ばんえい",
            "sex": "牡",
            "age": 5,
            "weight_carried": 700,
            "jockey": "一号騎手",
            "trainer": "一号調教",
            "horse_weight": 950,
            "horse_weight_diff": 12,
            "time_str": "1:05.4",
            "time_sec": pytest.approx(65.4),
            "margin": "",
            "popularity": 2,
        }

    def test_apprentice_mark_stripped_from_jockey(self, parsed):
        # 元セルは "☆一号騎手 （ばんえい）"
        assert parsed["results"][0]["jockey"] == "一号騎手"

    def test_horse_id_absent_without_link(self, parsed):
        assert parsed["results"][1]["horse_id"] is None

    def test_negative_weight_diff(self, parsed):
        assert parsed["results"][1]["horse_weight_diff"] == -6

    def test_margin_kept(self, parsed):
        assert parsed["results"][1]["margin"] == "大差"

    def test_same_bracket_second_horse(self, parsed):
        # 馬番2と3はどちらも枠2
        assert parsed["results"][1]["bracket"] == 2
        assert parsed["results"][2]["bracket"] == 2

    def test_scratched_horse(self, parsed):
        r = parsed["results"][2]
        assert r["finish"] is None
        assert r["status"] == "中止"
        assert r["horse_weight"] is None
        assert r["horse_weight_diff"] is None
        assert r["time_sec"] is None
        assert r["popularity"] is None


class TestResultPagePayouts:
    def test_four_and_three_cell_rows(self, parsed):
        assert parsed["payouts"] == [
            {"bet_type": "単勝", "combination": "1", "amount": 340, "popularity": 2},
            {"bet_type": "複勝", "combination": "1", "amount": 110, "popularity": 2},
            {"bet_type": "複勝", "combination": "2", "amount": 130, "popularity": 1},
            {"bet_type": "馬連複", "combination": "1-2", "amount": 450, "popularity": 3},
        ]

    def test_row_without_yen_is_skipped(self, parsed):
        assert all(p["bet_type"] != "参考" for p in parsed["payouts"])


class TestResultPageUnfinished:
    def test_returns_none(self):
        assert parse_result_page(fixture("result_page_unfinished.html")) is None

    def test_empty_html_returns_none(self):
        assert parse_result_page("<html><body>準備中</body></html>") is None


class TestOddsPage:
    def test_all_horses(self, odds_rows):
        assert [r["horse_no"] for r in odds_rows] == [1, 2, 3]

    def test_win_and_place(self, odds_rows):
        assert odds_rows[0] == {
            "horse_no": 1,
            "horse_name": "テストホースア",
            "win_odds": pytest.approx(3.4),
            "place_min": pytest.approx(1.1),
            "place_max": pytest.approx(1.9),
        }

    def test_rowspan_collapsed_row(self, odds_rows):
        # 枠番セルが省略された行でも列がずれない
        assert odds_rows[2]["horse_name"] == "テストホースウ"
        assert odds_rows[2]["win_odds"] == pytest.approx(101.5)
        assert odds_rows[2]["place_max"] == pytest.approx(40.1)


class TestComboMatrix:
    def test_unordered_sorts_combination(self, matrix_unordered):
        assert matrix_unordered["1-2"] == (pytest.approx(12.3), None)
        assert matrix_unordered["2-3"] == (pytest.approx(45.6), None)

    def test_ordered_keeps_header_first(self):
        got = parse_matrix(fixture("combo_matrix.html"), ordered=True)
        assert "1-3" in got  # ヘッダ "1" + 相手 "3"
        assert got["1-3"][0] == pytest.approx(3.1)

    def test_range_captures_both_bounds(self, matrix_unordered):
        assert matrix_unordered["1-3"] == (pytest.approx(3.1), pytest.approx(5.2))

    def test_comma_separated_odds(self, matrix_unordered):
        assert matrix_unordered["2-4"][0] == pytest.approx(1234.5)


class TestSanrentanPage:
    def test_nbsp_separated_combination(self, sanrentan):
        assert sanrentan["1-2-3"] == (pytest.approx(123.4), None)

    def test_plain_combination(self, sanrentan):
        assert sanrentan["1-2-4"] == (pytest.approx(2345.6), None)

    def test_non_combination_row_skipped(self, sanrentan):
        assert len(sanrentan) == 2
