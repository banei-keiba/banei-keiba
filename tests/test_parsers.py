"""スクレイパーの純粋関数に対するテスト。

HTML 全体のゴールデンテスト（fixtures 使用）は Phase 1 で追加する。
"""

import pytest

from banei.ingest.combo_odds import norm_combo
from banei.ingest.odds import parse_float
from banei.ingest.results import month_range, parse_int, parse_time


class TestParseInt:
    def test_plain(self):
        assert parse_int("5") == 5

    def test_comma(self):
        assert parse_int("1,234円") == 1234

    def test_negative(self):
        assert parse_int("(-8)") == -8

    def test_no_digits(self):
        assert parse_int("―") is None


class TestParseTime:
    def test_with_minutes(self):
        assert parse_time("1:05.4") == pytest.approx(65.4)

    def test_seconds_only(self):
        assert parse_time("42.7") == pytest.approx(42.7)

    def test_surrounding_space(self):
        assert parse_time("  1:00.0 ") == pytest.approx(60.0)

    def test_invalid(self):
        assert parse_time("取消") is None


class TestParseFloat:
    def test_decimal(self):
        assert parse_float("12.3") == pytest.approx(12.3)

    def test_comma(self):
        assert parse_float("1,024.5") == pytest.approx(1024.5)

    def test_invalid(self):
        assert parse_float("---") is None


class TestNormCombo:
    def test_ordered_keeps_order(self):
        assert norm_combo(["8", "2"], ordered=True) == "8-2"

    def test_unordered_sorts_numerically(self):
        assert norm_combo(["8", "2"], ordered=False) == "2-8"

    def test_unordered_triple_not_lexicographic(self):
        # 文字列ソートだと "10" < "2" になってしまうため数値順であることを確認する
        assert norm_combo(["10", "2", "4"], ordered=False) == "2-4-10"


class TestMonthRange:
    def test_crosses_year_boundary(self):
        assert list(month_range("2024-11", "2025-02")) == [
            (2024, 11), (2024, 12), (2025, 1), (2025, 2)]

    def test_single_month(self):
        assert list(month_range("2024-05", "2024-05")) == [(2024, 5)]

    def test_end_before_start_is_empty(self):
        assert list(month_range("2024-05", "2024-04")) == []
