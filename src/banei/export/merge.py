"""区分のまとめ方（探索 UI 用）。DB に依存しない純粋な関数だけを置く。

各表は対象の出走をもれなく分け、期間帯ごとにすべてのマスが 0 件か floor 件以上になるまで
隣り合う区分をまとめる。マスを消すと、別に公開した合計との引き算で値が割り出せてしまう
（設計書 docs/superpowers/specs/2026-10-13-explore-ui-design.md §3）。
"""

Key = tuple[int, ...]  # 各軸の区分番号の組


def regroup(counts: dict[Key, list[int]], groups: list[list[list[int]]]) -> dict[Key, list[int]]:
    """基本区分ごとの数のリストを、まとめた区分ごとに要素ごと足し直す。"""
    index = [{b: gi for gi, g in enumerate(gs) for b in g} for gs in groups]
    out: dict[Key, list[int]] = {}
    for key, ns in counts.items():
        k = tuple(index[ax][b] for ax, b in enumerate(key))
        acc = out.setdefault(k, [0] * len(ns))
        for i, n in enumerate(ns):
            acc[i] += n
    return out


def violations(cells: dict[Key, list[int]], floor: int) -> list[tuple[int, int, Key]]:
    """0 < n < floor のマスを (n, 期間帯, マス) の昇順で返す。"""
    return sorted(
        (n, band, key)
        for key, ns in cells.items()
        for band, n in enumerate(ns)
        if 0 < n < floor
    )


def merge_bins(
    counts: dict[Key, list[int]],
    n_bins: list[int],
    *,
    floor: int,
    start: list[list[list[int]]] | None = None,
) -> list[list[list[int]]]:
    """規則を満たすまで区分をまとめ、軸ごとに「まとめた区分」の並びを返す。

    counts は基本区分の組 → 期間帯ごとの出走数。start（前回の版の区分）があればそこから、
    無ければ基本区分から始める。前回の区分から始めるのは、版をまたいで区分が細かくなったり
    交差したりすると、版と版の差でどの版でも検査していない切れ端が割り出せるため。
    手順（同じ入力なら同じ出力）:

    1. 違反マスのうち n が最小のものを選ぶ（同値なら期間帯 → 軸の順 → 区分の順）
    2. その期間帯で、違反マスが属する各軸の区分の出走数を比べ、少ない軸を選ぶ
       （同値なら先の軸）。区分が 1 つしか残っていない軸は選ばない
    3. その区分を、同じ期間帯で出走の少ない隣とまとめる（同値なら前の区分）。
       0 件の隣は後回し。0 件とまとめても違反は解けず、実在しない幅の区分ができる

    ある期間帯の合計そのものが floor 未満だと、全部まとめても満たせないので ValueError。
    """
    if start is None:
        groups = [[[b] for b in range(n)] for n in n_bins]
    else:
        groups = [[list(g) for g in gs] for gs in start]
    while True:
        cells = regroup(counts, groups)
        found = violations(cells, floor)
        if not found:
            return groups
        _, band, key = found[0]
        totals = [[0] * len(gs) for gs in groups]
        for k, ns in cells.items():
            for ax, gi in enumerate(k):
                totals[ax][gi] += ns[band]
        axes = [ax for ax in range(len(groups)) if len(groups[ax]) > 1]
        if not axes:
            raise ValueError(
                f"期間帯 {band} の合計が {floor} 件未満で、区分をまとめても満たせない")
        ax = min(axes, key=lambda a: (totals[a][key[a]], a))
        gi = key[ax]
        neighbors = [j for j in (gi - 1, gi + 1) if 0 <= j < len(groups[ax])]
        j = min(neighbors, key=lambda j: (totals[ax][j] == 0, totals[ax][j], j))
        lo, hi = min(gi, j), max(gi, j)
        groups[ax][lo:hi + 1] = [groups[ax][lo] + groups[ax][hi]]


def is_coarsening(old: list[list[list[int]]], new: list[list[list[int]]]) -> bool:
    """new の各軸の区分が、old の隣り合う区分をまとめたもの（同じでもよい）か。

    どちらも基本区分を順に覆うので、new の区分の境目がすべて old の境目にあればよい。
    """
    def flat(gs):
        return [b for g in gs for b in g]

    return len(old) == len(new) and all(
        flat(o) == flat(n) and {g[0] for g in n} <= {g[0] for g in o}
        for o, n in zip(old, new, strict=False)
    )
