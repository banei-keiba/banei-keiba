"""特徴量まわりのテスト。ml エクストラが必要。"""

import pytest

pytest.importorskip("numpy", reason="ml エクストラ未導入")

import numpy as np  # noqa: E402

from banei.features.dataset import race_class  # noqa: E402


class TestRaceClass:
    @pytest.mark.parametrize(("name", "expected"), [
        ("Ｃ２", 0),
        ("Ｃ１", 1),
        ("Ｂ４", 2),
        ("Ｂ１", 5),
        ("Ａ２", 6),
        ("Ａ１", 7),
    ])
    def test_ladder(self, name, expected):
        assert race_class(name) == expected

    def test_class_with_group_suffix(self):
        assert race_class("Ｂ３－１") == 3

    def test_open(self):
        assert race_class("ばんえい記念（オープン）") == 8

    def test_selection_counts_as_open(self):
        assert race_class("選抜戦") == 8

    @pytest.mark.parametrize("name", [None, "", "新馬戦"])
    def test_unknown_is_nan(self, name):
        assert np.isnan(race_class(name))
