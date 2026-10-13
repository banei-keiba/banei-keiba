# Phase 3 探索 UI 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 人を除く 8 軸の 1 軸・2 軸クロス表（36 表）を export で集計し、73 の静的ページとして公開する。

**Architecture:** Python の `src/banei/export/explore.py` が締めたシーズンまでの出走を集計し、
期間帯ごとに全マスが 0 件か 30 件以上になるまで区分を隣とまとめて（`merge.py`）、
`web/src/data/explore/*.json` に書く。違反は既存の `export.build()` の `PolicyError` で止める。
Astro は `getStaticPaths` で JSON からページを作る。JS は配信しない。

**Tech Stack:** Python 3.13 / SQLite / pytest / ruff（uv）、Astro 7、Node 24（`node --test`）

**Spec:** `docs/superpowers/specs/2026-10-13-explore-ui-design.md`（必ず併せて読むこと）

## Global Constraints

- 公開物は `src/banei/export/` を唯一の出口にする。検査は実行時に走らせ、違反は `PolicyError` で書き出し全体を止める
- 30 件の下限は `banei.export.aggregates.MIN_GROUP_SIZE` を使う（数値を直書きしない）
- `FIRST_RECENT_SEASON = 2023`（初回公開の直近 3 シーズンの始まり。後から変えない）
- シーズンは 4/1〜翌 3/31、開始年で呼ぶ。締めは 5/1。日付は JST で明示的に判定する
- 出力 JSON に生成時刻を入れない（入れると検査 3 が成り立たない）
- 馬番のキーは `post`（`horse_no` は `FORBIDDEN_KEYS` に当たる）
- Web は JS ゼロ（`<script>` を書かない）。色は `web/src/styles/global.css` のトークンだけを使う
- 濃淡は `--data` を `--card` に 12 / 24 / 36 / 48% 混ぜた 4 段階。出走数 100 未満のマスには付けない
- テストは合成データのみ（実ページの HTML・実 DB を使わない）
- `.db` をコミットしない。`data/` は .gitignore 済み
- ドキュメント・コメント・コミットメッセージは日本語。コミットメッセージは「なぜ」を書く
- git commit は GPG 署名必須。`Inappropriate ioctl for device` で失敗したら、ユーザーに
  `echo test | gpg --clearsign > /dev/null` を実行してもらう。署名を外さない
- push はユーザーの承認を得てから（この計画では push しない）
- 各タスクの最後に `uv run ruff check . && uv run pytest -q` が通ること
- コミットメッセージの末尾に `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` を付ける

## Review Focus

- 想定外の軸の値（新しい天候「霧」・11 番人気など）→ 黙って別の区分に入れず、検査 2 で書き出しが止まる（Task 2・3 でテスト）
- 前回の出力 JSON が壊れている・手で編集されている → 上書きせず `PolicyError` で止まる（Task 4 でテスト）
- 締めたシーズンの出走が 0 件の DB（既存の公開ポリシーテストの小さな DB）→ 探索 UI の出力を作らず、既存の集計は通る（Task 3 でテスト。既存の `test_clean_build_succeeds` も守る）
- ある期間帯の合計そのものが 30 件未満 → まとめ切れないことを違反として報告し、無限ループや素の例外で落ちない（Task 1・3 でテスト）
- 表のマスが全部同じ値・出走数 100 以上のマスが 1 つも無い → 濃淡の計算で 0 除算しない（Task 6 でテスト）

---

## File Structure

| ファイル | 責務 |
|---|---|
| `src/banei/export/merge.py`（新規） | 区分のまとめ方。DB に依存しない純粋な関数 |
| `src/banei/export/explore.py`（新規） | 軸の定義・締め・対象出走の集計・表の組み立て・検査 1〜3 |
| `src/banei/export/__init__.py`（変更） | `build()` に探索 UI の表を組み込む |
| `src/banei/config.py`（変更） | `JST` をここへ移す（ingest と export の両方が使う） |
| `src/banei/ingest/results.py`（変更） | `JST` を config から import する |
| `tests/test_explore_merge.py`（新規） | merge.py のテスト |
| `tests/test_explore.py`（新規） | explore.py と export への組み込みのテスト |
| `tests/test_heat_contrast.py`（新規） | 濃淡の上の文字のコントラスト検査 |
| `web/src/lib/heat.ts`・`heat.test.ts`（新規） | 濃淡の段階の計算とそのテスト |
| `web/src/lib/explore.ts`（新規） | JSON の型・軸と指標の名前・URL の決まり・JSON の読み込み |
| `web/src/components/ValueCell.astro`（新規） | 率と出走数を並べたマス |
| `web/src/components/CrossTable.astro`（新規） | 2 軸の表（1 指標） |
| `web/src/components/ExploreMatrix.astro`（新規） | 指標のタブ（CSS のみ） |
| `web/src/components/ExploreNav.astro`（新規） | 軸・期間の切り替えリンク |
| `web/src/components/ExploreNotes.astro`（新規） | 共通の注記 |
| `web/src/pages/explore/index.astro`（新規） | 入口 |
| `web/src/pages/explore/[axis]/[period].astro`（新規） | 1 軸のページ |
| `web/src/pages/explore/[a]/[b]/[period].astro`（新規） | 2 軸のページ |
| `web/src/styles/global.css`（変更） | 探索 UI のスタイル（濃淡・タブ・表） |
| `web/src/layouts/Base.astro`（変更） | ナビに「探索」 |
| `web/src/data/explore/*.json`（生成物） | 36 表。日次ワークフローがコミットする |
| `docs/architecture.md`・`CLAUDE.md`（変更） | 方針と仕組みの記録 |

---

### Task 1: 区分のまとめ方（merge.py）

**Files:**
- Create: `src/banei/export/merge.py`
- Test: `tests/test_explore_merge.py`

**Interfaces:**
- Produces:
  - `Key = tuple[int, ...]`（各軸の区分番号の組）
  - `regroup(counts: dict[Key, list[int]], groups: list[list[list[int]]]) -> dict[Key, list[int]]` — 基本区分ごとの数のリストを、まとめた区分ごとに要素ごと足し直す（数のリストは期間帯ごとの出走数でも、集計値 6 要素でもよい）
  - `violations(cells: dict[Key, list[int]], floor: int) -> list[tuple[int, int, Key]]` — `0 < n < floor` の `(n, リストの位置, マス)` を昇順で
  - `merge_bins(counts: dict[Key, list[int]], n_bins: list[int], *, floor: int) -> list[list[list[int]]]` — 軸ごとに「まとめた区分（基本区分番号のリスト）」の並びを返す。まとめ切れなければ `ValueError`（メッセージに「まとめても」を含む）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_explore_merge.py`:

```python
"""区分のまとめ方のテスト。

マスを消すと、別に公開した合計との引き算で値が割り出せる。そこで消さずに隣とまとめる
（設計書 §3）。ここが壊れると 30 件未満の集計がそのまま公開されるので、性質を乱数でも確かめる。
"""

import itertools
import random

import pytest

from banei.export.merge import merge_bins, regroup, violations

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
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest tests/test_explore_merge.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'banei.export.merge'`）

- [ ] **Step 3: 実装する**

`src/banei/export/merge.py`:

```python
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
    counts: dict[Key, list[int]], n_bins: list[int], *, floor: int
) -> list[list[list[int]]]:
    """規則を満たすまで区分をまとめ、軸ごとに「まとめた区分」の並びを返す。

    counts は基本区分の組 → 期間帯ごとの出走数。手順（同じ入力なら同じ出力）:

    1. 違反マスのうち n が最小のものを選ぶ（同値なら期間帯 → 軸の順 → 区分の順）
    2. その期間帯で、違反マスが属する各軸の区分の出走数を比べ、少ない軸を選ぶ
       （同値なら先の軸）。区分が 1 つしか残っていない軸は選ばない
    3. その区分を、同じ期間帯で出走の少ない隣とまとめる（同値なら前の区分）。
       0 件の隣は後回し。0 件とまとめても違反は解けず、実在しない幅の区分ができる

    ある期間帯の合計そのものが floor 未満だと、全部まとめても満たせないので ValueError。
    """
    groups = [[[b] for b in range(n)] for n in n_bins]
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
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest tests/test_explore_merge.py -q`
Expected: PASS（207 passed）

- [ ] **Step 5: 全体を確かめてコミット**

Run: `uv run ruff check . && uv run pytest -q`
Expected: すべて PASS

```bash
git add src/banei/export/merge.py tests/test_explore_merge.py
git commit -F - <<'EOF'
探索 UI の区分をまとめる処理を足す

30 件未満のマスを消すだけだと、別に公開した合計との引き算で値が割り出せる
（実データで 289 行）。消さずに隣の区分とまとめ、各表が対象の出走をもれなく
分けた状態を保つ。0 件の隣を先にまとめると違反が解けないまま実在しない幅の
区分ができるので後回しにする。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 2: 対象の出走と基本区分の集計（explore.py 前半）

**Files:**
- Modify: `src/banei/config.py`（`JST` を追加）
- Modify: `src/banei/ingest/results.py:16`・`:22`（`JST` を config から import）
- Create: `src/banei/export/explore.py`
- Test: `tests/test_explore.py`

**Interfaces:**
- Consumes: なし
- Produces（`banei.export.explore`）:
  - 定数 `FIRST_RECENT_SEASON = 2023`、`RECENT_SEASONS = 3`、`CLOSE_MONTH = 5`、`SEASON_START_MONTH = 4`
  - 集計値の位置 `N, WIN, TOP2, PLACE, WIN_PAY, PLACE_PAY = range(6)`
  - `@dataclass(frozen=True) class Axis(key: str, name: str, sql: str, bins=(), names=(), unit="")`、プロパティ `n_bins: int`、メソッド `label(group: list[int]) -> str`
  - `AXES: tuple[Axis, ...]`（並びは popularity, post, weight_diff, age, sex, moisture, weather, month）
  - `_now() -> dt.datetime`（テストで差し替える）、`today_jst() -> dt.date`、`through_season(today: dt.date) -> int`、`band_of(season: int) -> int`
  - `population(con: sqlite3.Connection, through: int) -> dict[int, int]`（シーズン → 対象出走数）
  - `load_cells(con: sqlite3.Connection, through: int) -> dict[tuple[int, ...], list[int]]`（`(シーズン, 8 軸の基本区分番号…)` → `[N, WIN, TOP2, PLACE, WIN_PAY, PLACE_PAY]`）
  - `banei.config.JST`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_explore.py`（このファイルは Task 3・4 で追記する）:

```python
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
        ("weather", [1, 2], "曇・雨・雪"),
        ("month", [0, 1], "4〜5月"),
        ("month", [8, 9], "12〜1月"),
    ])
    def test_label(self, key, group, label):
        axis = next(a for a in explore.AXES if a.key == key)
        assert axis.label(group) == label
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest tests/test_explore.py -q`
Expected: FAIL（`ImportError: cannot import name 'explore'`）

- [ ] **Step 3: JST を config へ移す**

`src/banei/config.py` の `import os` の直前に `import datetime as dt` を足し、末尾に追記:

```python

# 日付の判定（開催日・探索 UI の締め）は JST で明示的に行う。GitHub ランナーのローカル時刻は
# UTC なので、ローカル日付に頼ると手元では正しくランナーでだけずれる（CLAUDE.md「環境まわり」）。
JST = dt.timezone(dt.timedelta(hours=9), "JST")
```

`src/banei/ingest/results.py`:
- `from banei.config import RACES_DB, REQUEST_INTERVAL` → `from banei.config import JST, RACES_DB, REQUEST_INTERVAL`
- `JST = dt.timezone(dt.timedelta(hours=9), "JST")` の行を削除する（`dt` は `_now` で使うので import は残す）

- [ ] **Step 4: explore.py の前半を実装する**

`src/banei/export/explore.py`:

```python
"""探索 UI 用のクロス表。

設計: docs/superpowers/specs/2026-10-13-explore-ui-design.md

- 対象は締めたシーズンまでの出走。シーズンは 4/1〜翌 3/31 で、締めは 5/1。
  日次収集が直近 30 日を取り直すので、取りこぼしが埋まるのを待ってから締める。
  毎日実行しても、出力は締めが進む年 1 回しか変わらない
- 各表は対象の出走をもれなく分ける。マスを消すと、別に公開した合計との引き算で値が
  割り出せるため、規則を満たさない区分は隣とまとめる（merge.py）
- 規則は「期間帯ごとに全マスが 0 件か 30 件以上」。期間帯は版と版の差で切り出される単位
"""

import datetime as dt
import sqlite3
from dataclasses import dataclass

from banei.config import JST

# 初回公開（2025 シーズンまで）の直近 3 シーズンの始まり。これより前のシーズンは
# 1 つの期間帯にまとめる。版の差で切り出される単位を決めているので、後から変えては
# いけない（変えると、過去の版との差で 30 件未満の集計が切り出せてしまう）。
FIRST_RECENT_SEASON = 2023
RECENT_SEASONS = 3
CLOSE_MONTH = 5  # この月の 1 日に前シーズンを締める
SEASON_START_MONTH = 4

# 各マスの集計値の並び。merge.regroup で要素ごとに足し合わせるのでリストで持つ
N, WIN, TOP2, PLACE, WIN_PAY, PLACE_PAY = range(6)


@dataclass(frozen=True)
class Axis:
    key: str  # JSON のキーと URL
    name: str  # 表示名
    sql: str  # 基本区分の番号（0 始まり）。想定外の値は NULL
    bins: tuple[tuple[str | None, str | None], ...] = ()  # 範囲の軸: (下限, 上限)
    names: tuple[str, ...] = ()  # 名義の軸: 区分名
    unit: str = ""

    @property
    def n_bins(self) -> int:
        return len(self.bins) or len(self.names)

    def label(self, group: list[int]) -> str:
        """まとめた区分の表示名。範囲の軸は「先頭の下限〜末尾の上限」、名義の軸は「・」でつなぐ。"""
        if self.names:
            return "・".join(self.names[i] for i in group)
        lo, hi = self.bins[group[0]][0], self.bins[group[-1]][1]
        if lo == hi:
            return f"{lo}{self.unit}"
        if hi is None:
            return f"{lo}{self.unit}〜"
        if lo is None:
            return f"〜{hi}{self.unit}"
        return f"{lo}〜{hi}{self.unit}"


def _each(values) -> tuple[tuple[str, str], ...]:
    return tuple((str(v), str(v)) for v in values)


# 並びは URL 上の軸の順でもある。同じ組み合わせが 2 つの URL にならないよう固定する。
# まとめるときは隣とだけまとめるので、名義の軸も並び順に意味がある。
AXES: tuple[Axis, ...] = (
    Axis("popularity", "人気",
         "CASE WHEN s.popularity BETWEEN 1 AND 10 THEN s.popularity - 1 END",
         bins=_each(range(1, 11))),
    # horse_no は aggregates.FORBIDDEN_KEYS に当たる（生データの個体キーと同じ名前を使わない）
    Axis("post", "馬番",
         "CASE WHEN s.horse_no BETWEEN 1 AND 10 THEN s.horse_no - 1 END",
         bins=_each(range(1, 11))),
    Axis("weight_diff", "重量差",
         "CASE WHEN s.wd = 0 THEN 0 WHEN s.wd <= 10 THEN 1 WHEN s.wd <= 20 THEN 2"
         " WHEN s.wd <= 30 THEN 3 WHEN s.wd > 30 THEN 4 END",
         bins=(("0", "0"), ("1", "10"), ("11", "20"), ("21", "30"), ("31", None)),
         unit="kg"),
    Axis("age", "馬齢",
         "CASE WHEN s.age BETWEEN 2 AND 9 THEN s.age - 2 WHEN s.age >= 10 THEN 8 END",
         bins=(*_each(range(2, 10)), ("10", None)), unit="歳"),
    # セン を 牡 の隣に置く
    Axis("sex", "性別",
         "CASE s.sex WHEN '牝' THEN 0 WHEN '牡' THEN 1 WHEN 'セン' THEN 2 END",
         names=("牝", "牡", "セン")),
    Axis("moisture", "馬場水分",
         "CASE WHEN ra.moisture < 0 THEN NULL WHEN ra.moisture < 1.0 THEN 0"
         " WHEN ra.moisture < 1.5 THEN 1 WHEN ra.moisture < 2.0 THEN 2"
         " WHEN ra.moisture < 2.5 THEN 3 WHEN ra.moisture < 3.0 THEN 4"
         " WHEN ra.moisture >= 3.0 THEN 5 END",
         bins=((None, "0.9"), ("1.0", "1.4"), ("1.5", "1.9"), ("2.0", "2.4"),
               ("2.5", "2.9"), ("3.0", None))),
    Axis("weather", "天候",
         "CASE WHEN ra.weather = '晴' THEN 0 WHEN ra.weather = '曇' THEN 1"
         " WHEN ra.weather IN ('小雨', '雨', '小雪', '雪') THEN 2 END",
         names=("晴", "曇", "雨・雪")),
    # シーズン順（4 月 = 0 … 3 月 = 11）。3 月と 4 月は隣ではない
    Axis("month", "月",
         "(CAST(substr(s.race_date, 6, 2) AS INTEGER) + 8) % 12",
         bins=_each([*range(4, 13), 1, 2, 3]), unit="月"),
)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def today_jst() -> dt.date:
    return _now().astimezone(JST).date()


def through_season(today: dt.date) -> int:
    """締めたシーズンのうち最新のもの。Y 年 5/1 からは Y-1 シーズン（Y-1/4/1〜Y/3/31）まで。"""
    return today.year - 1 if today.month >= CLOSE_MONTH else today.year - 2


def band_of(season: int) -> int:
    """期間帯。FIRST_RECENT_SEASON より前は 1 つにまとめ、以後は 1 シーズンずつ。"""
    return max(season, FIRST_RECENT_SEASON - 1)


# 対象の出走: 取消・除外を除く（中止・失格は馬券が外れ扱いなので含める）。
# 複勝の払戻が無いレースは複勝の指標が定義できないので除く（3〜4 頭立ての数レース）。
# 重量差はこの範囲（取消・除外を除いた出走馬）の中で最も軽い馬との差。
_STARTERS = """
WITH s AS (
  SELECT r.*,
         CAST(substr(r.race_date, 1, 4) AS INTEGER)
           - (CAST(substr(r.race_date, 6, 2) AS INTEGER) < 4) AS season,
         r.weight_carried - MIN(r.weight_carried)
           OVER (PARTITION BY r.race_date, r.race_no) AS wd
  FROM results r
  WHERE COALESCE(r.status, '') NOT IN ('取消', '除外')
    AND r.race_date < :end
    AND EXISTS (SELECT 1 FROM payouts p
                WHERE p.race_date = r.race_date AND p.race_no = r.race_no
                  AND p.bet_type = '複勝')
)
"""


def _end(through: int) -> str:
    return f"{through + 1}-{SEASON_START_MONTH:02d}-01"


def population(con: sqlite3.Connection, through: int) -> dict[int, int]:
    """シーズンごとの対象出走数。軸の値に関係なく数える（検査 2 の基準）。"""
    rows = con.execute(_STARTERS + "SELECT season, COUNT(*) FROM s GROUP BY season",
                       {"end": _end(through)})
    return dict(rows.fetchall())


def load_cells(con: sqlite3.Connection, through: int) -> dict[tuple[int, ...], list[int]]:
    """(シーズン, 各軸の基本区分…) → 集計値 [N, WIN, TOP2, PLACE, WIN_PAY, PLACE_PAY]。

    軸の値が想定外（NULL）の出走は入れない。黙って別の区分に入れると集計が歪むので、
    検査 2（マスの合計 = 対象出走数）で止める。
    """
    axis_cols = ", ".join(f"{a.sql} AS {a.key}" for a in AXES)
    sql = _STARTERS + f"""
    SELECT s.season, {axis_cols},
           COALESCE(s.finish = 1, 0), COALESCE(s.finish <= 2, 0),
           pp.amount IS NOT NULL, COALESCE(pw.amount, 0), COALESCE(pp.amount, 0)
    FROM s
    JOIN races ra ON ra.race_date = s.race_date AND ra.race_no = s.race_no
    LEFT JOIN payouts pw ON pw.race_date = s.race_date AND pw.race_no = s.race_no
         AND pw.bet_type = '単勝' AND CAST(pw.combination AS INTEGER) = s.horse_no
    LEFT JOIN payouts pp ON pp.race_date = s.race_date AND pp.race_no = s.race_no
         AND pp.bet_type = '複勝' AND CAST(pp.combination AS INTEGER) = s.horse_no
    """
    cells: dict[tuple[int, ...], list[int]] = {}
    k = len(AXES)
    for row in con.execute(sql, {"end": _end(through)}):
        season, idx, values = row[0], row[1:1 + k], row[1 + k:]
        if any(v is None for v in idx):
            continue
        acc = cells.setdefault((season, *idx), [0] * 6)
        acc[N] += 1
        for i, v in enumerate(values, start=WIN):
            acc[i] += v
    return cells
```

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest tests/test_explore.py tests/test_results_scrape.py -q`
Expected: PASS（JST を移しても開催日の判定テストが通る）

- [ ] **Step 6: 全体を確かめてコミット**

Run: `uv run ruff check . && uv run pytest -q`
Expected: すべて PASS

```bash
git add src/banei/config.py src/banei/ingest/results.py src/banei/export/explore.py tests/test_explore.py
git commit -F - <<'EOF'
探索 UI の対象出走と基本区分を集計する

回収率の分母に入れるべき中止・失格を含め、返還になる取消・除外を除く。
複勝率は 7 頭以下で 2 着までになるので、着順ではなく払戻データで数える。
軸の値が想定外の出走は別の区分に紛れ込ませず、マスから外して検査で止める。
締めの日付判定は ingest と同じく JST で行うので、JST を config に移した。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 3: 表の組み立てと検査 1・2（explore.py 後半）

**Files:**
- Modify: `src/banei/export/explore.py`
- Test: `tests/test_explore.py`（追記）

**Interfaces:**
- Consumes: Task 1 の `merge_bins` / `regroup` / `violations`、Task 2 の `AXES` / `population` / `load_cells` / `band_of` / `through_season` / 定数
- Produces（`banei.export.explore`）:
  - `TABLES: tuple[tuple[Axis, ...], ...]`（1 軸 8 + 2 軸 28 = 36）
  - `table_name(axes: tuple[Axis, ...]) -> str`（`"explore/popularity__moisture"`）
  - `build_table(axes, base, pop, through) -> tuple[dict, list[str]]`（まとめ切れなければ `ValueError`）
  - `build(con: sqlite3.Connection, today: dt.date) -> tuple[dict[str, dict], list[str]]`（`{出力名: 中身}` と違反の一覧）
  - `flatten(payload: dict) -> list[dict]`（公開ポリシー検査にかける行）
  - JSON の形は設計書 §5 のとおり（`axes` / `through_season` / `bins` / `periods.{all,recent3}.{first_season,last_season,total,cells,margins}`）。各行の指標キーは `n, win_rate, top2_rate, place_rate, win_roi, place_roi`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_explore.py` の末尾に追記:

```python
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
                            lambda counts, n_bins, floor: [[[b] for b in range(n)] for n in n_bins])
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
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest tests/test_explore.py -q`
Expected: FAIL（`AttributeError: module 'banei.export.explore' has no attribute 'build'`）

- [ ] **Step 3: 実装する**

`src/banei/export/explore.py` の import を次に置き換える:

```python
import datetime as dt
import itertools
import sqlite3
from dataclasses import dataclass

from banei.config import JST
from banei.export.aggregates import MIN_GROUP_SIZE
from banei.export.merge import merge_bins, regroup, violations
```

`load_cells` の後に追記:

```python


# 1 軸 8 表 + 2 軸 28 表
TABLES: tuple[tuple[Axis, ...], ...] = (
    *((a,) for a in AXES),
    *itertools.combinations(AXES, 2),
)


def table_name(axes: tuple[Axis, ...]) -> str:
    return "explore/" + "__".join(a.key for a in axes)


def _add(acc: list[int], m: list[int]) -> None:
    for i, v in enumerate(m):
        acc[i] += v


def _metrics(m: list[int]) -> dict:
    n = m[N]
    return {
        "n": n,
        "win_rate": round(100 * m[WIN] / n, 1),
        "top2_rate": round(100 * m[TOP2] / n, 1),
        "place_rate": round(100 * m[PLACE] / n, 1),
        # 払戻は 100 円あたりなので、払戻合計 ÷ (n × 100 円) × 100% = 払戻合計 ÷ n
        "win_roi": round(m[WIN_PAY] / n, 1),
        "place_roi": round(m[PLACE_PAY] / n, 1),
    }


def _period_payload(axes, groups, merged, lo: int, hi: int) -> dict:
    total = [0] * 6
    for m in merged.values():
        _add(total, m)
    out = {
        "first_season": lo,
        "last_season": hi,
        "total": _metrics(total) if total[N] else None,
        # 0 件のマスは入れない（画面では「—」）
        "cells": [
            {**{a.key: a.label(groups[i][key[i]]) for i, a in enumerate(axes)}, **_metrics(m)}
            for key, m in sorted(merged.items())
        ],
    }
    if len(axes) == 2:
        # 全体の行と列。まとめた区分でのマスの合計なので、新たな数字は出ない
        out["margins"] = {}
        for i, a in enumerate(axes):
            side: dict[int, list[int]] = {}
            for key, m in merged.items():
                _add(side.setdefault(key[i], [0] * 6), m)
            out["margins"][a.key] = [
                {a.key: a.label(groups[i][g]), **_metrics(m)} for g, m in sorted(side.items())]
    return out


def build_table(
    axes: tuple[Axis, ...],
    base: dict[tuple[int, ...], list[int]],
    pop: dict[int, int],
    through: int,
) -> tuple[dict, list[str]]:
    """1 つの表を作る。戻り値は (JSON にする中身, 検査 1・2 の違反)。

    区分をまとめ切れない（ある期間帯の合計そのものが 30 件未満）ときは ValueError。
    """
    name = table_name(axes)
    pos = [AXES.index(a) for a in axes]
    by_season: dict[int, dict[tuple[int, ...], list[int]]] = {}
    for (season, *idx), m in base.items():
        key = tuple(idx[p] for p in pos)
        _add(by_season.setdefault(season, {}).setdefault(key, [0] * 6), m)

    # まとめ方は期間帯ごとの出走数で決め、両方の期間で同じものを使う
    bands = sorted({band_of(s) for s in pop})
    counts: dict[tuple[int, ...], list[int]] = {}
    for season, cells in by_season.items():
        b = bands.index(band_of(season))
        for key, m in cells.items():
            counts.setdefault(key, [0] * len(bands))[b] += m[N]
    groups = merge_bins(counts, [a.n_bins for a in axes], floor=MIN_GROUP_SIZE)

    # 検査 1: まとめた後、どの期間帯でも全マスが 0 か 30 以上
    problems = [
        f"{name}: 期間帯 {bands[b]} のマス {key} が {n} 件（0 か {MIN_GROUP_SIZE} 以上が必要）"
        for n, b, key in violations(regroup(counts, groups), MIN_GROUP_SIZE)
    ]

    spans = {"all": (min(pop), through), "recent3": (through - RECENT_SEASONS + 1, through)}
    periods = {}
    for period, (lo, hi) in spans.items():
        summed: dict[tuple[int, ...], list[int]] = {}
        for season, cells in by_season.items():
            if lo <= season <= hi:
                for key, m in cells.items():
                    _add(summed.setdefault(key, [0] * 6), m)
        merged = regroup(summed, groups)
        # 検査 2: マスの合計が対象出走数と一致する（もれなく分けている）
        expected = sum(n for s, n in pop.items() if lo <= s <= hi)
        got = sum(m[N] for m in merged.values())
        if got != expected:
            problems.append(f"{name}（{period}）: マスの合計 {got} が対象出走数 {expected} と"
                            "一致しない（軸の値が想定外の出走がある）")
        periods[period] = _period_payload(axes, groups, merged, lo, hi)

    payload = {
        "axes": [a.key for a in axes],
        "through_season": through,
        "bins": {a.key: [a.label(g) for g in groups[i]] for i, a in enumerate(axes)},
        "periods": periods,
    }
    return payload, problems


def build(con: sqlite3.Connection, today: dt.date) -> tuple[dict[str, dict], list[str]]:
    """全表を作る。戻り値は ({出力名: 中身}, 違反の一覧)。

    締めたシーズンの出走が 1 件も無ければ何も作らない（テスト用の小さな DB など）。
    """
    through = through_season(today)
    if through - RECENT_SEASONS + 1 < FIRST_RECENT_SEASON:
        return {}, [f"直近 {RECENT_SEASONS} シーズンが {FIRST_RECENT_SEASON} より前から始まる"
                    f"（締め {through}）。FIRST_RECENT_SEASON の設定か日付が誤っている"]
    pop = population(con, through)
    if not pop:
        return {}, []
    base = load_cells(con, through)
    out: dict[str, dict] = {}
    problems: list[str] = []
    for axes in TABLES:
        name = table_name(axes)
        try:
            payload, found = build_table(axes, base, pop, through)
        except ValueError as e:
            problems.append(f"{name}: {e}")
            continue
        out[name] = payload
        problems += found
    return out, problems


def flatten(payload: dict) -> list[dict]:
    """公開ポリシーの検査（aggregates.policy_violations）にかける行。マス・全体の行と列・合計。"""
    rows: list[dict] = []
    for p in payload["periods"].values():
        rows += p["cells"]
        for side in p.get("margins", {}).values():
            rows += side
        if p["total"] is not None:
            rows.append(p["total"])
    return rows
```

- [ ] **Step 4: 通ることを確かめる**

Run: `uv run pytest tests/test_explore.py -q`
Expected: PASS

- [ ] **Step 5: 全体を確かめてコミット**

Run: `uv run ruff check . && uv run pytest -q`
Expected: すべて PASS

```bash
git add src/banei/export/explore.py tests/test_explore.py
git commit -F - <<'EOF'
探索 UI の表を組み立てて検査する

1 軸 8 表・2 軸 28 表を作り、まとめ方は期間帯ごとの出走数で決めて両方の期間で
共有する。期間で変えると、全期間と直近 3 シーズンの差で小さなマスが切り出せる。
まとめ方の処理とは別に、書き出す前に「全マスが期間帯ごとに 0 か 30 以上」と
「マスの合計が対象出走数と一致する」を確かめる。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 4: export への組み込みと検査 3

**Files:**
- Modify: `src/banei/export/explore.py`（`previous_problems` を追加）
- Modify: `src/banei/export/__init__.py`（全体を置き換え）
- Test: `tests/test_explore.py`（追記）

**Interfaces:**
- Consumes: Task 3 の `explore.build` / `explore.flatten`、Task 2 の `explore.today_jst`
- Produces:
  - `explore.previous_problems(name: str, payload: dict, previous_dir: Path) -> list[str]`
  - `export.build(db_path=RACES_DB, today: dt.date | None = None, previous_dir: Path | str | None = None) -> dict[str, object]`（探索 UI の表は `explore/…` という出力名で入る）
  - `export.run(db_path=RACES_DB, out_dir=DEFAULT_OUT_DIR, today: dt.date | None = None) -> None`（`out_dir/explore/*.json` も書く。前回の出力として `out_dir` を使う）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_explore.py` の import を次に置き換える:

```python
import datetime as dt
import json
import sqlite3

import pytest

from banei import export
from banei.db.schema import RACES_SCHEMA
from banei.export import explore
```

末尾に追記:

```python
def identity_merge(counts, n_bins, floor):
    """まとめ方が壊れた状態（何もまとめない）。"""
    return [[[b] for b in range(n)] for n in n_bins]


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
```

- [ ] **Step 2: 失敗を確かめる**

Run: `uv run pytest tests/test_explore.py -q -k TestExport`
Expected: FAIL（`TypeError: run() got an unexpected keyword argument 'today'`）

- [ ] **Step 3: previous_problems を実装する**

`src/banei/export/explore.py` の import に `import json` と `from pathlib import Path` を足す
（並びは `import datetime as dt` / `import itertools` / `import json` / `import sqlite3` /
`from dataclasses import dataclass` / `from pathlib import Path`）。末尾に追記:

```python


def previous_problems(name: str, payload: dict, previous_dir: Path) -> list[str]:
    """検査 3: 締めたシーズンが同じなのに、前回の出力と内容が違えば違反。

    締めたシーズンのデータが後から変わった（修正・取りこぼしの補完）ことを意味する。
    その差は小さな集計の漏れになるので、人が判断するまで公開しない（CLAUDE.md の手順）。
    前回の出力が無い（初回）・締めが進んだ場合は通す。読めない・締めが戻った場合は止める。
    """
    path = previous_dir / f"{name}.json"
    if not path.exists():
        return []
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
        prev_through = prev["through_season"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        return [f"{name}: 前回の出力を読めない（{e!r}）。中身を確かめるまで上書きしない"]
    through = payload["through_season"]
    if through < prev_through:
        return [f"{name}: 締めが {prev_through} から {through} に戻っている"]
    if through == prev_through and prev != payload:
        return [f"{name}: 締めたシーズン（{through} まで）が同じなのに内容が変わった。"
                "過去のデータが修正・補完された可能性がある"]
    return []
```

- [ ] **Step 4: export/__init__.py を置き換える**

`src/banei/export/__init__.py`:

```python
"""集計結果を JSON として書き出す。Astro のビルド入力になる。

出力先は既定で `web/src/data/`。Astro からは `import data from '~/data/xxx.json'` で
読める。ここに出るのは集計値だけで、生データは含まれない（aggregates.py 参照）。
探索 UI の表は `explore/` 以下に書く（explore.py 参照）。
"""

import datetime as dt
import json
from pathlib import Path

from banei.config import RACES_DB
from banei.export import explore
from banei.export.aggregates import AGGREGATES, connect, policy_violations, summary

DEFAULT_OUT_DIR = Path("web/src/data")


class PolicyError(RuntimeError):
    """公開ポリシーに反する出力を検出した。"""


def build(
    db_path: Path | str = RACES_DB,
    today: dt.date | None = None,
    previous_dir: Path | str | None = None,
) -> dict[str, object]:
    """全集計を実行して {出力名: 中身} を返す。

    公開ポリシーに反する内容があれば PolicyError を送出して書き出しを止める。
    生データが 1 度でも公開側へ出ると取り返しがつかないので、ここで落とす。

    探索 UI の表（出力名 explore/…）は today（省略時は JST の今日）で締めを決め、
    previous_dir にある前回の出力と比べる（締めたシーズンが後から変わっていないか）。
    """
    con = connect(db_path)
    try:
        out: dict[str, object] = {
            "summary": {
                **summary(con),
                "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            }
        }
        for name, fn in AGGREGATES.items():
            out[name] = fn(con)
        tables, problems = explore.build(con, today or explore.today_jst())
    finally:
        con.close()

    for name, payload in out.items():
        rows = payload if isinstance(payload, list) else [payload]
        # summary の n_jockeys などはグループの大きさではなく実体の個数なので、
        # グループサイズの下限は当てない（個体特定キーの検査は行う）
        problems += policy_violations(name, rows, check_group_size=(name != "summary"))
    for name, payload in tables.items():
        problems += policy_violations(name, explore.flatten(payload))
        if previous_dir is not None:
            problems += explore.previous_problems(name, payload, Path(previous_dir))
    if problems:
        raise PolicyError(
            "公開ポリシー違反のため書き出しを中止した:\n  " + "\n  ".join(problems))
    return {**out, **tables}


def run(
    db_path: Path | str = RACES_DB,
    out_dir: Path | str = DEFAULT_OUT_DIR,
    today: dt.date | None = None,
) -> None:
    out_dir = Path(out_dir)
    data = build(db_path, today=today, previous_dir=out_dir)
    for name, payload in data.items():
        path = out_dir / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        n = len(payload) if isinstance(payload, list) else 1
        print(f"  {path}  ({n} 件)")
    print(f"書き出し完了: {len(data)} ファイル")
```

- [ ] **Step 5: 通ることを確かめる**

Run: `uv run pytest tests/test_explore.py tests/test_export_policy.py -q`
Expected: PASS（既存の `test_clean_build_succeeds` も通る。その DB は複勝の払戻が無いので探索 UI の出力は作られない）

- [ ] **Step 6: テストが違反を本当に捕まえるかを、コードをわざと壊して確かめる**

作業用ディレクトリ（セッションの scratchpad。リポジトリには入れない）に `mutation_explore.py` を置く:

```python
"""explore.py / merge.py の検査をわざと壊し、テストが落ちることを確かめる。必ず元に戻す。"""

import subprocess
import sys
from pathlib import Path

REPO = Path(sys.argv[1])
MUTATIONS = [
    ("検査 1 を外す", "src/banei/export/explore.py",
     "violations(regroup(counts, groups), MIN_GROUP_SIZE)", "[]"),
    ("検査 2 を外す", "src/banei/export/explore.py", "if got != expected:", "if False:"),
    ("検査 3 を外す", "src/banei/export/explore.py",
     "through == prev_through and prev != payload", "False"),
    ("締めの戻りを見逃す", "src/banei/export/explore.py", "if through < prev_through:", "if False:"),
    ("取消を数える", "src/banei/export/explore.py",
     "NOT IN ('取消', '除外')", "NOT IN ('除外')"),
    ("4/1 に締める", "src/banei/export/explore.py", "CLOSE_MONTH = 5", "CLOSE_MONTH = 4"),
    ("0 件の隣を先にまとめる", "src/banei/export/merge.py",
     "(totals[ax][j] == 0, totals[ax][j], j)", "(totals[ax][j], j)"),
    ("全体の出走数で軸を選ぶ", "src/banei/export/merge.py",
     "totals[ax][gi] += ns[band]", "totals[ax][gi] += sum(ns)"),
]
for label, rel, old, new in MUTATIONS:
    path = REPO / rel
    original = path.read_text(encoding="utf-8")
    assert original.count(old) == 1, f"置換対象が一意でない: {label}"
    try:
        path.write_text(original.replace(old, new), encoding="utf-8")
        r = subprocess.run(
            ["uv", "run", "pytest", "-q", "-p", "no:cacheprovider",
             "tests/test_explore.py", "tests/test_explore_merge.py"],
            cwd=REPO, capture_output=True, text=True)
        failed = [ln for ln in r.stdout.splitlines() if ln.startswith("FAILED")]
        print(f"{'検知' if failed else '★見逃し'}  {label}: {len(failed)} 件失敗")
    finally:
        path.write_text(original, encoding="utf-8")
```

Run: `python3 -I <scratchpad>/mutation_explore.py "$(pwd)" && git status --short src/`
Expected: 8 行すべて「検知」。`git status` で src/ に変更が残っていない（壊したコードは戻っている）。
「★見逃し」があれば、その性質を捕まえるテストを `tests/test_explore.py` か `tests/test_explore_merge.py` に足してから進む。

- [ ] **Step 7: 全体を確かめてコミット**

Run: `uv run ruff check . && uv run pytest -q`
Expected: すべて PASS

```bash
git add src/banei/export/__init__.py src/banei/export/explore.py tests/test_explore.py
git commit -F - <<'EOF'
探索 UI の表を export に組み込み、締めたシーズンの変化を止める

表は毎日計算するが、締めたシーズンが同じなら出力は変わらないはず。変わったなら
過去のデータが修正・補完されたということで、その差は小さな集計の漏れになる。
コミット済みの前回の出力と比べ、人が判断するまで書き出しを止める。違反は既存の
集計と同じ PolicyError で扱い、1 つでもあれば何も書き出さない。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 5: 実データで確かめて、集計をコミットする

**Files:**
- Create（生成物）: `web/src/data/explore/*.json`（36 ファイル）

**Interfaces:**
- Consumes: Task 4 の `banei export`
- Produces: Task 7 のページが読む JSON

- [ ] **Step 1: 最新のバックアップから復元する**

```bash
gh release download latest --repo banei-keiba/banei-db-backup --dir data --clobber
gunzip -f data/banei.db.gz data/odds.db.gz
```

- [ ] **Step 2: export を回す**

Run: `uv run banei export`
Expected: 41 ファイル（既存 5 + 探索 UI 36）を書いて「書き出し完了: 41 ファイル」。PolicyError が出ないこと

- [ ] **Step 3: 区分のまとまり方が設計時の測定と一致するかを確かめる**

作業用ディレクトリに `check_explore_bins.py` を置く:

```python
"""書き出した探索 UI の表の区分数を、設計時の測定（試作 7 回目）と比べる。"""

import json
import sys
from pathlib import Path

BASE = {"popularity": 10, "post": 10, "weight_diff": 5, "age": 9, "sex": 3,
        "moisture": 6, "weather": 3, "month": 12}
# まとまる表と、まとまった後の区分数（それ以外の表・軸は基本区分のまま）
EXPECTED = {
    "moisture__month": {"moisture": 4},
    "popularity__moisture": {"moisture": 5},
    "weight_diff__moisture": {"moisture": 5, "weight_diff": 4},
    "post__moisture": {"moisture": 5},
    "age__moisture": {"moisture": 5, "age": 8},
    "sex__moisture": {"moisture": 5, "sex": 2},
    "weather__month": {"weather": 2},
    "weight_diff__weather": {"weight_diff": 4},
    "age__weather": {"age": 8},
    "popularity__month": {"month": 11, "popularity": 9},
    "weight_diff__month": {"weight_diff": 4},
    "post__month": {"month": 11, "post": 9},
    "age__month": {"month": 11, "age": 8},
    "sex__month": {"sex": 2},
    "popularity__weight_diff": {"weight_diff": 4},
    "popularity__age": {"age": 7},
    "popularity__sex": {"sex": 2},
    "post__weight_diff": {"weight_diff": 4},
    "weight_diff__age": {"weight_diff": 4, "age": 8},
    "weight_diff__sex": {"weight_diff": 3, "sex": 2},
    "post__age": {"age": 7},
    "post__sex": {"sex": 2},
    "age__sex": {"age": 6, "sex": 2},
}
out_dir = Path(sys.argv[1])
ok = True
for path in sorted(out_dir.glob("*.json")):
    t = json.loads(path.read_text(encoding="utf-8"))
    name = path.stem
    want = {a: EXPECTED.get(name, {}).get(a, BASE[a]) for a in t["axes"]}
    got = {a: len(t["bins"][a]) for a in t["axes"]}
    totals = {p: t["periods"][p]["total"]["n"] for p in ("all", "recent3")}
    mark = "ok" if got == want else "★違う"
    ok &= got == want
    merged = {a: t["bins"][a] for a in t["axes"] if got[a] != BASE[a]}
    print(f"{mark:4} {name:24} {totals}  {merged or ''}")
print("すべて一致" if ok else "一致しない表がある")
```

Run: `python3 -I <scratchpad>/check_explore_bins.py web/src/data/explore`
Expected:
- 36 行すべて `ok`、最後に「すべて一致」
- 全表で `all` の出走数が 299,447（2025 シーズンまで）
- `recent3` の出走数が全表で同じ値

「★違う」が出たら、軸の並び（試作は 水分→天候→月→人気→… の順で、同値のときの選び方が変わりうる）が
原因かを `EXPECTED` との差で確かめ、原因を報告してから進む。黙って `EXPECTED` を書き換えない。

- [ ] **Step 4: 毎日回しても出力が変わらないことを確かめる**

Run: `sha256sum web/src/data/explore/*.json > /tmp/explore-1.sum && uv run banei export && sha256sum -c --quiet /tmp/explore-1.sum && echo 同一`
Expected: 2 回目も PolicyError なしで「同一」

- [ ] **Step 5: 大きさを確かめる**

Run: `du -sh web/src/data/explore && ls -S web/src/data/explore | head -3 | xargs -I{} du -h web/src/data/explore/{}`
Expected: 合計数百 KB 程度、最大のファイルでも 100KB 未満

- [ ] **Step 6: 探索 UI の JSON だけをコミットする**

既存の集計（`summary.json` の生成時刻など）は日次ワークフローに任せ、ここでは戻す。

```bash
git checkout -- web/src/data/*.json
git status --short web/src/data
git add web/src/data/explore
git commit -F - <<'EOF'
探索 UI の集計を書き出す（2025 シーズンまで）

初回の版。以後は日次ワークフローが毎日計算し、締めが進む 5/1 にだけ内容が変わる。
直近 3 シーズンが 2023 から始まるこの版が、期間帯の基準（FIRST_RECENT_SEASON）になる。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

Expected: `git status --short web/src/data` が、コミット前は `?? web/src/data/explore/` だけ

---

### Task 6: マスの濃淡（heat.ts・CSS・コントラスト検査）

**Files:**
- Create: `web/src/lib/heat.ts`
- Create: `web/src/lib/heat.test.ts`
- Modify: `web/src/styles/global.css`（末尾に探索 UI のスタイルを追記）
- Test: `tests/test_heat_contrast.py`

**Interfaces:**
- Produces:
  - `heatScale(values: number[], steps = 4): (v: number) => number`（`web/src/lib/heat.ts`）
  - CSS クラス `.heat-1`〜`.heat-4`、`.low-n`、`.empty`、`.total`、`.matrix`、`.metric-tabs`（`> input` / `> label` / `.panels > .panel`）、`.axis-links`、`.explore-links`

- [ ] **Step 1: 失敗するテストを書く**

`web/src/lib/heat.test.ts`:

```ts
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { heatScale } from './heat.ts';

test('最小は 0、最大は steps', () => {
  const s = heatScale([10, 20, 30]);
  assert.equal(s(10), 0);
  assert.equal(s(30), 4);
});

test('最小〜最大を 5 等分する', () => {
  const s = heatScale([0, 100]);
  assert.deepEqual([0, 19.9, 20, 59.9, 60, 80, 100].map(s), [0, 0, 1, 2, 3, 4, 4]);
});

test('全部同じ値なら 0（0 除算しない）', () => {
  assert.equal(heatScale([5, 5, 5])(5), 0);
});

test('対象のマスが無ければ 0', () => {
  assert.equal(heatScale([])(42), 0);
});

test('範囲外の値も 0〜steps に収まる', () => {
  const s = heatScale([10, 20]);
  assert.equal(s(-100), 0);
  assert.equal(s(1000), 4);
});
```

`tests/test_heat_contrast.py`:

```python
"""探索 UI のマスの濃淡の上で、文字が読めることを確かめる（目視で色を決めない）。

global.css のトークン（ライト / ダーク）と .heat-N の混色率を読み、WCAG のコントラスト比が
4.5:1 以上かを計算する。color-mix(in srgb, …) は sRGB の値をそのまま線形に混ぜるので、
同じ計算で再現できる。global.css の系列色を検証したスクリプトはこの環境に無いため、
CSS を変えたらここで落ちるようにしておく。
"""

import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parents[1] / "web/src/styles/global.css").read_text(
    encoding="utf-8")
AA = 4.5


def _tokens(selector: str) -> dict[str, str]:
    block = re.search(re.escape(selector) + r"\s*\{(.*?)\}", CSS, re.S).group(1)
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block))


THEMES = {"light": _tokens(":root"), "dark": _tokens(":root[data-theme='dark']")}
HEAT = {
    int(n): int(p) / 100
    for n, p in re.findall(
        r"\.heat-(\d)\s*\{\s*background:\s*color-mix\(in srgb, var\(--data\) (\d+)%,"
        r" var\(--card\)\);", CSS)
}


def _rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _luminance(c) -> float:
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (f(v) for v in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _mix(a, b, p):
    return tuple(round(x * p + y * (1 - p)) for x, y in zip(a, b, strict=True))


def test_heat_steps_are_defined():
    # 正規表現が CSS とずれて検査が空振りしないこと
    assert sorted(HEAT) == [1, 2, 3, 4]
    assert max(HEAT.values()) <= 0.48


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("step", [1, 2, 3, 4])
def test_cell_text_is_readable_on_heat(theme, step):
    t = THEMES[theme]
    bg = _mix(_rgb(t["data"]), _rgb(t["card"]), HEAT[step])
    assert _contrast(_rgb(t["ink"]), bg) >= AA


@pytest.mark.parametrize("theme", THEMES)
def test_low_n_text_is_readable_on_card(theme):
    # 出走数 100 未満のマスは濃淡を付けず --ink-2 の文字にする
    t = THEMES[theme]
    assert _contrast(_rgb(t["ink-2"]), _rgb(t["card"])) >= AA


@pytest.mark.parametrize("theme", THEMES)
def test_selected_tab_text_is_readable(theme):
    t = THEMES[theme]
    assert _contrast(_rgb(t["card"]), _rgb(t["data"])) >= AA
```

- [ ] **Step 2: 失敗を確かめる**

Run: `node --test web/src/lib/heat.test.ts`
Expected: FAIL（`Cannot find module '.../heat.ts'`）

Run: `uv run pytest tests/test_heat_contrast.py -q`
Expected: FAIL（`test_heat_steps_are_defined` が `[] == [1, 2, 3, 4]` で落ち、他は KeyError）

- [ ] **Step 3: heat.ts を実装する**

`web/src/lib/heat.ts`:

```ts
/**
 * マスの値を濃淡の段階に変える関数を返す。
 *
 * 表の中の最小〜最大を steps + 1 等分し、0（濃淡なし）〜 steps の段階にする。
 * 対象のマスが無いとき・全部同じ値のときは常に 0（0 除算しない）。
 * 渡すのは出走数 100 以上のマスの値だけ（少ないマスは振れが大きいので色で目を引かせない）。
 */
export function heatScale(values: number[], steps = 4): (v: number) => number {
  if (values.length === 0) return () => 0;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  if (hi === lo) return () => 0;
  return (v) => Math.min(steps, Math.max(0, Math.floor(((v - lo) / (hi - lo)) * (steps + 1))));
}
```

- [ ] **Step 4: global.css の末尾に追記する**

```css

/* --- 探索 --- */

/* マスの濃淡。--data を --card に混ぜる。上限 48% は、マス内の文字（--ink）の
   コントラスト比が両モードで 4.5:1 以上になる範囲（tests/test_heat_contrast.py で検査）。
   出走数 100 未満のマスには付けない（.low-n の --ink-2 は濃いマスの上で 4.5:1 を下回る。
   振れの大きいマスが色で目を引かないようにする意味もある）。 */
.heat-1 {
  background: color-mix(in srgb, var(--data) 12%, var(--card));
}

.heat-2 {
  background: color-mix(in srgb, var(--data) 24%, var(--card));
}

.heat-3 {
  background: color-mix(in srgb, var(--data) 36%, var(--card));
}

.heat-4 {
  background: color-mix(in srgb, var(--data) 48%, var(--card));
}

.matrix {
  overflow-x: auto;
  margin: 1rem 0 1.5rem;
}

.matrix table {
  width: auto;
  min-width: 100%;
  margin: 0;
}

.matrix th,
.matrix td {
  padding: 0.3rem 0.55rem;
  white-space: nowrap;
}

.matrix tbody th {
  font-weight: 600;
  color: var(--ink-2);
}

.matrix td .v {
  display: block;
  font-weight: 600;
}

/* --ink-2 は濃いマスの上で 4.5:1 を下回るので、出走数も --ink のまま小さくする */
.matrix td .n {
  display: block;
  font-size: 0.75rem;
}

.matrix .low-n,
.matrix .low-n .v {
  color: var(--ink-2);
  font-weight: 400;
}

.matrix .empty {
  color: var(--ink-3);
}

.matrix .total {
  border-left: 1px solid var(--line);
}

.matrix tr.total th,
.matrix tr.total td {
  border-top: 2px solid var(--line);
}

/* 指標のタブ。ラジオボタンと CSS だけで切り替える（JS を配信しない）。
   input・label・.panels は兄弟に置く。n 番目の input が n 番目の .panel を表示する。 */
.metric-tabs > input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.metric-tabs > label {
  display: inline-block;
  margin: 0 0.25rem 0.375rem 0;
  padding: 0.2rem 0.75rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--ink-2);
  font-size: 0.875rem;
  cursor: pointer;
}

.metric-tabs > input:checked + label {
  background: var(--data);
  border-color: var(--data);
  color: var(--card);
}

.metric-tabs > input:focus-visible + label {
  outline: 2px solid var(--data);
  outline-offset: 2px;
}

.metric-tabs .panel {
  display: none;
}

.metric-tabs > input:nth-of-type(1):checked ~ .panels > .panel:nth-child(1),
.metric-tabs > input:nth-of-type(2):checked ~ .panels > .panel:nth-child(2),
.metric-tabs > input:nth-of-type(3):checked ~ .panels > .panel:nth-child(3),
.metric-tabs > input:nth-of-type(4):checked ~ .panels > .panel:nth-child(4),
.metric-tabs > input:nth-of-type(5):checked ~ .panels > .panel:nth-child(5) {
  display: block;
}

.axis-links {
  margin: 0 0 0.375rem;
  color: var(--ink-2);
  font-size: 0.875rem;
}

.axis-links a {
  margin-right: 0.75rem;
}

.axis-links a[aria-current='page'] {
  color: var(--ink);
  font-weight: 600;
  text-decoration: none;
}

ul.explore-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1.25rem;
  list-style: none;
  padding: 0;
}
```

- [ ] **Step 5: 通ることを確かめる**

Run: `node --test web/src/lib/heat.test.ts && uv run pytest tests/test_heat_contrast.py -q`
Expected: 5 tests pass（node）/ 13 passed（pytest）

- [ ] **Step 6: 全体を確かめてコミット**

Run: `uv run ruff check . && uv run pytest -q`
Expected: すべて PASS

```bash
git add web/src/lib/heat.ts web/src/lib/heat.test.ts web/src/styles/global.css tests/test_heat_contrast.py
git commit -F - <<'EOF'
探索 UI のマスの濃淡を決め、文字が読めるかを検査する

濃淡の上限は、マス内の文字のコントラスト比が両モードで 4.5:1 以上になる 48% にした。
出走数 100 未満のマスは、薄い文字が濃いマスの上で読めなくなるうえ、振れが大きい値が
色で目を引くので濃淡を付けない。色を検証したスクリプトはこの環境に無いので、
同じ計算を pytest に置き、CSS を変えたら落ちるようにした。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 7: 探索 UI のページ

**Files:**
- Create: `web/src/lib/explore.ts`
- Create: `web/src/components/ValueCell.astro`
- Create: `web/src/components/CrossTable.astro`
- Create: `web/src/components/ExploreMatrix.astro`
- Create: `web/src/components/ExploreNav.astro`
- Create: `web/src/components/ExploreNotes.astro`
- Create: `web/src/pages/explore/index.astro`
- Create: `web/src/pages/explore/[axis]/[period].astro`
- Create: `web/src/pages/explore/[a]/[b]/[period].astro`
- Modify: `web/src/layouts/Base.astro`（ナビ）

**Interfaces:**
- Consumes: Task 5 の `web/src/data/explore/*.json`、Task 6 の `heatScale` と CSS クラス
- Produces（`web/src/lib/explore.ts`）: 型 `Metrics` / `Row` / `Period` / `PeriodKey` / `Table`、`AXES`、`axisName(key)`、`PERIODS`、`periodName(key)`、`METRICS`、`RELIABLE_N = 100`、`pairUrl(x, y, period)`、`singleUrl(x, period)`、`TABLES`、`pct(v)`、`count(v)`、`seasonRange(p)`

- [ ] **Step 1: データと URL の決まりを書く**

`web/src/lib/explore.ts`:

```ts
/** 探索 UI のデータ（src/banei/export/explore.py が書き出す JSON）と URL の決まり。 */

export interface Metrics {
  n: number;
  win_rate: number;
  top2_rate: number;
  place_rate: number;
  win_roi: number;
  place_roi: number;
}
export type Row = Metrics & Record<string, string | number>;
export type PeriodKey = 'all' | 'recent3';
export interface Period {
  first_season: number;
  last_season: number;
  total: Metrics | null;
  cells: Row[];
  margins?: Record<string, Row[]>;
}
export interface Table {
  axes: string[];
  through_season: number;
  bins: Record<string, string[]>;
  periods: Record<PeriodKey, Period>;
}

/** URL 上の軸の順（explore.py の AXES と同じ）。同じ組み合わせを 2 つの URL にしない。 */
export const AXES: { key: string; name: string }[] = [
  { key: 'popularity', name: '人気' },
  { key: 'post', name: '馬番' },
  { key: 'weight_diff', name: '重量差' },
  { key: 'age', name: '馬齢' },
  { key: 'sex', name: '性別' },
  { key: 'moisture', name: '馬場水分' },
  { key: 'weather', name: '天候' },
  { key: 'month', name: '月' },
];
export const axisName = (key: string) => AXES.find((a) => a.key === key)?.name ?? key;

export const PERIODS: { key: PeriodKey; name: string }[] = [
  { key: 'all', name: '全期間' },
  { key: 'recent3', name: '直近 3 シーズン' },
];
export const periodName = (key: PeriodKey) => PERIODS.find((p) => p.key === key)?.name ?? key;

export const METRICS: { key: keyof Metrics; name: string }[] = [
  { key: 'win_rate', name: '勝率' },
  { key: 'top2_rate', name: '連対率' },
  { key: 'place_rate', name: '複勝率' },
  { key: 'win_roi', name: '単勝回収率' },
  { key: 'place_roi', name: '複勝回収率' },
];

/** 濃淡を付ける最小の出走数。これ未満のマスは振れが大きいので、薄い文字にして色を付けない。 */
export const RELIABLE_N = 100;

const order = (key: string) => AXES.findIndex((a) => a.key === key);

export function pairUrl(x: string, y: string, period: PeriodKey): string {
  const [a, b] = [x, y].sort((p, q) => order(p) - order(q));
  return `/explore/${a}/${b}/${period}/`;
}

export function singleUrl(x: string, period: PeriodKey): string {
  return `/explore/${x}/${period}/`;
}

const modules = import.meta.glob<{ default: Table }>('../data/explore/*.json', { eager: true });

/** 書き出された全表。キーは軸のキーを __ でつないだもの（popularity__moisture）。 */
export const TABLES: Record<string, Table> = Object.fromEntries(
  Object.entries(modules).map(([path, mod]) => [
    path.slice(path.lastIndexOf('/') + 1, -'.json'.length),
    mod.default,
  ]),
);

export const pct = (v: number) => `${v.toFixed(1)}%`;
export const count = (v: number) => v.toLocaleString('ja-JP');
export const seasonRange = (p: Period) => `${p.first_season}〜${p.last_season} シーズン`;
```

- [ ] **Step 2: 表の部品を書く**

`web/src/components/ValueCell.astro`:

```astro
---
/* 率と出走数を上下に並べたマス。row が無ければ「—」（0 件のマスは JSON に入らない）。 */
import { count, pct, type Metrics } from '../lib/explore';

interface Props {
  row?: Metrics | null;
  metric: keyof Metrics;
  class?: string;
}

const { row, metric, class: cls = '' } = Astro.props;
---

{
  row ? (
    <td class={cls}>
      <span class="v">{pct(row[metric])}</span>
      <span class="n">{count(row.n)}</span>
    </td>
  ) : (
    <td class={`${cls} empty`.trim()}>—</td>
  )
}
```

`web/src/components/CrossTable.astro`:

```astro
---
/* 2 軸のクロス表（1 指標）。端に「全体」の行と列を付ける。
   全体はマスの合計として export 側で集計済み。ここでは新たな数字を作らない。 */
import ValueCell from './ValueCell.astro';
import { heatScale } from '../lib/heat';
import { RELIABLE_N, axisName, type Metrics, type Period, type Table } from '../lib/explore';

interface Props {
  table: Table;
  period: Period;
  metric: keyof Metrics;
}

const { table, period, metric } = Astro.props;

// 区分の多い軸を行にする（列が増えて横にはみ出すのを抑える）。同数なら URL の順で先の軸
const [x, y] = table.axes;
const [rowAxis, colAxis] = table.bins[y].length > table.bins[x].length ? [y, x] : [x, y];
const key = (r: string, c: string) => `${r}\u0000${c}`;
const cells = new Map(period.cells.map((c) => [key(String(c[rowAxis]), String(c[colAxis])), c]));
const rowTotal = new Map((period.margins?.[rowAxis] ?? []).map((m) => [String(m[rowAxis]), m]));
const colTotal = new Map((period.margins?.[colAxis] ?? []).map((m) => [String(m[colAxis]), m]));
const heat = heatScale(period.cells.filter((c) => c.n >= RELIABLE_N).map((c) => c[metric]));
const cellClass = (n: number, v: number) => (n >= RELIABLE_N ? `heat-${heat(v)}` : 'low-n');
---

<div class="matrix">
  <table>
    <thead>
      <tr>
        <th scope="col">{axisName(rowAxis)} ＼ {axisName(colAxis)}</th>
        {table.bins[colAxis].map((c) => <th scope="col">{c}</th>)}
        <th scope="col" class="total">全体</th>
      </tr>
    </thead>
    <tbody>
      {
        table.bins[rowAxis].map((r) => (
          <tr>
            <th scope="row">{r}</th>
            {table.bins[colAxis].map((c) => {
              const cell = cells.get(key(r, c));
              return (
                <ValueCell
                  row={cell}
                  metric={metric}
                  class={cell ? cellClass(cell.n, cell[metric]) : ''}
                />
              );
            })}
            <ValueCell row={rowTotal.get(r)} metric={metric} class="total" />
          </tr>
        ))
      }
      <tr class="total">
        <th scope="row">全体</th>
        {table.bins[colAxis].map((c) => <ValueCell row={colTotal.get(c)} metric={metric} />)}
        <ValueCell row={period.total} metric={metric} class="total" />
      </tr>
    </tbody>
  </table>
</div>
```

`web/src/components/ExploreMatrix.astro`:

```astro
---
/* 指標のタブ。ラジオボタンと CSS だけで切り替える（JS を配信しない。global.css の .metric-tabs）。 */
import CrossTable from './CrossTable.astro';
import { METRICS, type Period, type Table } from '../lib/explore';

interface Props {
  table: Table;
  period: Period;
}

const { table, period } = Astro.props;
---

<div class="metric-tabs" role="group" aria-label="指標">
  {
    METRICS.map((m, i) => (
      <>
        <input type="radio" name="metric" id={`metric-${m.key}`} checked={i === 0} />
        <label for={`metric-${m.key}`}>{m.name}</label>
      </>
    ))
  }
  <div class="panels">
    {
      METRICS.map((m) => (
        <div class="panel">
          <CrossTable table={table} period={period} metric={m.key} />
        </div>
      ))
    }
  </div>
</div>
```

`web/src/components/ExploreNav.astro`:

```astro
---
/* 軸と期間の切り替え。すべて静的ページへのリンク。 */
import {
  AXES,
  PERIODS,
  axisName,
  pairUrl,
  singleUrl,
  type PeriodKey,
} from '../lib/explore';

interface Props {
  axes: string[];
  period: PeriodKey;
}

const { axes, period } = Astro.props;
const urlFor = (keys: string[], p: PeriodKey) =>
  keys.length === 2 ? pairUrl(keys[0], keys[1], p) : singleUrl(keys[0], p);
const here = urlFor(axes, period);
const current = (url: string) => (url === here ? 'page' : undefined);
---

<nav aria-label="表の切り替え">
  {
    axes.map((a) => (
      <p class="axis-links">
        {axisName(a)} と組み合わせる：
        {AXES.filter((o) => o.key !== a).map((o) => {
          const url = pairUrl(a, o.key, period);
          return (
            <a href={url} aria-current={current(url)}>
              {o.name}
            </a>
          );
        })}
      </p>
    ))
  }
  {
    axes.length === 2 && (
      <p class="axis-links">
        1 つの条件で見る：
        {axes.map((a) => <a href={singleUrl(a, period)}>{axisName(a)}</a>)}
      </p>
    )
  }
  <p class="axis-links">
    期間：
    {
      PERIODS.map((p) => {
        const url = urlFor(axes, p.key);
        return (
          <a href={url} aria-current={current(url)}>
            {p.name}
          </a>
        );
      })
    }
  </p>
</nav>
```

`web/src/components/ExploreNotes.astro`:

```astro
---
/* 探索ページ共通の注記。予想の材料として見る読者が、偶然を傾向と取り違えないように。 */
import { RELIABLE_N } from '../lib/explore';

interface Props {
  /* 2 軸の表（マスに率と出走数を並べる）のページか */
  matrix?: boolean;
  /* 入口ページへのリンクを付けるか（入口ページ自身では付けない） */
  about?: boolean;
}

const { matrix = false, about = true } = Astro.props;
---

<div class="note">
  {
    matrix && (
      <p>
        各マスの上段が率、下段が出走数です。薄い文字のマスは出走数が {RELIABLE_N} 未満で、
        率の振れが大きいため色を付けていません。
      </p>
    )
  }
  <p>
    回収率は 1 回の高配当で大きく動きます。また、多くのマスを見比べれば、偶然でも 100%
    を超えるマスはいくつか出ます。過去にそうだったことは、これからもそうなることを意味しません。
  </p>
  {
    about && (
      <p>
        集計は終わったシーズン（4 月〜翌 3 月）までで、年に 1 回、5 月に更新します。
        区分をまとめている表がある理由は<a href="/explore/">条件で探す</a>に書いています。
      </p>
    )
  }
</div>
```

- [ ] **Step 3: ページを書く**

`web/src/pages/explore/[a]/[b]/[period].astro`:

```astro
---
import ExploreMatrix from '../../../../components/ExploreMatrix.astro';
import ExploreNav from '../../../../components/ExploreNav.astro';
import ExploreNotes from '../../../../components/ExploreNotes.astro';
import Base from '../../../../layouts/Base.astro';
import {
  PERIODS,
  TABLES,
  axisName,
  count,
  periodName,
  seasonRange,
  type PeriodKey,
  type Table,
} from '../../../../lib/explore';

export function getStaticPaths() {
  return Object.values(TABLES)
    .filter((t) => t.axes.length === 2)
    .flatMap((table) =>
      PERIODS.map((p) => ({
        params: { a: table.axes[0], b: table.axes[1], period: p.key },
        props: { table, periodKey: p.key },
      })),
    );
}

interface Props {
  table: Table;
  periodKey: PeriodKey;
}

const { table, periodKey } = Astro.props;
const period = table.periods[periodKey];
const [a, b] = table.axes.map(axisName);
---

<Base
  title={`${a}×${b}の勝率・回収率（${periodName(periodKey)}）`}
  description={`ばんえい競馬の${a}と${b}の組み合わせごとに、勝率・連対率・複勝率・回収率を集計した表です。`}
>
  <h1>{a} × {b}</h1>
  <p class="meta">
    {periodName(periodKey)}：{seasonRange(period)}・{count(period.total?.n ?? 0)} 出走
  </p>
  <ExploreNav axes={table.axes} period={periodKey} />
  <ExploreMatrix table={table} period={period} />
  <ExploreNotes matrix />
</Base>
```

`web/src/pages/explore/[axis]/[period].astro`:

```astro
---
import ExploreNav from '../../../components/ExploreNav.astro';
import ExploreNotes from '../../../components/ExploreNotes.astro';
import Base from '../../../layouts/Base.astro';
import {
  METRICS,
  PERIODS,
  RELIABLE_N,
  TABLES,
  axisName,
  count,
  pct,
  periodName,
  seasonRange,
  type PeriodKey,
  type Table,
} from '../../../lib/explore';

export function getStaticPaths() {
  return Object.values(TABLES)
    .filter((t) => t.axes.length === 1)
    .flatMap((table) =>
      PERIODS.map((p) => ({
        params: { axis: table.axes[0], period: p.key },
        props: { table, periodKey: p.key },
      })),
    );
}

interface Props {
  table: Table;
  periodKey: PeriodKey;
}

const { table, periodKey } = Astro.props;
const period = table.periods[periodKey];
const axis = table.axes[0];
const name = axisName(axis);
const byBin = new Map(period.cells.map((c) => [String(c[axis]), c]));
---

<Base
  title={`${name}別の勝率・回収率（${periodName(periodKey)}）`}
  description={`ばんえい競馬の${name}別に、勝率・連対率・複勝率・回収率を集計した表です。`}
>
  <h1>{name}別の勝率・回収率</h1>
  <p class="meta">
    {periodName(periodKey)}：{seasonRange(period)}・{count(period.total?.n ?? 0)} 出走
  </p>
  <ExploreNav axes={table.axes} period={periodKey} />
  <div class="matrix">
    <table>
      <thead>
        <tr>
          <th scope="col">{name}</th>
          <th scope="col">出走数</th>
          {METRICS.map((m) => <th scope="col">{m.name}</th>)}
        </tr>
      </thead>
      <tbody>
        {
          table.bins[axis].map((bin) => {
            const c = byBin.get(bin);
            return c ? (
              <tr class={c.n < RELIABLE_N ? 'low-n' : undefined}>
                <th scope="row">{bin}</th>
                <td>{count(c.n)}</td>
                {METRICS.map((m) => <td>{pct(c[m.key])}</td>)}
              </tr>
            ) : (
              <tr>
                <th scope="row">{bin}</th>
                <td class="empty" colspan={METRICS.length + 1}>—</td>
              </tr>
            );
          })
        }
        {
          period.total && (
            <tr class="total">
              <th scope="row">全体</th>
              <td>{count(period.total.n)}</td>
              {METRICS.map((m) => <td>{pct(period.total![m.key])}</td>)}
            </tr>
          )
        }
      </tbody>
    </table>
  </div>
  <ExploreNotes />
</Base>
```

`web/src/pages/explore/index.astro`:

```astro
---
import ExploreNotes from '../../components/ExploreNotes.astro';
import Base from '../../layouts/Base.astro';
import { AXES, TABLES, axisName, pairUrl, singleUrl } from '../../lib/explore';

const tables = Object.values(TABLES);
const singles = AXES.filter((a) => tables.some((t) => t.axes.length === 1 && t.axes[0] === a.key));
const pairs = tables.filter((t) => t.axes.length === 2);
const through = tables[0]?.through_season;
---

<Base
  title="条件で探す"
  description="ばんえい競馬の勝率・連対率・複勝率・回収率を、人気・馬番・馬場水分などの条件の組み合わせで集計した表の一覧です。"
>
  <h1>条件で探す</h1>
  <p class="lede">
    人気・馬番・重量差・馬齢・性別・馬場水分・天候・月のうち 1 つか 2 つを選んで、
    勝率・連対率・複勝率・回収率を表で見られます。
  </p>
  {
    through && (
      <p class="meta">
        {through} シーズン（{through} 年 4 月〜{through + 1} 年 3 月）までを集計
      </p>
    )
  }

  <h2>1 つの条件で見る</h2>
  <ul class="explore-links">
    {singles.map((a) => <li><a href={singleUrl(a.key, 'all')}>{a.name}</a></li>)}
  </ul>

  <h2>2 つの条件を組み合わせる</h2>
  {
    AXES.map((a) => {
      const mine = pairs.filter((t) => t.axes[0] === a.key);
      return (
        mine.length > 0 && (
          <p class="axis-links">
            {a.name} ×{' '}
            {mine.map((t) => (
              <a href={pairUrl(t.axes[0], t.axes[1], 'all')}>{axisName(t.axes[1])}</a>
            ))}
          </p>
        )
      );
    })
  }

  <h2>何を数えているか</h2>
  <p>
    取消・除外を除いた全出走です。競走中止・失格も、馬券は外れとして数えています。
    複勝率は「複勝の払戻対象になった割合」で、7 頭立て以下では 2 着まで、8 頭立て以上では
    3 着までです。回収率は、100 円ずつ買い続けたときの払戻の合計を、買った金額で割ったものです。
  </p>

  <h2>年に 1 回だけ更新します</h2>
  <p>
    集計は終わったシーズン（4 月〜翌 3 月）までで、5 月に 1 回だけ更新します。毎日更新すると、
    前日との差からその日のレース結果が読み取れてしまうためです（このサイトは個別レースの
    結果を掲載しない方針です）。
  </p>

  <h2>区分をまとめている表があります</h2>
  <p>
    どの表も、シーズンごとに数えて各マスが 0 件か 30 件以上になるよう、件数の少ない区分を
    隣の区分とまとめています（例：9〜10 番人気）。マスを消すだけだと、合計との差から少ない
    件数の集計が割り出せてしまうためです。
  </p>

  <ExploreNotes about={false} />
</Base>
```

`web/src/layouts/Base.astro` のナビ:

```astro
        <nav>
          <a href="/">ホーム</a>
          <a href="/explore/">探索</a>
          <a href="/data/">データについて</a>
        </nav>
```

- [ ] **Step 4: ビルドして確かめる**

Run: `cd web && npm run build 2>&1 | tail -5; cd ..`
Expected: エラーなく完了。生成ページ数が 77（既存 4 + 探索 73）

Run: `find web/dist/explore -name index.html | wc -l`
Expected: `73`

Run: `grep -rl '<script' web/dist/explore | wc -l`
Expected: `0`（JS ゼロ）

Run: `ls -S web/dist/explore/*/*/*/index.html | head -1 | xargs du -b`
Expected: 最大の 2 軸ページが 60KB 未満（見込みは 30KB 前後）

Run: `grep -o 'class="[^"]*"' web/dist/explore/popularity/moisture/all/index.html | sort | uniq -c | sort -rn | head`
Expected: `heat-0`〜`heat-4` と `low-n` が出現している（濃淡と少数マスの区別が効いている）

- [ ] **Step 5: 見た目を手元で確かめる**

Run: `cd web && npm run preview` を別端末で起動し、`/explore/`・`/explore/popularity/all/`・
`/explore/popularity/moisture/all/` をブラウザで開く。確かめること:
- タブで指標が切り替わる（キーボードの Tab と矢印キーでも）
- ダークモードでもマスの文字が読める
- 幅 375px でも表が横スクロールで収まり、ページ全体は横にはみ出さない

ブラウザが使えない環境では、このステップを飛ばしたことを報告に書く（完了扱いにしない）。

- [ ] **Step 6: 全体を確かめてコミット**

Run: `uv run ruff check . && uv run pytest -q && node --test web/src/lib/heat.test.ts`
Expected: すべて PASS

```bash
git add web/src/lib/explore.ts web/src/components/ValueCell.astro web/src/components/CrossTable.astro \
  web/src/components/ExploreMatrix.astro web/src/components/ExploreNav.astro \
  web/src/components/ExploreNotes.astro web/src/pages/explore web/src/layouts/Base.astro
git commit -F - <<'EOF'
探索 UI のページを足す

予想の材料を探す読者向けに、1 軸 8 表・2 軸 28 表を全期間と直近 3 シーズンの
73 ページにした。組み合わせごとに静的ページにしたのは、JS ゼロの方針を守りつつ
各ページが検索に拾われるようにするため。指標の切り替えはラジオボタンと CSS で行う。
回収率の振れと見比べによる偶然を注記し、偶然を傾向と取り違えないようにした。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 8: ドキュメントの更新

**Files:**
- Modify: `docs/architecture.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: Task 1〜7 の結果（テスト件数・ページ数・区分の測定）

- [ ] **Step 1: architecture.md を書き換える**

- 冒頭の `最終更新:` を作業日にする
- §1 の 2. 「両者の境界は「生成されたファイル（Parquet / JSON）」だけ」→「両者の境界は「生成された JSON」だけ」
- §2 の図:
  - `B4["export<br/>Parquet / JSON"]` → `B4["export<br/>集計 JSON"]`
  - `C2["Pages 静的アセット<br/>集計済み Parquet"]` の行と `B4 --> C2`、`C2 --> W2` を削除する
  - `W2["DuckDB-WASM<br/>ブラウザ内 探索 UI"]` → `W2["探索ページ<br/>2 軸の静的クロス表"]`、`B4 --> W2` を足す
- §2 の表: 「エクスポート | Python → Parquet / JSON」→「Python → JSON」。「配信データ | Pages 静的アセット | 集計済み Parquet のみ（探索 UI 用）」の行を削除
- §3.3 の最終段落の 2 文目（「Parquet を静的アセットとして置き、…成立する。」）を「探索 UI も静的ページなので、アクセスが増えても費用は変わらない。」にする
- §3.4 の表「生データの Parquet 配布 | 集計済みテーブルの Parquet」→「生データの配布 | 集計済みの表（JSON・静的ページ）」
- §3.4 の「**探索 UI — Parquet + DuckDB-WASM**」の小節（見出しから 4 つの箇条書きまで）を次に置き換える:

```markdown
**探索 UI — 2 軸の静的クロス表**（設計: docs/superpowers/specs/2026-10-13-explore-ui-design.md）

当初はブラウザ内の DuckDB-WASM で自由にクロス集計する計画だったが、実データで測ると
成り立たなかった。全 10 軸の組み合わせはすべてのマスが 30 件未満になり、細かいマスを
消してから足し合わせると、消えた分だけ件数が少なく出る。正しい値を出すには、見せる
組み合わせごとに事前集計するしかない。そこで、人を除く 8 軸の 1 軸・2 軸の表（36 表）を
export で集計し、全期間と直近 3 シーズンの 73 の静的ページにした。

- **マスを消さずに隣とまとめる**。消すと、別に公開した合計との引き算で値が割り出せる
  （実測で 289 行）。各表は対象の出走をもれなく分ける
- **30 件ルールは版と版の差にも当てる**。毎日更新すると、前日との差からその日の結果が
  ほぼ復元できる。そのため集計は締めたシーズン（5/1 締め）までとし、年 1 回だけ変わる。
  規則は「期間帯（2007〜2022 のかたまり / 2023 以降は 1 シーズンずつ）ごとに全マスが
  0 件か 30 件以上」
- 騎手・調教師を含めると、この規則では騎手の表の 53〜100% が「その他」になる（実測）。
  人の切り口は Phase 4 で決める
- export の実行時検査: 全マスが期間帯ごとに 0 か 30 以上 / マスの合計が対象出走数と一致 /
  締めたシーズンが同じなのに前回の出力と違えば止める
```

- §4 のツリー `export/ … 集計 → Parquet / JSON` → `集計 → JSON（探索 UI は explore/）`
- §5 の表「集計 Parquet/JSON 出力」→「集計 JSON 出力」
- Phase 3 のチェックリストを次に置き換える:

```markdown
- [x] Python 側で集計 → `web/src/data/explore/*.json`（36 表）。DuckDB-WASM は採らない（§3.4）
- [x] 2 軸の静的クロス表 73 ページ（人気・馬番・重量差・馬齢・性別・馬場水分・天候・月 × 全期間 / 直近 3 シーズン）
- [x] 配色は global.css のトークン。マスの濃淡の文字コントラストは tests/test_heat_contrast.py で検査
```

- §8 の「運用上の注意」の末尾に追記:

```markdown
- **既知の課題: 今の公開ページにある版の差の漏れ**。人気別の表などは 1 行 3 万件台で 0.1% 単位に
  丸めているので 1 出走ぶんの変化は読めないが、件数の少ない行（`weight_handicap` の重量差 80kg・
  n=31 など）は 1 出走増えたときに勝ったかどうかが分かる。`moisture_vs_time` の `fastest_sec` は
  1 レースの値そのもの。探索 UI と同じく締めたシーズンまでにするか、行をまとめて直す
```

Run: `grep -n 'Parquet\|DuckDB' docs/architecture.md`
Expected: 新しい §3.4 の「DuckDB-WASM で自由にクロス集計する計画だったが」と、Phase 3 の「DuckDB-WASM は採らない」だけが残る

- [ ] **Step 2: CLAUDE.md を書き換える**

「最重要: データ公開方針」の「具体的に守ること」の箇条書きの末尾に追記:

```markdown
- **30 件ルールは版と版の差にも当てる**。集計は毎日 public リポジトリにコミットされるので、
  前日の版との差からその日のレースだけの集計が出る。細かい表を毎日更新すると、その日の
  結果表がほぼ復元できる。探索 UI が締めたシーズンまで・年 1 回更新なのはこのため
```

「構成」のツリーの `export/` の行を次にする:

```text
  export/     【公開データの唯一の出口】集計 → web/src/data/*.json（探索 UI は explore/*.json）
```

「## 環境まわりの既知の事情」の直前に節を足す:

```markdown
## 探索 UI は年 1 回だけ変わる

`banei export` は探索 UI の表（`web/src/data/explore/*.json`）も毎日計算するが、集計は締めた
シーズン（4/1〜翌 3/31、5/1 締め）までなので、出力は 5/1 に締めが進むときだけ変わる。
期間帯の基準 `FIRST_RECENT_SEASON = 2023`（`src/banei/export/explore.py`）は初回公開の
直近 3 シーズンの始まりで、**変えてはいけない**（版の差で切り出される単位が変わる）。

**「締めたシーズンが同じなのに内容が変わった」で export が止まったら**: 締めたシーズンの
データが後から修正・補完されたということ。その差は小さな集計の漏れになるので、日次の
デプロイは止まったままにして調べる（DB のバックアップは export より前に済んでいる）。

1. `uv run banei export --out-dir /tmp/explore-check` で新しい出力を作り、コミット済みの
   `web/src/data/explore/` と比べて、どの表のどのマスが変わったかを確かめる
2. 原因が過去データの修正・補完で、その差を公開してよいと判断したら、変わった表の JSON を
   削除してから `banei export` をやり直す（初回扱いで通る）。判断の理由をコミットに書く
3. 公開できないなら、データを修正前に戻す
```

「進捗」の「次は Phase 3」の行を次に置き換える:

```markdown
- **Phase 3（探索 UI）完了**（作業日を書く）— 人を除く 8 軸の 1 軸・2 軸の表 36 表を 73 の静的
  ページに。計画の DuckDB-WASM は実測で成り立たず採らなかった（architecture.md §3.4）。
  テストは全 N 件（N は `uv run pytest -q` の結果。Node の heat.test.ts 5 件は別）
- **次は Phase 4（騎手・馬ページ）**。人の切り口は版の差の規則で大半が「その他」になるので、
  設計から決める。組み合わせオッズのバックフィルはフェーズ非依存で並行して進める
```

「Phase 1 …テストは全 126 件（ゴールデン 32 / 検証 32 ほか）」の件数の記述は Phase 1 時点の記録なので変えない。

- [ ] **Step 3: 全体を確かめてコミット**

Run: `uv run ruff check . && uv run pytest -q && node --test web/src/lib/heat.test.ts && (cd web && npm run build >/dev/null) && echo ok`
Expected: `ok`

```bash
git add docs/architecture.md CLAUDE.md
git commit -F - <<'EOF'
Phase 3 の完了と、版の差にも 30 件ルールを当てる方針を記録する

計画の DuckDB-WASM を採らなかった理由（実測）と、探索 UI が年 1 回しか変わらない
理由を残す。締めたシーズンの変化で export が止まったときの手順も書いた。
今の公開ページにも件数の少ない行で同じ種類の漏れがあるので、既知の課題として残す。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```
