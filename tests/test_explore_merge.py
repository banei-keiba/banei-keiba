"""区分のまとめ方のテスト。

マスを消すと、別に公開した合計との引き算で値が割り出せる。そこで消さずに隣とまとめる
（設計書 §3）。ここが壊れると 30 件未満の集計がそのまま公開されるので、性質を乱数でも確かめる。
"""

import itertools
import random

import pytest

from banei.export.merge import is_coarsening, merge_bins, regroup, violations

FLOOR = 30


def test_no_violation_keeps_base_bins():
    counts = {(0,): [40], (1,): [0], (2,): [35]}
    assert merge_bins(counts, [3], floor=FLOOR) == [[[0], [1], [2]]]


def test_zero_cell_is_not_a_violation():
    # 期間帯に 1 件も無いマスは違反ではない（0 件と分かっても何も漏れない）
    counts = {(0,): [40, 0], (1,): [0, 35]}
    assert merge_bins(counts, [2], floor=FLOOR) == [[[0], [1]]]


def test_merges_with_smaller_neighbor():
    counts = {(0,): [100], (1,): [10], (2,): [50]}
    assert merge_bins(counts, [3], floor=FLOOR) == [[[0], [1, 2]]]


def test_tie_merges_with_previous_neighbor():
    counts = {(0,): [100], (1,): [10], (2,): [100]}
    assert merge_bins(counts, [3], floor=FLOOR) == [[[0, 1], [2]]]


def test_empty_neighbor_is_merged_last():
    # 0 件の隣とまとめても違反は解けない。先にまとめると実在しない幅の区分ができる
    counts = {(0,): [40], (1,): [5], (2,): [0], (3,): [0]}
    assert merge_bins(counts, [4], floor=FLOOR) == [[[0, 1], [2], [3]]]


def test_merges_axis_that_is_sparse_in_the_violating_band():
    # 全体では軸 0 の区分 1 が多い（1,050 件 > 軸 1 の区分 1 の 610 件）が、
    # 違反のある期間帯 1 では軸 0 の区分 1 が少ない（50 件 < 110 件）。期間帯 1 で比べる
    counts = {
        (0, 0): [0, 100], (0, 1): [0, 100],
        (1, 0): [500, 40], (1, 1): [500, 10],
    }
    assert merge_bins(counts, [2, 2], floor=FLOOR) == [[[0, 1]], [[0], [1]]]


def test_band_total_below_floor_raises():
    with pytest.raises(ValueError, match="まとめても"):
        merge_bins({(0,): [10], (1,): [5]}, [2], floor=FLOOR)


@pytest.mark.parametrize("seed", range(200))
def test_merged_cells_always_satisfy_the_rule(seed):
    rng = random.Random(seed)
    n_bins = [rng.randint(1, 6) for _ in range(rng.choice([1, 2]))]
    n_bands = rng.randint(1, 4)
    counts = {
        key: [rng.choice([0, 0, rng.randint(1, 29), rng.randint(30, 300)]) for _ in range(n_bands)]
        for key in itertools.product(*(range(n) for n in n_bins))
    }
    band_totals = [sum(ns[b] for ns in counts.values()) for b in range(n_bands)]
    if any(0 < t < FLOOR for t in band_totals):
        with pytest.raises(ValueError):
            merge_bins(counts, n_bins, floor=FLOOR)
        return

    groups = merge_bins(counts, n_bins, floor=FLOOR)

    # 各軸の区分は基本区分を順に、重複も欠けもなく覆う（隣とだけまとめた）
    for gs, n in zip(groups, n_bins, strict=True):
        assert [b for g in gs for b in g] == list(range(n))
    cells = regroup(counts, groups)
    assert violations(cells, FLOOR) == []
    for b in range(n_bands):
        assert sum(ns[b] for ns in cells.values()) == band_totals[b]


def test_start_groups_are_kept_when_no_violation():
    # 前回の版でまとめた区分は、違反が無くても分け直さない（細かくすると版の差で切れ端が出る）
    counts = {(0,): [40], (1,): [40], (2,): [40]}
    assert merge_bins(counts, [3], floor=FLOOR, start=[[[0, 1], [2]]]) == [[[0, 1], [2]]]


def test_merging_continues_from_start_groups():
    counts = {(0,): [100], (1,): [40], (2,): [10]}
    assert merge_bins(counts, [3], floor=FLOOR, start=[[[0, 1], [2]]]) == [[[0, 1, 2]]]


@pytest.mark.parametrize(("old", "new", "expected"), [
    ([[0], [1], [2]], [[0, 1], [2]], True),
    ([[0, 1], [2]], [[0, 1], [2]], True),
    ([[0, 1], [2]], [[0, 1, 2]], True),
    ([[0, 1], [2]], [[0], [1], [2]], False),  # 細かくなった
    ([[0, 1], [2]], [[0], [1, 2]], False),  # 交差した
])
def test_is_coarsening(old, new, expected):
    assert is_coarsening([old], [new]) is expected


@pytest.mark.parametrize("seed", range(100))
def test_merging_from_start_only_coarsens(seed):
    rng = random.Random(seed)
    n_bins = [rng.randint(1, 6) for _ in range(rng.choice([1, 2]))]
    counts = {
        key: [rng.choice([0, rng.randint(1, 29), rng.randint(30, 300)]) for _ in range(3)]
        for key in itertools.product(*(range(n) for n in n_bins))
    }
    if any(0 < sum(ns[b] for ns in counts.values()) < FLOOR for b in range(3)):
        return
    start = []
    for n in n_bins:  # 隣り合う区分をランダムにまとめた前回の区分
        cuts = [0] + sorted(rng.sample(range(1, n), rng.randint(0, n - 1))) + [n]
        start.append([list(range(a, b)) for a, b in itertools.pairwise(cuts)])

    groups = merge_bins(counts, n_bins, floor=FLOOR, start=start)

    assert is_coarsening(start, groups)
    assert violations(regroup(counts, groups), FLOOR) == []
