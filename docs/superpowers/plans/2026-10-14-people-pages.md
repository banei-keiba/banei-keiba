# Phase 4 騎手・調教師ページ 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 騎手・調教師のシーズンごとの成績と派生指標（人気から見込まれる勝ち数との差）を export で集計し、一覧と 1 人 1 ページ（約 90 ページ）の静的ページとして作る（公開はしない）。

**Architecture:** Python の `src/banei/export/people.py` が、探索 UI と同じ対象出走（`explore.STARTERS`）を
役割（騎手・調教師）× DB の略称 × シーズンで集計し、30 件未満の人・シーズンをシーズンごとに「その他」へ
まとめて `web/src/data/people.json` に書く。表示名は `src/banei/export/people.toml`（略称 → 正式名）で
付け、集計と URL は略称で決める。違反は既存の `export.build()` の `PolicyError` で止める。
Astro は `getStaticPaths` で JSON からページを作る。JS は配信しない。

**Tech Stack:** Python 3.13 / SQLite / tomllib / pytest / ruff（uv）、Astro 7、Node 24

**Spec:** `docs/superpowers/specs/2026-10-14-people-pages-design.md`（必ず併せて読むこと）

## Global Constraints

- 公開物は `src/banei/export/` を唯一の出口にする。検査は実行時に走らせ、違反は `PolicyError` で書き出し全体を止める
- 30 件の下限は `banei.export.aggregates.MIN_GROUP_SIZE` を使う（数値を直書きしない）
- 対象の出走・締め・指標の定義は `explore.py` のもの（`STARTERS` / `RUN_VALUES` / `PAYOUTS` / `season_end` / `through_season` / `population` / `metrics`）を使い、複製しない
- シーズンは 4/1〜翌 3/31、開始年で呼ぶ。締めは 5/1。日付は JST で明示的に判定する（`explore.today_jst()`）
- 出力 JSON に生成時刻を入れない（入れると検査 3 が成り立たない）
- `policy_violations()` は `n` と `n_` で始まる整数列を件数とみなして 30 以上を求める。人数は `people_count` と書く（`n_people` にしない）。`status`・`horse_name` などは `FORBIDDEN_KEYS`。現役かどうかは `active` と書く
- 人気に関わる値（人気別の出走数の重み付き合計）は `avg_popularity` と `expected_wins` の 2 つだけ。増やさない
- 正式名は出典で確かめた人だけを対応表に書く。推測で埋めない
- URL（slug）は DB の略称から空白（全角を含む）を除いたもの。対応表を直しても変わらない
- Web は JS ゼロ（`<script>` を書かない）。色は `web/src/styles/global.css` のトークンだけを使う。単系列の図に凡例を置かず、値は端点だけ直接ラベルし、全図版に表ビュー（`DataTable.astro`）を付ける
- テストは合成データのみ（実ページの HTML・実 DB を使わない）
- `.db` をコミットしない。`data/` は .gitignore 済み
- ドキュメント・コメント・コミットメッセージは日本語。コミットメッセージは「なぜ」を書く
- git commit は GPG 署名必須。`Inappropriate ioctl for device` で失敗したら、ユーザーに
  `echo test | gpg --clearsign > /dev/null` を実行してもらう。署名を外さない
- push はユーザーの承認を得てから（この計画では push しない）
- 各タスクの最後に `uv run ruff check . && uv run pytest -q` が通ること
- コミットメッセージの末尾に `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` を付ける

## Review Focus

- 日本語の URL（`/people/鈴木恵/`）が、ビルドしたファイル・リンク・プレビューのすべてで同じページに解決する → Task 7 でパーセントエンコードした URL をプレビューに投げて 200 を確かめる
- 5/1 に対応表に無い新人が出ても export が止まらず、略称のページと警告になる。騎手と調教師で同じ略称の新人は 1 ページになる → Task 3・4 でテスト
- シーズン全体が 30 件未満（テスト用の小さな DB など）→ 落ちずに公開ポリシー違反として報告される → Task 2 でテスト
- people の追加で既存の export テスト（`test_export_policy.py` の小さな DB、`test_explore.py` の big）が壊れない → Task 4 で全テストを回す。探索 UI のテストの合成 DB に騎手・調教師を入れる
- 個人の欄が 1 シーズンだけの人（図を出さない）・「その他」にまとめたシーズンのある人のページが崩れない → Task 7 でビルド結果を確かめる

---

## File Structure

| ファイル | 責務 |
|---|---|
| `src/banei/export/explore.py`（変更） | 対象出走の SQL・1 出走の値・締めの日付・指標を公開名にし、people.py から使えるようにする |
| `src/banei/export/people.py`（新規） | 人ごとの集計・「その他」へのまとめ・対応表・ページの一覧・検査 2〜4 |
| `src/banei/export/people.toml`（新規） | 略称 → 正式名の対応表（Task 3 で空の雛形、Task 5 で中身） |
| `src/banei/export/__init__.py`（変更） | `build()` に people を組み込む。警告を表示する |
| `src/banei/svgcheck.py`（新規） | ビルドした HTML の SVG のはみ出し検査（`python -m banei.svgcheck web/dist`） |
| `tests/test_people.py`（新規） | people.py と export への組み込みのテスト |
| `tests/test_svgcheck.py`（新規） | svgcheck.py のテスト |
| `tests/test_explore.py`（変更） | 合成 DB に騎手・調教師を入れる（export が people も作るため） |
| `web/src/components/LineChart.astro`（変更） | `xFormat` と `refValue` を足す |
| `web/src/lib/people.ts`（新規） | people.json の型・役割の名前・URL・書式 |
| `web/src/pages/people/index.astro`（新規） | 一覧（最新シーズンの順位表と全員） |
| `web/src/pages/people/[slug].astro`（新規） | 1 人のページ |
| `web/src/layouts/Base.astro`（変更） | ナビに「騎手・調教師」 |
| `web/src/data/people.json`（生成物） | 日次ワークフローがコミットする（`git add web/src/data` に含まれる） |
| `docs/architecture.md`・`CLAUDE.md`（変更） | 方針と仕組みの記録 |

---

### Task 1: 人ごとの集計と指標（people.py 前半）

**Files:**
- Modify: `src/banei/export/explore.py:144-203`（`_STARTERS`・`_end`・`load_cells`）, `:222-232`（`_metrics`）と呼び出し元
- Create: `src/banei/export/people.py`
- Test: `tests/test_people.py`

**Interfaces:**
- Consumes: `explore.N`, `explore.WIN`（集計値の位置）, `explore.population(con, through) -> dict[int, int]`
- Produces（explore.py の改名。挙動は変えない）:
  - `explore.STARTERS: str` — 対象出走の CTE（`s`）。パラメータ `:end`
  - `explore.RUN_VALUES: str` — 1 出走の `[WIN, TOP2, PLACE, WIN_PAY, PLACE_PAY]` の SELECT 列
  - `explore.PAYOUTS: str` — `pw`（単勝）・`pp`（複勝）の LEFT JOIN
  - `explore.season_end(through: int) -> str` — `:end` に渡す日付
  - `explore.metrics(m: list[int]) -> dict` — `n, win_rate, top2_rate, place_rate, win_roi, place_roi`
- Produces（people.py）:
  - `people.ROLES = ("jockey", "trainer")`, `people.ROLE_NAMES = {"jockey": "騎手", "trainer": "調教師"}`
  - `people.POPULARITIES = range(1, 11)`, `people.POP = 6`, `people.WIDTH = 16` — 集計値は `[N, WIN, TOP2, PLACE, WIN_PAY, PLACE_PAY, 人気1の出走数, …, 人気10の出走数]`
  - `people.Cells = dict[tuple[int, str], list[int]]` — (シーズン, 略称) → 集計値
  - `people.Loaded(roles: dict[str, Cells], seasons: dict[int, list[int]], rates: dict[int, list[float]])`（frozen dataclass）
  - `people.load(con, through: int) -> Loaded`
  - `people.expected(m: list[int], rates: list[float]) -> float`
  - `people.metrics(m: list[int], exp: float) -> dict` — explore の 6 つ + `wins, avg_popularity, expected_wins, wins_over_expected`

- [ ] **Step 1: explore.py の共有する部分を公開名にする（挙動は変えない）**

`src/banei/export/explore.py` の `_STARTERS = """` を `STARTERS = """` に、`def _end(` を `def season_end(` に、
`def _metrics(` を `def metrics(` に改名し、ファイル内の呼び出し（`_STARTERS +`・`_end(through)`・`_metrics(`）を
すべて新しい名前に置き換える。`_end` の直後に docstring を足す:

```python
def season_end(through: int) -> str:
    """締めたシーズンの翌日（STARTERS の :end）。この日より前の出走が対象。"""
    return f"{through + 1}-{SEASON_START_MONTH:02d}-01"
```

`metrics` には次の docstring を足す:

```python
def metrics(m: list[int]) -> dict:
    """1 マスの指標。騎手・調教師ページ（people.py）も同じ定義を使う。"""
```

`STARTERS` の直後に、1 出走の値と払戻の結合を足す（今 `load_cells` の SQL に書いてあるものを移す）:

```python
# 1 出走の集計値 [WIN, TOP2, PLACE, WIN_PAY, PLACE_PAY]（N を除く）。FROM s に PAYOUTS を付けて使う
RUN_VALUES = """COALESCE(s.finish = 1, 0), COALESCE(s.finish <= 2, 0),
       pp.amount IS NOT NULL, COALESCE(pw.amount, 0), COALESCE(pp.amount, 0)"""
PAYOUTS = """
LEFT JOIN payouts pw ON pw.race_date = s.race_date AND pw.race_no = s.race_no
     AND pw.bet_type = '単勝' AND CAST(pw.combination AS INTEGER) = s.horse_no
LEFT JOIN payouts pp ON pp.race_date = s.race_date AND pp.race_no = s.race_no
     AND pp.bet_type = '複勝' AND CAST(pp.combination AS INTEGER) = s.horse_no
"""
```

`load_cells` の SQL を次に置き換える（結合の順は前と同じ: races の JOIN の後に払戻の LEFT JOIN）:

```python
    sql = STARTERS + f"""
    SELECT s.season, {axis_cols}, {RUN_VALUES}
    FROM s
    JOIN races ra ON ra.race_date = s.race_date AND ra.race_no = s.race_no
    {PAYOUTS}
    """
```

- [ ] **Step 2: 探索 UI のテストが変わらず通ることを確かめる**

Run: `uv run pytest tests/test_explore.py -q && uv run ruff check src/banei/export/explore.py`
Expected: 全件 PASS、ruff の指摘なし

- [ ] **Step 3: 失敗するテストを書く**

`tests/test_people.py` を新規作成:

```python
"""騎手・調教師ページの集計（people.py）のテスト。合成データのみ（実データ・実ページは使わない）。"""

import datetime as dt
import sqlite3

import pytest

from banei.db.schema import RACES_SCHEMA
from banei.export import people

SEASON_2025 = "2025-06-01"  # 2025 シーズン（2025-04-01〜2026-03-31）
TODAY = dt.date(2026, 10, 14)  # 2025 シーズンまで締めている


def run(no, finish=None, status=None, popularity=None, jockey="騎手A", trainer="調教師甲"):
    """出走 1 頭。status を省くと着順の数字を入れる（実データと同じ）。人気を省くと馬番と同じ。"""
    return {"no": no, "finish": finish, "status": status or str(finish),
            "popularity": popularity or no, "jockey": jockey, "trainer": trainer}


def add_race(con, date, race_no, runs, win=None, place=None):
    """1 レースを足す。win / place は {馬番: 払戻}。place が空ならそのレースは複勝の払戻なし。"""
    con.execute("INSERT INTO races VALUES (?,?,?,?,?,?,?)",
                (date, race_no, "テスト", 200, "晴", 1.2, "条件"))
    for r in runs:
        con.execute(
            "INSERT INTO results (race_date,race_no,horse_no,finish,status,horse_name,sex,age,"
            "weight_carried,popularity,jockey,trainer) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (date, race_no, r["no"], r["finish"], r["status"], f"馬{r['no']}", "牡", 5, 700,
             r["popularity"], r["jockey"], r["trainer"]))
    for bet, pays in (("単勝", win or {}), ("複勝", place or {})):
        for no, amount in pays.items():
            con.execute("INSERT INTO payouts VALUES (?,?,?,?,?,NULL)",
                        (date, race_no, bet, str(no), amount))


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "banei.db"


@pytest.fixture
def con(db_path):
    # export.build は別の接続で開くので、書いたらすぐ見えるよう autocommit にする
    c = sqlite3.connect(db_path, isolation_level=None)
    c.execute("PRAGMA synchronous = OFF")
    c.executescript(RACES_SCHEMA)
    yield c
    c.close()


def add_two_races(con):
    """手で数えられる 2 レース（2025 シーズン）。

    1 レース目: 1 番人気（騎手A・調教師甲）が勝ち、2 番人気（騎手B・甲）2 着、3 番人気（騎手A・乙）
      3 着。3 頭立てなので複勝は 2 着まで
    2 レース目: 2 番人気（騎手A・甲）が勝ち、1 番人気（騎手B・乙）2 着、3 番人気（騎手B・乙）中止、
      4 番人気（騎手A・甲）取消
    """
    add_race(con, SEASON_2025, 1,
             [run(1, 1, jockey="騎手A", trainer="調教師甲"),
              run(2, 2, jockey="騎手B", trainer="調教師甲"),
              run(3, 3, jockey="騎手A", trainer="調教師乙")],
             win={1: 200}, place={1: 110, 2: 130})
    add_race(con, "2025-06-02", 1,
             [run(1, 2, popularity=1, jockey="騎手B", trainer="調教師乙"),
              run(2, 1, popularity=2, jockey="騎手A", trainer="調教師甲"),
              run(3, status="中止", popularity=3, jockey="騎手B", trainer="調教師乙"),
              run(4, status="取消", popularity=4, jockey="騎手A", trainer="調教師甲")],
             win={2: 450}, place={2: 160, 1: 120})


class TestLoad:
    def test_cells_by_role_and_key(self, con):
        add_two_races(con)
        data = people.load(con, 2025)
        # [N, WIN, TOP2, PLACE, WIN_PAY, PLACE_PAY] + 人気 1〜10 の出走数
        assert data.roles["jockey"][(2025, "騎手A")] == [
            3, 2, 2, 2, 650, 270, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
        # 中止は出走に入り、外れとして数える。取消は入らない
        assert data.roles["jockey"][(2025, "騎手B")] == [
            3, 0, 2, 2, 0, 250, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
        assert data.roles["trainer"][(2025, "調教師甲")][:6] == [3, 2, 3, 3, 650, 400]
        assert data.seasons[2025][:6] == [6, 2, 4, 4, 650, 520]

    def test_rates_are_season_win_rates_by_popularity(self, con):
        add_two_races(con)
        assert people.load(con, 2025).rates[2025][:4] == [0.5, 0.5, 0.0, 0.0]

    def test_dead_heat_counts_both_winners(self, con):
        add_race(con, SEASON_2025, 1, [run(1, 1), run(2, 1), run(3, 3, jockey="騎手B")],
                 win={1: 150, 2: 260}, place={1: 110, 2: 130})
        data = people.load(con, 2025)
        assert data.roles["jockey"][(2025, "騎手A")][:5] == [2, 2, 2, 2, 410]
        assert data.rates[2025][:2] == [1.0, 1.0]

    def test_unclosed_season_and_races_without_place_payouts_are_excluded(self, con):
        add_race(con, "2026-04-01", 1, [run(1, 1)], win={1: 100}, place={1: 100})
        add_race(con, SEASON_2025, 1, [run(1, 1), run(2, 2)], win={1: 140}, place={})
        data = people.load(con, 2025)
        assert data.roles == {"jockey": {}, "trainer": {}} and data.seasons == {}


class TestMetrics:
    def test_hand_counted_values(self, con):
        add_two_races(con)
        data = people.load(con, 2025)
        rates = data.rates[2025]
        a = data.roles["jockey"][(2025, "騎手A")]
        # 見込み = 人気 1（勝率 0.5）+ 人気 2（0.5）+ 人気 3（0）= 1.0
        assert people.metrics(a, people.expected(a, rates)) == {
            "n": 3, "win_rate": 66.7, "top2_rate": 66.7, "place_rate": 66.7,
            "win_roi": 216.7, "place_roi": 90.0, "wins": 2,
            "avg_popularity": 2.0, "expected_wins": 1.0, "wins_over_expected": 1.0,
        }
        b = data.roles["jockey"][(2025, "騎手B")]
        assert people.metrics(b, people.expected(b, rates))["wins_over_expected"] == -1.0
        t = data.roles["trainer"][(2025, "調教師甲")]  # 人気 1・2・2 で 2 勝
        m = people.metrics(t, people.expected(t, rates))
        assert (m["avg_popularity"], m["expected_wins"], m["wins_over_expected"]) == (1.67, 1.5, 0.5)
```

- [ ] **Step 4: テストが失敗することを確かめる**

Run: `uv run pytest tests/test_people.py -q`
Expected: FAIL（`ImportError: cannot import name 'people'`）

- [ ] **Step 5: people.py の前半を書く**

`src/banei/export/people.py` を新規作成:

```python
"""騎手・調教師ページの集計。

設計: docs/superpowers/specs/2026-10-14-people-pages-design.md

- 対象の出走・締め・指標の定義は探索 UI と同じ（explore.py のものを使う）。定義が 2 か所に
  分かれると、探索 UI と人のページの数字が食い違う
- 単位は 役割（騎手・調教師）× DB の略称 × シーズン。2007 シーズンから 1 シーズンずつ載せる。
  最初の版で締めたシーズンまでを一度に出すので、版の差で切り出されるのは新しいシーズンだけ
- 30 件未満の人・シーズンは消さずに「その他」にまとめる（pooled）。消すと、シーズンの合計からの
  引き算で値が割り出せる
- 平均人気と見込み勝ち数は、人気別の出走数（10 個）の重み付き合計。この種の値を増やすと人気別の
  内訳が連立方程式で割り出せるようになるので、2 つより増やさない
"""

import sqlite3
from dataclasses import dataclass

from banei.export import explore
from banei.export.explore import N, WIN

ROLES = ("jockey", "trainer")
ROLE_NAMES = {"jockey": "騎手", "trainer": "調教師"}

# 1 欄の集計値: explore と同じ [N, WIN, TOP2, PLACE, WIN_PAY, PLACE_PAY] に続けて、人気 1〜10 の
# 出走数。すべて整数で持つ（足し合わせても誤差が出ず、毎回同じ値になる。検査 3 の前提）
POPULARITIES = range(1, 11)
POP = 6
WIDTH = POP + len(POPULARITIES)

Cells = dict[tuple[int, str], list[int]]  # (シーズン, 略称) → 集計値


@dataclass(frozen=True)
class Loaded:
    roles: dict[str, Cells]  # 役割 → (シーズン, 略称) → 集計値
    seasons: dict[int, list[int]]  # シーズン → そのシーズン全体の集計値
    rates: dict[int, list[float]]  # シーズン → 人気 1〜10 の勝率（見込み勝ち数の重み）


def _add(acc: list[int], m: list[int]) -> None:
    for i, v in enumerate(m):
        acc[i] += v


def load(con: sqlite3.Connection, through: int) -> Loaded:
    """締めたシーズン（through まで）の出走を、役割・略称・シーズンごとに集計する。

    人気が 1〜10 以外の出走と、略称が空の出走は入れない。母数（explore.population）には
    入るので、検査 2（欄の合計 = 対象出走数）で止まる。黙って除くと集計が歪む。
    """
    sql = explore.STARTERS + f"""
    SELECT s.season, s.jockey, s.trainer, s.popularity, {explore.RUN_VALUES}
    FROM s
    {explore.PAYOUTS}
    """
    roles: dict[str, Cells] = {role: {} for role in ROLES}
    seasons: dict[int, list[int]] = {}
    wins: dict[int, list[int]] = {}  # シーズン → 人気 1〜10 の勝ち数
    for season, jockey, trainer, popularity, *values in con.execute(
            sql, {"end": explore.season_end(through)}):
        if popularity not in POPULARITIES:
            continue
        run = [1, *values, *([0] * len(POPULARITIES))]
        run[POP + popularity - 1] = 1
        _add(seasons.setdefault(season, [0] * WIDTH), run)
        wins.setdefault(season, [0] * len(POPULARITIES))[popularity - 1] += run[WIN]
        for role, key in zip(ROLES, (jockey, trainer), strict=True):
            if key:
                _add(roles[role].setdefault((season, key), [0] * WIDTH), run)
    rates = {
        season: [w / n if n else 0.0 for w, n in zip(wins[season], m[POP:], strict=True)]
        for season, m in seasons.items()
    }
    return Loaded(roles, seasons, rates)


def expected(m: list[int], rates: list[float]) -> float:
    """見込み勝ち数。人気ごとの出走数 × そのシーズン全体のその人気の勝率 の合計。"""
    return sum(m[POP + i] * r for i, r in enumerate(rates))


def metrics(m: list[int], exp: float) -> dict:
    """1 欄の指標。率と回収率は探索 UI と同じ。見込みとの差は表に出す見込み勝ち数（丸めた値）から出す。"""
    e = round(exp, 1)
    return {
        **explore.metrics(m),
        "wins": m[WIN],
        "avg_popularity": round(sum(p * m[POP + p - 1] for p in POPULARITIES) / m[N], 2),
        "expected_wins": e,
        "wins_over_expected": round(m[WIN] - e, 1),
    }
```

- [ ] **Step 6: テストが通ることを確かめる**

Run: `uv run pytest tests/test_people.py -q && uv run ruff check . && uv run pytest -q`
Expected: 全件 PASS、ruff の指摘なし

- [ ] **Step 7: コミット**

```bash
git add src/banei/export/explore.py src/banei/export/people.py tests/test_people.py
git commit -F - <<'EOF'
騎手・調教師ページの集計（人ごと・シーズンごとの成績と見込み勝ち数）を足す

対象の出走と指標を探索 UI と同じ定義にするため、explore.py の SQL と指標を共有名にして使う。
2 か所に書くと、探索 UI と人のページの数字が食い違う。
見込み勝ち数は人気別の出走数を整数で持って最後に掛ける。足し合わせの順で値が揺れないようにし、
締めたシーズンの比較（検査 3）が誤って止まらないようにするため。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 2: 「その他」へのまとめ方と役割ごとの JSON・検査 2（people.py 中盤）

**Files:**
- Modify: `src/banei/export/people.py`（末尾に追記）
- Test: `tests/test_people.py`（末尾に追記）

**Interfaces:**
- Consumes: Task 1 の `Loaded`, `load`, `expected`, `metrics`, `WIDTH`, `POP`, `_add`
- Produces:
  - `people.pooled(counts: dict[str, int]) -> set[str]` — 1 シーズン分の {略称: 出走数} から「その他」にまとめる略称
  - `people.build_role(cells: Cells, data: Loaded) -> dict` — `{"seasons": [{"season", "total", "other"}], "people": [{"key", "seasons", "pooled_seasons", "career"}]}`。`other` は `{"people_count": int, **metrics}` か `None`、`career` は `{"first_season", "last_season", **metrics}` か `None`。`people` は略称の順、`seasons` はシーズンの昇順
  - `people.completeness(role: str, cells: Cells, population: dict[int, int]) -> list[str]` — 検査 2
  - `people.build_roles(con, through: int) -> tuple[dict | None, list[str]]` — `{"jockey": build_role(...), "trainer": ...}`。締めたシーズンの出走が無ければ `(None, [])`
  - `people.flatten(payload: dict) -> list[dict]` — `payload["roles"]` の全行（シーズン全体・その他・個人の欄・通算）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_people.py` の import を次にする（ruff の I001 に合わせた並び）:

```python
import datetime as dt
import random
import sqlite3

import pytest

from banei.db.schema import RACES_SCHEMA
from banei.export import explore, people
from banei.export.aggregates import MIN_GROUP_SIZE, policy_violations
```

末尾に追記:

```python
def vec(n, wins=0, popularity=1):
    """1 欄の集計値。n 出走がすべて同じ人気で、wins 回勝った。"""
    m = [0] * people.WIDTH
    m[explore.N], m[explore.WIN] = n, wins
    m[people.POP + popularity - 1] = n
    return m


def loaded(cells):
    """騎手の欄だけの Loaded。シーズン全体はその合計、人気 1 の勝率は 0.1 とする。"""
    seasons = {}
    for (season, _), m in cells.items():
        acc = seasons.setdefault(season, [0] * people.WIDTH)
        for i, v in enumerate(m):
            acc[i] += v
    rates = {s: [0.1] + [0.0] * 9 for s in seasons}
    return people.Loaded(roles={"jockey": cells, "trainer": {}}, seasons=seasons, rates=rates)


class TestPooled:
    @pytest.mark.parametrize(("counts", "expected"), [
        ({"A": 100, "B": 40}, set()),
        ({"A": 100, "B": 20, "C": 15}, {"B", "C"}),  # 35 件で足りる
        ({"A": 100, "B": 40, "C": 10}, {"B", "C"}),  # 10 件では足りず、少ない B を移す
        ({"A": 50, "B": 50, "C": 5}, {"A", "C"}),  # 同数なら略称の順
        ({"A": 10}, {"A"}),  # シーズン全体が 30 件未満（公開ポリシーの検査で止まる）
        ({}, set()),
    ])
    def test_pooled(self, counts, expected):
        assert people.pooled(counts) == expected

    def test_pool_is_never_a_single_person(self):
        # 1 人だけだと「その他」の値がその人の値になる
        rng = random.Random(0)
        for _ in range(500):
            counts = {f"P{i}": rng.choice([rng.randint(1, 29), rng.randint(30, 300)])
                      for i in range(rng.randint(1, 8))}
            if sum(counts.values()) < MIN_GROUP_SIZE:
                continue
            pool = people.pooled(counts)
            assert not pool or (len(pool) >= 2
                                and sum(counts[k] for k in pool) >= MIN_GROUP_SIZE)
            assert all(counts[k] >= MIN_GROUP_SIZE for k in counts if k not in pool)


class TestBuildRole:
    CELLS = {(2024, "A"): vec(40, 4), (2024, "B"): vec(5),
             (2025, "A"): vec(50, 5), (2025, "B"): vec(60, 6)}

    def test_small_season_goes_to_other_with_the_smallest_neighbour(self):
        data = loaded(self.CELLS)
        role = people.build_role(data.roles["jockey"], data)
        s2024, s2025 = role["seasons"]
        assert (s2024["season"], s2024["total"]["n"]) == (2024, 45)
        assert (s2024["other"]["people_count"], s2024["other"]["n"]) == (2, 45)
        assert s2025["other"] is None and s2025["total"]["n"] == 110
        a, b = role["people"]
        assert (a["key"], a["pooled_seasons"]) == ("A", [2024])
        assert [s["season"] for s in a["seasons"]] == [2025]
        assert (b["key"], b["pooled_seasons"]) == ("B", [2024])

    def test_career_excludes_pooled_seasons(self):
        # 入れると、通算から個人のシーズンを引いて「その他」にまとめた値が出る
        data = loaded(self.CELLS)
        a = people.build_role(data.roles["jockey"], data)["people"][0]
        assert (a["career"]["n"], a["career"]["wins"]) == (50, 5)
        assert (a["career"]["first_season"], a["career"]["last_season"]) == (2025, 2025)
        assert a["career"]["expected_wins"] == 5.0  # 50 出走 × 人気 1 の勝率 0.1

    def test_career_sums_published_seasons(self):
        data = loaded({(2024, "A"): vec(40, 4), (2025, "A"): vec(50, 5)})
        c = people.build_role(data.roles["jockey"], data)["people"][0]["career"]
        assert (c["n"], c["wins"], c["expected_wins"]) == (90, 9, 9.0)
        assert (c["first_season"], c["last_season"]) == (2024, 2025)

    def test_person_with_every_season_pooled_has_no_career(self):
        data = loaded({(2024, "A"): vec(10), (2024, "B"): vec(25)})
        role = people.build_role(data.roles["jockey"], data)
        assert [p["career"] for p in role["people"]] == [None, None]

    def test_pooling_is_decided_per_season(self):
        # 新人はデビューした年だけ「その他」に入り、翌シーズンからは個人の欄に載る
        data = loaded({(2024, "A"): vec(100), (2024, "新人"): vec(10), (2024, "B"): vec(90),
                       (2025, "A"): vec(100), (2025, "新人"): vec(40), (2025, "B"): vec(90)})
        role = people.build_role(data.roles["jockey"], data)
        newbie = next(p for p in role["people"] if p["key"] == "新人")
        assert newbie["pooled_seasons"] == [2024]
        assert [s["season"] for s in newbie["seasons"]] == [2025]


class TestBuildRoles:
    def test_no_closed_seasons_gives_none(self, con):
        add_race(con, "2026-05-10", 1, [run(1, 1), run(2, 2)],
                 win={1: 300}, place={1: 110, 2: 120})
        assert people.build_roles(con, 2025) == (None, [])

    def test_unexpected_popularity_is_reported(self, con):
        add_race(con, SEASON_2025, 1, [run(1, 1), run(2, 2, popularity=11)],
                 win={1: 300}, place={1: 110, 2: 120})
        _, problems = people.build_roles(con, 2025)
        # 騎手・調教師の両方で、欄の合計 1 が対象出走数 2 と合わない
        assert len(problems) == 2 and all("対象出走数 2" in p for p in problems)

    def test_missing_popularity_is_reported(self, con):
        add_race(con, SEASON_2025, 1, [run(1, 1), run(2, 2)],
                 win={1: 300}, place={1: 110, 2: 120})
        con.execute("UPDATE results SET popularity = NULL WHERE horse_no = 2")
        assert len(people.build_roles(con, 2025)[1]) == 2

    def test_missing_jockey_is_reported_for_jockeys_only(self, con):
        add_race(con, SEASON_2025, 1, [run(1, 1), run(2, 2, jockey="")],
                 win={1: 300}, place={1: 110, 2: 120})
        _, problems = people.build_roles(con, 2025)
        assert len(problems) == 1 and "騎手" in problems[0]

    def test_tiny_season_is_a_policy_violation_not_a_crash(self, con):
        # 6 出走しかないシーズンは全員を「その他」にしても 30 件に届かない
        add_two_races(con)
        roles, problems = people.build_roles(con, 2025)
        assert problems == []
        rows = people.flatten({"roles": roles})
        # 役割ごとに シーズン全体 1 +「その他」1。個人の欄と通算は無い
        assert len(rows) == 4
        assert any("下限" in p for p in policy_violations("people", rows))
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `uv run pytest tests/test_people.py -q`
Expected: FAIL（`AttributeError: module 'banei.export.people' has no attribute 'pooled'` など）

- [ ] **Step 3: 実装を書く**

`src/banei/export/people.py` の import に `from banei.export.aggregates import MIN_GROUP_SIZE` を足し、末尾に追記:

```python
def pooled(counts: dict[str, int]) -> set[str]:
    """1 シーズン分の {略称: 出走数} から「その他」にまとめる略称。

    30 件未満の人を入れ、「その他」が 1〜29 件なら、残りで出走数の最も少ない人（同数なら略称の順）を
    30 件以上になるまで移す。シーズン全体が 30 件以上なら、空でない「その他」は必ず 2 人以上になる
    （1 人だとその人の値が出る）。全体が 30 件未満なら全員を入れても届かないが、そのまま返す
    （公開ポリシーの検査で止まる）。
    """
    pool = {k for k, n in counts.items() if n < MIN_GROUP_SIZE}
    while 0 < sum(counts[k] for k in pool) < MIN_GROUP_SIZE:
        rest = [k for k in counts if k not in pool]
        if not rest:
            break
        pool.add(min(rest, key=lambda k: (counts[k], k)))
    return pool


def build_role(cells: Cells, data: Loaded) -> dict:
    """1 つの役割の JSON。シーズンごとの全体と「その他」、人ごとのシーズンの欄と通算。

    まとめ方はシーズンごとに独立に決める。締めたシーズンの顔ぶれは、データが変わらない限り
    後から変わらない。通算は個人の欄に載せたシーズンだけの合計（まとめたシーズンを含めると、
    通算から個人の欄を引いて「その他」にまとめた値が出る）。
    """
    by_season: dict[int, dict[str, list[int]]] = {}
    for (season, key), m in cells.items():
        by_season.setdefault(season, {})[key] = m
    seasons_out = []
    acc: dict[str, dict] = {}
    for season in sorted(data.seasons):
        rates = data.rates[season]
        here = by_season.get(season, {})
        pool = pooled({k: m[N] for k, m in here.items()})
        other = [0] * WIDTH
        for k in pool:
            _add(other, here[k])
        total = data.seasons[season]
        seasons_out.append({
            "season": season,
            "total": metrics(total, expected(total, rates)),
            "other": ({"people_count": len(pool), **metrics(other, expected(other, rates))}
                      if pool else None),
        })
        for key in sorted(here):
            p = acc.setdefault(key, {"seasons": [], "pooled_seasons": [],
                                     "sum": [0] * WIDTH, "expected": 0.0})
            if key in pool:
                p["pooled_seasons"].append(season)
                continue
            e = expected(here[key], rates)
            p["seasons"].append({"season": season, **metrics(here[key], e)})
            _add(p["sum"], here[key])
            p["expected"] += e
    people_out = []
    for key in sorted(acc):
        p = acc[key]
        career = None
        if p["seasons"]:
            career = {"first_season": p["seasons"][0]["season"],
                      "last_season": p["seasons"][-1]["season"],
                      **metrics(p["sum"], p["expected"])}
        people_out.append({"key": key, "seasons": p["seasons"],
                           "pooled_seasons": p["pooled_seasons"], "career": career})
    return {"seasons": seasons_out, "people": people_out}


def completeness(role: str, cells: Cells, population: dict[int, int]) -> list[str]:
    """検査 2: シーズンごとに、欄の出走数の合計が対象出走数と一致する（もれなく分けている）。"""
    got: dict[int, int] = {}
    for (season, _), m in cells.items():
        got[season] = got.get(season, 0) + m[N]
    name = ROLE_NAMES[role]
    return [
        f"people（{name}）: {season} シーズンの欄の合計 {got.get(season, 0)} が対象出走数 {n} と"
        f"一致しない（人気が 1〜10 以外か、{name}の無い出走がある）"
        for season, n in sorted(population.items()) if got.get(season, 0) != n
    ]


def build_roles(con: sqlite3.Connection, through: int) -> tuple[dict | None, list[str]]:
    """締めたシーズン（through まで）の集計。戻り値は (役割 → JSON, 検査 2 の違反)。

    締めたシーズンの出走が 1 件も無ければ (None, [])（テスト用の小さな DB など。探索 UI と同じ）。
    """
    population = explore.population(con, through)
    if not population:
        return None, []
    data = load(con, through)
    problems: list[str] = []
    roles = {}
    for role in ROLES:
        problems += completeness(role, data.roles[role], population)
        roles[role] = build_role(data.roles[role], data)
    return roles, problems


def flatten(payload: dict) -> list[dict]:
    """公開ポリシーの検査（aggregates.policy_violations）にかける行。roles の全行。"""
    rows: list[dict] = []
    for role in payload["roles"].values():
        for s in role["seasons"]:
            rows.append(s["total"])
            if s["other"] is not None:
                rows.append(s["other"])
        for p in role["people"]:
            rows += p["seasons"]
            if p["career"] is not None:
                rows.append(p["career"])
    return rows
```

- [ ] **Step 4: テストが通ることを確かめる**

Run: `uv run pytest tests/test_people.py -q && uv run ruff check . && uv run pytest -q`
Expected: 全件 PASS、ruff の指摘なし

- [ ] **Step 5: コミット**

```bash
git add src/banei/export/people.py tests/test_people.py
git commit -F - <<'EOF'
30 件未満の人・シーズンを「その他」にまとめ、役割ごとの JSON を組み立てる

消さずにまとめるのは、シーズンの合計からの引き算で消した値が割り出せるため。
まとめ方をシーズンごとに独立に決めるのは、探索 UI の区分のように版をまたいで固定すると、
デビュー年に少なかった新人が以後ずっと個人として出せなくなるため。
通算からまとめたシーズンを除くのも、通算との引き算で値が出るのを防ぐため。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 3: 正式名の対応表とページの一覧（people.py 後半の 1）

**Files:**
- Create: `src/banei/export/people.toml`
- Modify: `src/banei/export/people.py`（import と末尾に追記）
- Test: `tests/test_people.py`（末尾に追記）

**Interfaces:**
- Consumes: Task 2 の `build_role` の出力の形（`people[].key / seasons[].season / pooled_seasons`）、`ROLES`, `ROLE_NAMES`
- Produces:
  - `people.NAMES_PATH: Path` — `src/banei/export/people.toml`。テストは monkeypatch で差し替える
  - `people.Person(name: str, jockey: str | None, trainer: str | None)`（frozen dataclass）と `Person.keys() -> dict[str, str]`（役割 → 略称）
  - `people.load_names(path: Path) -> tuple[list[Person], list[str]]` — (人, 違反)
  - `people.slug_of(key: str) -> str`
  - `people.build_pages(roles: dict, names: list[Person], through: int) -> tuple[list[dict], list[str], list[str]]` — (ページ, 違反, 警告)。ページは `{"slug", "name", "name_confirmed", "jockey", "trainer", "active"}` で slug の順

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_people.py` の末尾に追記:

```python
def write_names(tmp_path, text):
    path = tmp_path / "people.toml"
    path.write_text(text, encoding="utf-8")
    return path


def role_people(spec):
    """build_pages に渡す役割の JSON（使う所だけ）。spec は {略称: (個人の欄のシーズン, まとめたシーズン)}。"""
    return {"seasons": [], "people": [
        {"key": k, "seasons": [{"season": s} for s in pub], "pooled_seasons": list(pool),
         "career": None}
        for k, (pub, pool) in spec.items()]}


class TestNames:
    def test_reads_people(self, tmp_path):
        path = write_names(tmp_path, """
[[person]]
name = "正式名一"
jockey = "正式名"
trainer = "正式名"
source = "https://example.invalid/ (2026-10-14 確認)"
""")
        assert people.load_names(path) == ([people.Person("正式名一", "正式名", "正式名")], [])

    @pytest.mark.parametrize("body", [
        'name = "名"\njockey = "略"',  # 出典が無い（推測で埋めない）
        'name = "名"\nsource = "s"',  # 略称が無い
        'name = ""\njockey = "略"\nsource = "s"',  # 空の名前
        'name = "名"\njokey = "略"\nsource = "s"',  # キーの綴り違い
        'name = "名"\njockey = 1\nsource = "s"',  # 文字列でない
    ])
    def test_rejects_incomplete_rows(self, tmp_path, body):
        names, problems = people.load_names(write_names(tmp_path, f"[[person]]\n{body}\n"))
        assert names == [] and len(problems) == 1

    def test_rejects_duplicate_keys(self, tmp_path):
        path = write_names(tmp_path, """
[[person]]
name = "一"
jockey = "略"
source = "s"
[[person]]
name = "二"
jockey = "略"
source = "s"
""")
        _, problems = people.load_names(path)
        assert len(problems) == 1 and "二重" in problems[0]

    def test_same_key_in_two_roles_is_not_a_duplicate(self, tmp_path):
        path = write_names(
            tmp_path, '[[person]]\nname = "一"\njockey = "略"\ntrainer = "略"\nsource = "s"\n')
        assert people.load_names(path)[1] == []

    @pytest.mark.parametrize("text", ["[[person]\n", "person = 1\n"])
    def test_unreadable_table_is_reported(self, tmp_path, text):
        names, problems = people.load_names(write_names(tmp_path, text))
        assert names == [] and len(problems) == 1 and "people.toml" in problems[0]

    def test_missing_file_is_reported(self, tmp_path):
        assert people.load_names(tmp_path / "none.toml")[1]

    def test_empty_table_is_fine(self, tmp_path):
        assert people.load_names(write_names(tmp_path, "# 空\n")) == ([], [])

    def test_repository_table_is_valid(self):
        # コミットする対応表が読めること（読めないと export が止まる）
        assert people.load_names(people.NAMES_PATH)[1] == []


class TestPages:
    ROLES = {
        "jockey": role_people({"鈴木恵": ([2024, 2025], []), "藤野俊": ([2025], []),
                               "林　豊": ([2010], [])}),
        "trainer": role_people({"藤野俊": ([2025], []), "西弘美": ([2020], [2025])}),
    }

    def build(self, names):
        return people.build_pages(self.ROLES, names, 2025)

    def test_listed_person_gets_one_page_for_both_roles(self):
        pages, problems, warnings = self.build([people.Person("藤野俊介", "藤野俊", "藤野俊")])
        assert problems == []
        assert next(p for p in pages if p["slug"] == "藤野俊") == {
            "slug": "藤野俊", "name": "藤野俊介", "name_confirmed": True,
            "jockey": "藤野俊", "trainer": "藤野俊", "active": True}
        assert not any("藤野俊" in w for w in warnings)

    def test_unlisted_key_gets_a_page_under_the_abbreviation_with_a_warning(self):
        pages, problems, warnings = self.build([])
        assert problems == []
        p = next(p for p in pages if p["slug"] == "鈴木恵")
        assert (p["name"], p["name_confirmed"]) == ("鈴木恵", False)
        assert any("「鈴木恵」" in w for w in warnings)

    def test_unlisted_same_key_in_both_roles_is_one_page(self):
        # 騎手から調教師に移った新人を表に足す前でも、URL が重複して export が止まらない
        pages, problems, warnings = self.build([])
        same = [p for p in pages if p["slug"] == "藤野俊"]
        assert problems == [] and len(same) == 1
        assert (same[0]["jockey"], same[0]["trainer"]) == ("藤野俊", "藤野俊")
        assert sum("「藤野俊」" in w for w in warnings) == 1

    def test_slug_drops_spaces(self):
        pages, _, _ = self.build([])
        assert "林豊" in {p["slug"] for p in pages}

    def test_active_means_ran_in_the_latest_closed_season(self):
        # 西弘美は 2025 に「その他」にまとめられたが、出走はしている
        pages, _, _ = self.build([])
        assert {p["slug"]: p["active"] for p in pages} == {
            "鈴木恵": True, "藤野俊": True, "林豊": False, "西弘美": True}

    def test_pages_are_sorted_by_slug(self):
        pages, _, _ = self.build([])
        assert [p["slug"] for p in pages] == sorted(p["slug"] for p in pages)

    def test_slug_collision_is_reported(self):
        # 表で騎手だけの人とした「藤野俊」と、表に無い調教師「藤野俊」が同じ URL になる
        _, problems, _ = self.build([people.Person("騎手の人", "藤野俊", None)])
        assert len(problems) == 1 and "/people/藤野俊/" in problems[0]

    def test_table_entry_without_data_makes_no_page(self):
        pages, _, _ = self.build([people.Person("未来の新人", "新人", None)])
        assert "新人" not in {p["slug"] for p in pages}

    def test_renaming_changes_only_the_name(self):
        a, _, _ = self.build([people.Person("名前一", "鈴木恵", None)])
        b, _, _ = self.build([people.Person("名前二", "鈴木恵", None)])
        assert [p["slug"] for p in a] == [p["slug"] for p in b]
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `uv run pytest tests/test_people.py -q`
Expected: FAIL（`AttributeError: module 'banei.export.people' has no attribute 'NAMES_PATH'` など）

- [ ] **Step 3: 対応表の雛形を作る**

`src/banei/export/people.toml` を新規作成（中身は Task 5 で足す）:

```toml
# 騎手・調教師の正式名の対応表（設計: docs/superpowers/specs/2026-10-14-people-pages-design.md §7）
#
# DB の騎手・調教師名は結果ページの 3 文字の略称（鈴木恵・竹ケ茉・林　豊）。ここで正式名を付け、
# 騎手と調教師を兼ねた（移った）人を 1 ページにまとめる。表示だけの話で、集計と URL は略称で決まる。
#
# - 公式の紹介ページなどで確かめた人だけを書く。推測で埋めない（書かなければ略称のまま表示される）
# - source に確かめた出典と確認日を書く
# - 略称は DB の表記そのまま（全角スペースも含める）
#
# [[person]]
# name = "正式名"
# jockey = "騎手の略称"      # 騎手でなければ書かない
# trainer = "調教師の略称"   # 調教師でなければ書かない
# source = "https://… (YYYY-MM-DD 確認)"
```

- [ ] **Step 4: 実装を書く**

`src/banei/export/people.py` の import を次にする:

```python
import sqlite3
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from banei.export import explore
from banei.export.aggregates import MIN_GROUP_SIZE
from banei.export.explore import N, WIN
```

`ROLE_NAMES` の下に足す:

```python
NAMES_PATH = Path(__file__).with_name("people.toml")
NAME_FIELDS = frozenset({"name", "jockey", "trainer", "source"})
```

末尾に追記:

```python
@dataclass(frozen=True)
class Person:
    """対応表の 1 行。jockey / trainer は DB の略称（その役割でなければ None）。"""

    name: str
    jockey: str | None
    trainer: str | None

    def keys(self) -> dict[str, str]:
        return {role: key for role, key in zip(ROLES, (self.jockey, self.trainer), strict=True)
                if key}


def load_names(path: Path) -> tuple[list[Person], list[str]]:
    """対応表を読む。戻り値は (人, 違反)。違反があると表示が誤るので export を止める。

    出典（source）の無い行は受け付けない。確かめていない名前を推測で入れないため。
    """
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        return [], [f"people.toml を読めない（{e!r}）"]
    rows = data.get("person", [])
    if not isinstance(rows, list):
        return [], ["people.toml: [[person]] の並びになっていない"]
    out: list[Person] = []
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for i, row in enumerate(rows, start=1):
        where = f"people.toml の {i} 人目"
        if not isinstance(row, dict) or set(row) - NAME_FIELDS:
            problems.append(f"{where}: 使えるキーは {sorted(NAME_FIELDS)} だけ")
            continue
        if not all(isinstance(v, str) and v.strip() for v in row.values()):
            problems.append(f"{where}: 値は空でない文字列にする")
            continue
        if not {"name", "source"} <= set(row) or not {"jockey", "trainer"} & set(row):
            problems.append(f"{where}: name と source、jockey か trainer の少なくとも一方が要る")
            continue
        person = Person(row["name"], row.get("jockey"), row.get("trainer"))
        for role, key in person.keys().items():
            if (role, key) in seen:
                problems.append(f"people.toml: {ROLE_NAMES[role]}の略称「{key}」が二重に登録されている")
            seen.add((role, key))
        out.append(person)
    return out, problems


def slug_of(key: str) -> str:
    """URL の名前。DB の略称から空白（全角を含む）を除いたもの。対応表を直しても変わらない。"""
    return "".join(key.split())


def build_pages(
    roles: dict, names: list[Person], through: int
) -> tuple[list[dict], list[str], list[str]]:
    """表示用のページの一覧。戻り値は (ページ, 違反, 警告)。

    対応表の人は 1 人 1 ページ（騎手と調教師を兼ねた人もまとめる）。表に無い略称は略称のまま
    ページにして警告する（5/1 に新人が出ても export を止めない）。騎手と調教師で同じ略称が
    表に無ければ同じ人として 1 ページにする（既知の兼任 8 人はすべてそう）。
    現役（active）は、最新の締めたシーズンに出走がある（「その他」にまとめた場合も含む）こと。
    """
    present = {role: {p["key"]: p for p in roles[role]["people"]} for role in ROLES}

    def ran_in(role: str, key: str) -> bool:
        p = present[role][key]
        return through in p["pooled_seasons"] or any(s["season"] == through for s in p["seasons"])

    def page(name: str, confirmed: bool, keys: dict[str, str]) -> dict:
        return {
            "slug": slug_of(keys.get("jockey") or keys["trainer"]),
            "name": name,
            "name_confirmed": confirmed,
            "jockey": keys.get("jockey"),
            "trainer": keys.get("trainer"),
            "active": any(ran_in(role, key) for role, key in keys.items()),
        }

    pages: list[dict] = []
    claimed: set[tuple[str, str]] = set()
    for person in names:
        keys = {role: key for role, key in person.keys().items() if key in present[role]}
        if keys:
            claimed |= set(keys.items())
            pages.append(page(person.name, True, keys))
    unlisted: dict[str, dict[str, str]] = {}
    for role in ROLES:
        for key in present[role]:
            if (role, key) not in claimed:
                unlisted.setdefault(key, {})[role] = key
    warnings = [
        f"対応表に無い略称「{key}」（{'・'.join(ROLE_NAMES[r] for r in keys)}）。略称のままページを作る"
        for key, keys in sorted(unlisted.items())
    ]
    pages += [page(key, False, keys) for key, keys in sorted(unlisted.items())]
    pages.sort(key=lambda p: p["slug"])
    problems = [
        f"people: URL「/people/{slug}/」が重複する。同一人物なら対応表で 1 行にまとめる"
        for slug, n in sorted(Counter(p["slug"] for p in pages).items()) if n > 1
    ]
    return pages, problems, warnings
```

- [ ] **Step 5: テストが通ることを確かめる**

Run: `uv run pytest tests/test_people.py -q && uv run ruff check . && uv run pytest -q`
Expected: 全件 PASS、ruff の指摘なし

- [ ] **Step 6: コミット**

```bash
git add src/banei/export/people.py src/banei/export/people.toml tests/test_people.py
git commit -F - <<'EOF'
騎手・調教師の正式名の対応表と、1 人 1 ページの一覧を作る

DB の名前は 3 文字の略称なので、検索で来る読者のために正式名を付ける。出典の無い行は
受け付けない（推測で埋めない）。URL は略称から作り、正式名が後から分かっても変わらないように
する。表に無い略称は止めずに略称のままページにする。5/1 に新人が出るたびに export が
止まると、サイトの更新がそのたびに止まるため。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 4: build・締めの検査（検査 3）と export への組み込み

**Files:**
- Modify: `src/banei/export/people.py`（import と末尾に追記）
- Modify: `src/banei/export/__init__.py`（全体を置き換え）
- Modify: `tests/test_explore.py:22-36`（`add_race` の INSERT に騎手・調教師）
- Test: `tests/test_people.py`（末尾に追記）

**Interfaces:**
- Consumes: Task 2 の `build_roles`, `flatten`、Task 3 の `NAMES_PATH`, `load_names`, `build_pages`
- Produces:
  - `people.OUTPUT = "people"` — 出力名（`web/src/data/people.json`）
  - `people.build(con, today: dt.date, previous_dir: Path | None = None, names_path: Path | None = None) -> tuple[dict | None, list[str], list[str]]` — (`{"through_season", "roles", "pages"}` か None, 違反, 警告)
  - `export.build()` の戻り値に `"people"` が加わる（締めたシーズンの出走があるとき）。警告は標準エラーに `警告: …` と出す

- [ ] **Step 1: 探索 UI のテストの合成 DB に騎手・調教師を入れる**

export が人のページも作るようになると、騎手・調教師が NULL の合成 DB は検査 2 で止まる。
`tests/test_explore.py` の `add_race` の results の INSERT を次に置き換える:

```python
        # 騎手・調教師も入れる。export は人のページ（people.py）も作り、無いと検査 2 で止まる
        con.execute(
            "INSERT INTO results (race_date,race_no,horse_no,finish,status,horse_name,sex,age,"
            "weight_carried,popularity,jockey,trainer) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (date, race_no, h["no"], h["finish"], h["status"], f"馬{h['no']}", h["sex"],
             h["age"], h["weight"], h["popularity"], "騎手", "調教師"))
```

Run: `uv run pytest tests/test_explore.py -q`
Expected: 全件 PASS（まだ export は people を呼ばないので変化なし）

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_people.py` の import を次にする:

```python
import datetime as dt
import json
import random
import sqlite3

import pytest

from banei import export
from banei.db.schema import RACES_SCHEMA
from banei.export import explore, people
from banei.export.aggregates import MIN_GROUP_SIZE, policy_violations
```

末尾に追記:

```python
def add_season(con, season, n_races=40, start_no=1):
    """1 シーズン分。騎手A・B と調教師甲・乙が n_races 回ずつ出走する。"""
    for i in range(n_races):
        add_race(con, f"{season}-05-{i % 28 + 1:02d}", start_no + i // 28,
                 [run(1, 1, jockey="騎手A", trainer="調教師甲"),
                  run(2, 2, jockey="騎手B", trainer="調教師乙")],
                 win={1: 340}, place={1: 120, 2: 150})


def add_extra_race(con, date):
    """騎手A・B が 1 回ずつ出走するレースを 1 つ足す（締めたシーズンの補完の再現などに使う）。"""
    add_race(con, date, 1, [run(1, 1), run(2, 2, jockey="騎手B", trainer="調教師乙")],
             win={1: 340}, place={1: 120, 2: 150})


@pytest.fixture
def big(con):
    for season in (2023, 2024, 2025):
        add_season(con, season)
    add_extra_race(con, "2026-05-10")  # 締めていない 2026 シーズン。入らないこと
    return con


@pytest.fixture
def names(tmp_path, monkeypatch):
    """騎手A と調教師甲だけ正式名を付けた対応表。export から使われるものも差し替える。"""
    path = tmp_path / "people.toml"
    path.write_text('[[person]]\nname = "正式名一"\njockey = "騎手A"\nsource = "テスト"\n'
                    '[[person]]\nname = "正式名二"\ntrainer = "調教師甲"\nsource = "テスト"\n',
                    encoding="utf-8")
    monkeypatch.setattr(people, "NAMES_PATH", path)
    return path


def read(out_dir):
    return json.loads((out_dir / "people.json").read_text(encoding="utf-8"))


class TestBuild:
    def test_payload(self, big, names):
        payload, problems, warnings = people.build(big, TODAY)
        assert problems == []
        assert payload["through_season"] == 2025
        jockeys = payload["roles"]["jockey"]
        assert [s["season"] for s in jockeys["seasons"]] == [2023, 2024, 2025]
        a = next(p for p in jockeys["people"] if p["key"] == "騎手A")
        assert (a["career"]["n"], a["career"]["wins"]) == (120, 120)  # 締めていない 2026 は入らない
        assert {p["slug"]: p["name"] for p in payload["pages"]} == {
            "騎手A": "正式名一", "騎手B": "騎手B", "調教師甲": "正式名二", "調教師乙": "調教師乙"}
        assert warnings == ["対応表に無い略称「調教師乙」（調教師）。略称のままページを作る",
                            "対応表に無い略称「騎手B」（騎手）。略称のままページを作る"]
        # 生成時刻を入れない。入れると毎日内容が変わり、検査 3 が成り立たない
        assert "generated_at" not in json.dumps(payload, ensure_ascii=False)

    def test_flatten_covers_every_row(self, big, names):
        payload, _, _ = people.build(big, TODAY)
        # 役割ごとに シーズン全体 3 + 2 人 ×（シーズン 3 + 通算 1）
        assert len(people.flatten(payload)) == 2 * (3 + 2 * 4)

    def test_nothing_without_closed_seasons(self, con, names):
        add_extra_race(con, "2026-05-10")
        assert people.build(con, TODAY) == (None, [], [])


class TestExport:
    """export に組み込まれ、締めたシーズンの変化（検査 3）と公開ポリシー違反で止まること。"""

    def test_people_json_is_written(self, big, db_path, tmp_path, names):
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        assert read(out_dir)["through_season"] == 2025

    def test_rerun_on_same_data_passes_check_3(self, big, db_path, tmp_path, names):
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        export.run(db_path, out_dir, today=dt.date(2026, 12, 1))  # 毎日回しても通る

    def test_new_closed_season_passes_check_3(self, big, db_path, tmp_path, names):
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        add_season(big, 2026, start_no=3)
        export.run(db_path, out_dir, today=dt.date(2027, 5, 1))
        assert read(out_dir)["through_season"] == 2026

    def test_changed_closed_season_stops_export(self, big, db_path, tmp_path, names):
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        before = (out_dir / "people.json").read_text(encoding="utf-8")
        add_extra_race(big, "2024-09-01")  # 締めた 2024 シーズンに、後から 1 レース補完された
        with pytest.raises(export.PolicyError, match="people: 締めたシーズン（2025 まで）が同じ"):
            export.run(db_path, out_dir, today=TODAY)
        assert (out_dir / "people.json").read_text(encoding="utf-8") == before

    def test_changed_closed_season_stops_export_when_through_advances(
        self, big, db_path, tmp_path, names
    ):
        # 補完で止まったまま 5/1 を迎えても、締めの進んだ版に素通りしない
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        add_extra_race(big, "2024-09-01")
        add_season(big, 2026, start_no=3)
        with pytest.raises(export.PolicyError,
                           match="people: 締めたシーズン（2025 まで）の内容が前回"):
            export.run(db_path, out_dir, today=dt.date(2027, 5, 1))

    def test_rewound_through_season_stops_export(self, big, db_path, tmp_path, names):
        out_dir = tmp_path / "out"
        add_season(big, 2026, start_no=3)
        export.run(db_path, out_dir, today=dt.date(2027, 5, 1))
        with pytest.raises(export.PolicyError, match="people: 締めが 2026 から 2025 に戻っている"):
            export.run(db_path, out_dir, today=TODAY)

    @pytest.mark.parametrize("text", [
        "{壊れた",
        '{"through_season": "2025", "roles": {}}',
        '{"through_season": 2025}',
        '{"through_season": 2025, "roles": []}',
    ])
    def test_unreadable_previous_output_stops_export(
        self, big, db_path, tmp_path, names, text
    ):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "people.json").write_text(text, encoding="utf-8")
        with pytest.raises(export.PolicyError, match="people: 前回の出力を読めない"):
            export.run(db_path, out_dir, today=TODAY)
        assert (out_dir / "people.json").read_text(encoding="utf-8") == text

    def test_renaming_in_the_table_passes_check_3(self, big, db_path, tmp_path, names):
        # 表示名は比べない。対応表の修正で export を止めないため
        out_dir = tmp_path / "out"
        export.run(db_path, out_dir, today=TODAY)
        names.write_text(names.read_text(encoding="utf-8").replace("正式名一", "正式名三"),
                         encoding="utf-8")
        export.run(db_path, out_dir, today=TODAY)
        assert "正式名三" in {p["name"] for p in read(out_dir)["pages"]}

    def test_broken_pooling_stops_export(self, big, db_path, tmp_path, names, monkeypatch):
        # 2025 シーズンに 5 回だけ乗った騎手C
        for i in range(5):
            add_race(big, f"2025-07-{i + 1:02d}", 1,
                     [run(1, 1, jockey="騎手C"), run(2, 2, jockey="騎手B", trainer="調教師乙")],
                     win={1: 340}, place={1: 120, 2: 150})
        export.run(db_path, tmp_path / "ok", today=TODAY)  # まとめる処理が正しければ通る
        # まとめる処理が壊れても、書き出し前の公開ポリシーの検査で止まる
        monkeypatch.setattr(people, "pooled", lambda counts: set())
        with pytest.raises(export.PolicyError, match=r"people\[\d+\]: 集約件数 5 が下限"):
            export.run(db_path, tmp_path / "out", today=TODAY)
        assert not (tmp_path / "out").exists() or not any((tmp_path / "out").rglob("*.json"))

    def test_pages_are_checked_for_identifying_keys(self, big, db_path, names, monkeypatch):
        real = people.build_pages

        def leaky(*args):
            pages, problems, warnings = real(*args)
            return [*pages, {"slug": "x", "horse_name": "馬"}], problems, warnings

        monkeypatch.setattr(people, "build_pages", leaky)
        with pytest.raises(export.PolicyError, match="horse_name"):
            export.build(db_path, today=TODAY)

    def test_broken_names_table_stops_export(self, big, db_path, names):
        names.write_text("[[person]\n", encoding="utf-8")
        with pytest.raises(export.PolicyError, match="people.toml"):
            export.build(db_path, today=TODAY)

    def test_warnings_are_printed(self, big, db_path, names, capsys):
        export.build(db_path, today=TODAY)
        assert "警告: 対応表に無い略称「騎手B」" in capsys.readouterr().err
```

- [ ] **Step 3: テストが失敗することを確かめる**

Run: `uv run pytest tests/test_people.py -q`
Expected: FAIL（`AttributeError: module 'banei.export.people' has no attribute 'build'` など）

- [ ] **Step 4: people.build と検査 3 を書く**

`src/banei/export/people.py` の import を次にする:

```python
import datetime as dt
import json
import sqlite3
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from banei.export import explore
from banei.export.aggregates import MIN_GROUP_SIZE
from banei.export.explore import N, WIN
```

`NAMES_PATH` の下に足す:

```python
OUTPUT = "people"  # 出力名（web/src/data/people.json）
```

末尾に追記:

```python
def _plain(obj):
    """JSON に書いて読み戻したもの。前回の出力（JSON から読んだもの）と同じ形で比べるため。"""
    return json.loads(json.dumps(obj, ensure_ascii=False))


def _previous(previous_dir: Path | None) -> tuple[dict | None, list[str]]:
    """前回の出力。無ければ（初回）None。読めない・形が想定外なら、上書きせず止めるため違反にする。"""
    if previous_dir is None:
        return None, []
    path = previous_dir / f"{OUTPUT}.json"
    if not path.exists():
        return None, []
    unreadable = f"{OUTPUT}: 前回の出力を読めない（{{}}）。中身を確かめるまで上書きしない"
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
        through, roles = prev["through_season"], prev["roles"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        return None, [unreadable.format(repr(e))]
    if type(through) is not int:
        return None, [unreadable.format(f"締め {through!r} が整数でない")]
    if not isinstance(roles, dict):
        return None, [unreadable.format("roles が辞書でない")]
    return prev, []


def _history_problems(
    con: sqlite3.Connection, roles: dict, through: int, prev: dict
) -> list[str]:
    """検査 3: 締めたシーズンの集計（roles）が前回の出力から変わっていない。

    締めが同じなら roles が同じこと。締めが進んだときも、今の DB から前回の締めで作り直して
    前回と比べる（止めて調べている最中に 5/1 が来ても、保留中の修正が素通りしない）。
    変わっていれば修正・補完があったということで、その差は小さな集計の漏れになる。
    表示（pages）は比べない。対応表の修正で止めないため。
    """
    prev_through = prev["through_season"]
    if prev_through > through:
        return [f"{OUTPUT}: 締めが {prev_through} から {through} に戻っている"]
    if prev_through == through:
        if _plain(roles) != prev["roles"]:
            return [f"{OUTPUT}: 締めたシーズン（{through} まで）が同じなのに内容が変わった。"
                    "過去のデータが修正・補完された可能性がある"]
        return []
    again, _ = build_roles(con, prev_through)
    if again is None or _plain(again) != prev["roles"]:
        return [f"{OUTPUT}: 締めたシーズン（{prev_through} まで）の内容が前回の出力と違う。"
                "過去のデータが修正・補完された可能性がある"]
    return []


def build(
    con: sqlite3.Connection,
    today: dt.date,
    previous_dir: Path | None = None,
    names_path: Path | None = None,
) -> tuple[dict | None, list[str], list[str]]:
    """人のページの JSON を作る。戻り値は (中身, 違反, 警告)。

    締めたシーズンの出走が無ければ中身は None。previous_dir に前回の出力があれば検査 3。
    names_path を省くと NAMES_PATH（呼ぶときに読むので、テストは monkeypatch で差し替えられる）。
    """
    through = explore.through_season(today)
    roles, problems = build_roles(con, through)
    if roles is None:
        return None, problems, []
    prev, found = _previous(previous_dir)
    problems += found
    if prev is not None:
        problems += _history_problems(con, roles, through, prev)
    names, found = load_names(names_path or NAMES_PATH)
    problems += found
    pages, found, warnings = build_pages(roles, names, through)
    problems += found
    return {"through_season": through, "roles": roles, "pages": pages}, problems, warnings
```

- [ ] **Step 5: export に組み込む**

`src/banei/export/__init__.py` を次に置き換える:

```python
"""集計結果を JSON として書き出す。Astro のビルド入力になる。

出力先は既定で `web/src/data/`。Astro からは `import data from '~/data/xxx.json'` で
読める。ここに出るのは集計値だけで、生データは含まれない（aggregates.py 参照）。
探索 UI の表は `explore/` 以下に（explore.py 参照）、騎手・調教師ページは `people.json` に
書く（people.py 参照）。
"""

import datetime as dt
import json
import sys
from pathlib import Path

from banei.config import RACES_DB
from banei.export import explore, people
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

    探索 UI の表（出力名 explore/…）と騎手・調教師ページ（people）は today（省略時は JST の
    今日）で締めを決め、previous_dir にある前回の出力と比べる（explore.build・people.build）。
    """
    today = today or explore.today_jst()
    previous = Path(previous_dir) if previous_dir is not None else None
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
        tables, problems = explore.build(con, today, previous)
        person, found, warnings = people.build(con, today, previous)
        problems += found
    finally:
        con.close()

    for w in warnings:
        print(f"警告: {w}", file=sys.stderr)
    for name, payload in out.items():
        rows = payload if isinstance(payload, list) else [payload]
        # summary の n_jockeys などはグループの大きさではなく実体の個数なので、
        # グループサイズの下限は当てない（個体特定キーの検査は行う）
        problems += policy_violations(name, rows, check_group_size=(name != "summary"))
    for name, payload in tables.items():
        problems += policy_violations(name, explore.flatten(payload))
    if person is not None:
        problems += policy_violations(people.OUTPUT, people.flatten(person))
        # ページの一覧は集計の行ではないので、個体特定キーの検査だけ当てる
        problems += policy_violations(f"{people.OUTPUT}.pages", person["pages"],
                                      check_group_size=False)
        tables[people.OUTPUT] = person
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

- [ ] **Step 6: テストが通ることを確かめる**

Run: `uv run pytest tests/test_people.py -q && uv run ruff check . && uv run pytest -q`
Expected: 全件 PASS（`test_export_policy.py` の `test_clean_build_succeeds` も含む。その DB は複勝の払戻が無いので people は None になる）

- [ ] **Step 7: 検査が違反を捕まえることを、検査をわざと壊して確かめる**

一時的に `_history_problems` の先頭に `return []` を足し、`uv run pytest tests/test_people.py -q -k "changed_closed or rewound"` が FAIL することを確かめてから元に戻す。同様に `completeness` の先頭に `return []` を足して `-k "unexpected_popularity or missing"` が FAIL することを確かめて戻す。

Run（戻した後）: `uv run pytest -q`
Expected: 全件 PASS

- [ ] **Step 8: コミット**

```bash
git add src/banei/export/people.py src/banei/export/__init__.py tests/test_people.py tests/test_explore.py
git commit -F - <<'EOF'
騎手・調教師ページを export に組み込み、締めたシーズンの変化を止める

人のページも探索 UI と同じく締めたシーズンまでで年 1 回だけ変わる。締めたシーズンの集計が
後から変わったら、その差が小さな集計の漏れになるので止める（探索 UI の検査 3 と同じ考え方）。
比べるのは集計（roles）だけで、表示（pages）は比べない。対応表の修正で止めないため。
探索 UI のテストの合成 DB には騎手・調教師を入れた。export が人のページも作るようになり、
NULL のままだと検査 2 で止まるため。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 5: 対応表を作り、実データで確かめて集計をコミットする

ここは調べ物とユーザーの確認を含む。**対応表はユーザーに見せて了承を得てからコミットする。**

**Files:**
- Modify: `src/banei/export/people.toml`
- Create（生成物）: `web/src/data/people.json`

**Interfaces:**
- Consumes: Task 4 の `banei export`
- Produces: コミット済みの `web/src/data/people.json`（Task 7 の Astro が import する。次回以降の検査 3 の基準にもなる）

- [ ] **Step 1: 最新のバックアップから DB を復元する**

```bash
gh release download latest --repo banei-keiba/banei-db-backup --dir data --clobber
gunzip -f data/banei.db.gz data/odds.db.gz
```

- [ ] **Step 2: 略称の一覧を出す**

```bash
sqlite3 -header data/banei.db "
SELECT 'jockey' AS role, jockey AS key, MIN(race_date) AS first, MAX(race_date) AS last, COUNT(*) AS n
  FROM results GROUP BY jockey
UNION ALL
SELECT 'trainer', trainer, MIN(race_date), MAX(race_date), COUNT(*) FROM results GROUP BY trainer
ORDER BY role, last DESC;"
```

Expected: 騎手 51 行・調教師 47 行（2026 シーズンからの調教師 藤野俊・藤本匠を含む）。

- [ ] **Step 3: 公式の一覧で正式名を確かめる**

ばんえい十勝の公式サイト（https://banei-keiba.or.jp/ から騎手・調教師の紹介ページを辿る）と、
地方競馬情報サイト（https://www.keiba.go.jp/ の騎手・調教師の名鑑）を WebFetch で読む。取得は人数分の
数ページに留める（連続取得しない）。

略称と正式名の対応は次の規則（実データで確認済み）で照合する:
- 姓が 1 字なら 姓 + 名の先頭 2 字（名が 1 字なら間に全角スペース。林豊 → 「林　豊」、谷あゆみ → 「谷あゆ」）
- 姓が 2 字以上なら 姓の先頭 2 字 + 名の先頭 1 字（鈴木恵介 → 「鈴木恵」、竹ケ原茉耶 → 「竹ケ茉」）

**照合が 1 人に定まり、出典のページで正式名を確認できた人だけ**を書く。同じ略称になる候補が複数いる・
引退して公式の一覧に無い・ページで確認できない人は書かない（略称のまま表示される）。騎手と調教師を
兼ねた人（2.4 の 8 人）は、同一人物だと出典で確かめられたら 1 行にまとめる。

`src/banei/export/people.toml` の雛形コメントの下に、1 人 1 ブロックで足す:

```toml
[[person]]
name = "（出典に書かれた正式名）"
jockey = "（DB の騎手の略称）"
trainer = "（DB の調教師の略称。調教師でなければこの行を書かない）"
source = "（確認したページの URL） (（確認した日 YYYY-MM-DD） 確認)"
```

- [ ] **Step 4: 対応表が読めることを確かめる**

Run: `uv run pytest tests/test_people.py -q -k repository_table`
Expected: PASS

- [ ] **Step 5: 別のディレクトリに書き出して、測定どおりかを確かめる**

`$SCRATCH` はこのセッションのスクラッチパッド（無ければ `mktemp -d` で作る）。

```bash
uv run banei export --out-dir "$SCRATCH/people-check" 2> "$SCRATCH/people-warnings.txt"
uv run python - "$SCRATCH/people-check/people.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
print("締め", d["through_season"])
for role in ("jockey", "trainer"):
    ppl = d["roles"][role]["people"]
    pooled = sorted((s, p["key"]) for p in ppl for s in p["pooled_seasons"])
    print(role, len(ppl), "人 / その他", len(pooled), pooled)
pages = d["pages"]
print("ページ", len(pages), "/ 正式名あり", sum(p["name_confirmed"] for p in pages),
      "/ 現役", sum(p["active"] for p in pages))
EOF
cat "$SCRATCH/people-warnings.txt"
```

Expected（設計 §4.3 の測定）:
- 締め 2025
- jockey 51 人 / その他 11: `(2008, 林義直) (2008, 菊池一) (2009, 渡来心) (2009, 貝羽智) (2010, 井上真) (2010, 林義直) (2010, 辻本貴) (2012, 井上真) (2012, 貝羽智) (2019, 林康文) (2019, 竹ケ茉)`
- trainer 45 人 / その他 8: `(2008, 前原陽) (2008, 福森浩) (2018, 山田勇) (2018, 森芳浩) (2019, 山田勇) (2019, 森芳浩) (2020, 山田勇) (2020, 森芳浩)`
- ページ 90（騎手 51 + 調教師 45 − 兼任 6）
- 警告は、対応表に書かなかった略称だけ

一致しなければ止めて原因を調べる（推測で数字を合わせない）。

- [ ] **Step 6: ユーザーに対応表を見せて了承を得る**

対応表（正式名・略称・出典）と、書かなかった人（略称のまま）の一覧、Step 5 の結果を見せる。
了承が得られるまで Step 7 に進まない。

- [ ] **Step 7: 本番の出力先に書き出してコミットする**

```bash
uv run banei export
git add web/src/data/people.json src/banei/export/people.toml
git restore web/src/data   # 他の集計（summary などの生成時刻）の差分はこのコミットに入れない
git status --short         # people.json と people.toml だけがステージされていること
git commit -F - <<'EOF'
騎手・調教師の正式名の対応表と、2025 シーズンまでの集計を足す

対応表には、公式の紹介ページで正式名を確かめられた人だけを書いた（出典と確認日つき）。
確かめられなかった人は略称のまま表示する。推測で埋めると誤った名前が公開されるため。
集計の「その他」は騎手 11・調教師 8 件で、設計時の測定と一致した。
people.json は次回以降の締めの検査（検査 3）の基準になるので、手で書き換えない。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 6: SVG のはみ出し検査と LineChart の拡張

**Files:**
- Create: `src/banei/svgcheck.py`
- Test: `tests/test_svgcheck.py`
- Modify: `web/src/components/LineChart.astro`

**Interfaces:**
- Produces:
  - `banei.svgcheck.text_width(s: str, font_px: float = 12.0) -> float`
  - `banei.svgcheck.problems_in(html: str) -> list[str]` — 「図 N: …」の形の違反
  - `banei.svgcheck.main(argv: list[str]) -> int` — 0: 問題なし / 1: 違反あり / 2: HTML が無い。`uv run python -m banei.svgcheck web/dist`
  - `LineChart` の新しい props: `xFormat?: (v: number) => string`（既定は `toLocaleString('ja-JP')`）、`refValue?: number`（参照線。ラベルは置かない）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_svgcheck.py` を新規作成:

```python
"""SVG のはみ出し検査（svgcheck.py）のテスト。合成の HTML だけを使う。"""

from banei import svgcheck


def svg(body, w=720, h=340):
    return f'<figure><svg viewBox="0 0 {w} {h}" role="img"><title>題</title>{body}</svg></figure>'


def test_text_inside_passes():
    html = svg('<text class="tick" x="42" y="100" text-anchor="end" '
               'dominant-baseline="middle">1,000</text>')
    assert svgcheck.problems_in(html) == []


def test_end_anchored_text_past_left_edge_is_reported():
    p = svgcheck.problems_in(svg('<text x="10" y="100" text-anchor="end">10,000</text>'))
    assert len(p) == 1 and "10,000" in p[0]


def test_wide_japanese_label_past_right_edge_is_reported():
    # 全角は 1 字幅で数える。半角と同じに数えると見逃す（700 + 6 字 × 12px > 720）
    assert svgcheck.problems_in(svg('<text x="700" y="100">見込みとの差</text>'))


def test_text_above_the_top_is_reported():
    assert svgcheck.problems_in(svg('<text x="100" y="5">勝</text>'))


def test_line_and_path_outside_are_reported():
    p = svgcheck.problems_in(svg('<line x1="0" x2="730" y1="10" y2="10" />'
                                 '<path d="M10,10 L20,-5" />'))
    assert len(p) == 2


def test_title_is_not_a_label():
    long = "とても長いタイトル" * 20
    assert svgcheck.problems_in(f'<svg viewBox="0 0 100 100"><title>{long}</title></svg>') == []


def test_each_svg_uses_its_own_viewbox():
    html = svg('<text x="600" y="100">a</text>') + svg('<text x="600" y="100">a</text>', w=500)
    p = svgcheck.problems_in(html)
    assert len(p) == 1 and p[0].startswith("図 2")


def test_svg_without_viewbox_is_ignored():
    assert svgcheck.problems_in('<svg><line x1="-5" x2="5" y1="0" y2="0" /></svg>') == []


def test_main_fails_without_html(tmp_path):
    # ビルドし忘れを「問題なし」にしない
    assert svgcheck.main(["svgcheck", str(tmp_path)]) == 2


def test_main_reports_file_and_fails(tmp_path, capsys):
    (tmp_path / "a").mkdir()
    (tmp_path / "a/index.html").write_text(
        svg('<text x="10" y="100" text-anchor="end">10,000</text>'), encoding="utf-8")
    assert svgcheck.main(["svgcheck", str(tmp_path)]) == 1
    assert "index.html" in capsys.readouterr().out
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `uv run pytest tests/test_svgcheck.py -q`
Expected: FAIL（`ImportError: cannot import name 'svgcheck'`）

- [ ] **Step 3: 実装を書く**

`src/banei/svgcheck.py` を新規作成:

```python
"""ビルドした HTML の SVG 図版で、文字・線・点が viewBox の外へ出ていないかを確かめる。

CLAUDE.md「図版を足すときの決まり」。y 軸の単位や参照線のラベルが viewBox の外に出る事故が
実際にあった。文字の幅はフォントを使わずに見積もる（半角 0.6 字・それ以外 1 字）。
path は絶対座標（M・L・Q・Z）だけを想定する（図版の部品はすべてそう書いている）。
文字どうしの重なりは見ない（目視で確かめる）。

    uv run python -m banei.svgcheck web/dist
"""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

FONT_PX = 12.0  # global.css の .tick / .axis-label / .point-label
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def text_width(s: str, font_px: float = FONT_PX) -> float:
    """文字列の幅の見積もり。半角（U+2000 未満）は 0.6 字、それ以外（漢字・かな・全角記号）は 1 字。"""
    return sum(font_px * (0.6 if ord(c) < 0x2000 else 1.0) for c in s)


class _Collector(HTMLParser):
    """viewBox のある svg ごとに、text の位置と中身、線・点・path の座標を集める。"""

    def __init__(self) -> None:
        super().__init__()
        self.svgs: list[dict] = []
        self._svg: dict | None = None
        self._text: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}  # 属性名は小文字になる（viewBox → viewbox）

        def num(key: str) -> float:
            return float(a.get(key) or 0)

        if tag == "svg":
            self._svg = None
            if "viewbox" in a:
                _, _, w, h = (float(v) for v in a["viewbox"].split())
                self._svg = {"w": w, "h": h, "texts": [], "points": []}
                self.svgs.append(self._svg)
            return
        if self._svg is None:
            return
        if tag == "text":
            self._text = {"x": num("x"), "y": num("y"), "anchor": a.get("text-anchor", "start"),
                          "middle": a.get("dominant-baseline") == "middle", "s": ""}
        elif tag == "line":
            self._svg["points"] += [(num("x1"), num("y1")), (num("x2"), num("y2"))]
        elif tag == "circle":
            r = num("r")
            self._svg["points"] += [(num("cx") - r, num("cy") - r), (num("cx") + r, num("cy") + r)]
        elif tag == "path":
            nums = [float(n) for n in _NUMBER.findall(a.get("d", ""))]
            self._svg["points"] += list(zip(nums[0::2], nums[1::2], strict=False))

    def handle_data(self, data: str) -> None:
        if self._text is not None:
            self._text["s"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "text" and self._text is not None and self._svg is not None:
            self._svg["texts"].append(self._text)
            self._text = None
        elif tag == "svg":
            self._svg = None


def problems_in(html: str) -> list[str]:
    """HTML 1 ページ分の違反。図の番号はページ内で viewBox のある svg の順（1 始まり）。"""
    c = _Collector()
    c.feed(html)
    out: list[str] = []
    for i, svg in enumerate(c.svgs, start=1):
        w, h = svg["w"], svg["h"]
        for t in svg["texts"]:
            s = t["s"].strip()
            width = text_width(s)
            left = t["x"] - {"middle": width / 2, "end": width}.get(t["anchor"], 0.0)
            if t["middle"]:
                top, bottom = t["y"] - FONT_PX / 2, t["y"] + FONT_PX / 2
            else:
                top, bottom = t["y"] - FONT_PX * 0.8, t["y"] + FONT_PX * 0.2
            if left < 0 or left + width > w or top < 0 or bottom > h:
                out.append(f"図 {i}: 文字「{s}」が viewBox（{w:g}×{h:g}）の外に出る"
                           f"（x {left:.0f}〜{left + width:.0f}, y {top:.0f}〜{bottom:.0f}）")
        for x, y in svg["points"]:
            if not (0 <= x <= w and 0 <= y <= h):
                out.append(f"図 {i}: 座標 ({x:g}, {y:g}) が viewBox（{w:g}×{h:g}）の外にある")
    return out


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path("web/dist")
    pages = sorted(root.rglob("*.html"))
    if not pages:
        print(f"{root} に HTML が無い（先に npm run build する）")
        return 2
    found = 0
    for path in pages:
        for p in problems_in(path.read_text(encoding="utf-8")):
            print(f"{path}: {p}")
            found += 1
    print(f"SVG の検査: {len(pages)} ページ・違反 {found} 件")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: テストが通ることを確かめる**

Run: `uv run pytest tests/test_svgcheck.py -q && uv run ruff check .`
Expected: 全件 PASS、ruff の指摘なし

- [ ] **Step 5: LineChart に xFormat と refValue を足す**

`web/src/components/LineChart.astro` の `interface Props` に足す:

```ts
  /** x 軸の目盛りの書式。既定は toLocaleString。シーズン（2025）は「2,025」になるので String を渡す */
  xFormat?: (v: number) => string;
  /** 参照線の値（0 など）。ラベルは置かない（端点のラベルと重なる）ので、意味は副題で説明する */
  refValue?: number;
```

props の分割代入を次にする:

```ts
const {
  data,
  xKey,
  yKey,
  title,
  subtitle,
  caption,
  xUnit = '',
  yUnit = '',
  tooltip,
  xFormat = (v: number) => v.toLocaleString('ja-JP'),
  refValue,
} = Astro.props;
```

y の目盛りが参照線を含むようにする:

```ts
const yTicks = niceTicks(Math.min(...ys, refValue ?? Infinity), Math.max(...ys, refValue ?? -Infinity));
```

x 軸の目盛りの `{d[xKey].toLocaleString('ja-JP')}` を `{xFormat(d[xKey])}` に置き換える。

`<path d={path} …>`（折れ線）の直前に参照線を足す（線の下に描く）:

```astro
    {
      refValue !== undefined && (
        <line
          x1={M.left}
          x2={M.left + pw}
          y1={sy(refValue)}
          y2={sy(refValue)}
          stroke="var(--accent)"
          stroke-width="2"
        />
      )
    }
```

- [ ] **Step 6: 既存のページをビルドして検査する（基準を取る）**

```bash
(cd web && npm run build)
uv run python -m banei.svgcheck web/dist
```

Expected: `違反 0 件`。既存のページで違反が出たら、この計画では直さずにユーザーに報告する（今の公開ページの問題なので、別に判断する）。LineChart の既定の挙動は変えていないので、既存ページの HTML は変わらないはず。

- [ ] **Step 7: コミット**

```bash
git add src/banei/svgcheck.py tests/test_svgcheck.py web/src/components/LineChart.astro
git commit -F - <<'EOF'
SVG のはみ出し検査を足し、折れ線に参照線と x 軸の書式を足す

y 軸の単位や参照線のラベルが viewBox の外に出る事故が実際にあった。目で数えるのをやめ、
ビルドした全ページを機械的に検査できるようにする。
騎手・調教師ページの「見込みとの差」は負の値があり 0 の参照線が要る。x 軸がシーズンなので、
toLocaleString のままだと「2,025」と表示される。参照線のラベルは置かない。最後の点が 0 に
近いと端点のラベルと重なるため、意味は副題で説明する。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 7: 騎手・調教師のページ

**Files:**
- Create: `web/src/lib/people.ts`
- Create: `web/src/pages/people/index.astro`
- Create: `web/src/pages/people/[slug].astro`
- Modify: `web/src/layouts/Base.astro:36-40`（ナビ）

**Interfaces:**
- Consumes: Task 5 の `web/src/data/people.json`、Task 6 の `LineChart` の `xFormat` / `refValue`、`web/src/lib/explore.ts` の `pct` / `count`、`DataTable.astro`
- Produces: `/people/`（一覧）と `/people/<slug>/`（1 人）

- [ ] **Step 1: データの型と書式（lib/people.ts）**

`web/src/lib/people.ts` を新規作成:

```ts
/** 騎手・調教師ページのデータ（src/banei/export/people.py が書き出す people.json）と URL の決まり。 */
import data from '../data/people.json';
import { count, pct } from './explore';

export interface Metrics {
  n: number;
  win_rate: number;
  top2_rate: number;
  place_rate: number;
  win_roi: number;
  place_roi: number;
  wins: number;
  avg_popularity: number;
  expected_wins: number;
  wins_over_expected: number;
}
export interface SeasonRow extends Metrics {
  season: number;
}
export interface Career extends Metrics {
  first_season: number;
  last_season: number;
}
export interface Person {
  key: string;
  seasons: SeasonRow[];
  pooled_seasons: number[];
  career: Career | null;
}
export interface SeasonTotal {
  season: number;
  total: Metrics;
  other: (Metrics & { people_count: number }) | null;
}
export type Role = 'jockey' | 'trainer';
export interface Page {
  slug: string;
  name: string;
  name_confirmed: boolean;
  jockey: string | null;
  trainer: string | null;
  active: boolean;
}
export interface PeopleData {
  through_season: number;
  roles: Record<Role, { seasons: SeasonTotal[]; people: Person[] }>;
  pages: Page[];
}

export const PEOPLE = data as unknown as PeopleData;

export const ROLES: { key: Role; name: string; runs: string; verb: string }[] = [
  { key: 'jockey', name: '騎手', runs: '騎乗数', verb: '騎乗' },
  { key: 'trainer', name: '調教師', runs: '出走数', verb: '出走' },
];
export const roleOf = (role: Role) => ROLES.find((r) => r.key === role)!;

/** そのページに載せる役割（騎手を先に）。 */
export const rolesOf = (page: Page): Role[] =>
  ROLES.map((r) => r.key).filter((r) => page[r] !== null);
export const rolesLabel = (page: Page) => rolesOf(page).map((r) => roleOf(r).name).join('・');

export const personOf = (role: Role, key: string): Person =>
  PEOPLE.roles[role].people.find((p) => p.key === key)!;
export const pageOf = (role: Role, key: string): Page =>
  PEOPLE.pages.find((p) => p[role] === key)!;
export const pageUrl = (page: Page) => `/people/${page.slug}/`;

/** シーズンの期間（2025 → 2025/4/1〜2026/3/31）。 */
export const seasonSpan = (season: number) => `${season}/4/1〜${season + 1}/3/31`;

/** 見込みとの差。正の値に + を付け、負の値はマイナス記号（−）にする。 */
export const signed = (v: number) =>
  v > 0 ? `+${v.toFixed(1)}` : v < 0 ? `−${Math.abs(v).toFixed(1)}` : '0.0';

/** シーズン別の表に並べる指標（出走数の後）。率の書式は探索 UI と同じ。 */
export const COLUMNS: { key: keyof Metrics; name: string; fmt: (v: number) => string }[] = [
  { key: 'win_rate', name: '勝率', fmt: pct },
  { key: 'top2_rate', name: '連対率', fmt: pct },
  { key: 'place_rate', name: '複勝率', fmt: pct },
  { key: 'win_roi', name: '単勝回収率', fmt: pct },
  { key: 'place_roi', name: '複勝回収率', fmt: pct },
  { key: 'avg_popularity', name: '平均人気', fmt: (v) => v.toFixed(2) },
  { key: 'wins', name: '勝ち数', fmt: count },
  { key: 'expected_wins', name: '見込み勝ち数', fmt: (v) => v.toFixed(1) },
  { key: 'wins_over_expected', name: '見込みとの差', fmt: signed },
];
```

- [ ] **Step 2: 1 人のページ**

`web/src/pages/people/[slug].astro` を新規作成:

```astro
---
import DataTable from '../../components/DataTable.astro';
import LineChart from '../../components/LineChart.astro';
import Base from '../../layouts/Base.astro';
import { count, pct } from '../../lib/explore';
import {
  COLUMNS,
  PEOPLE,
  personOf,
  roleOf,
  rolesLabel,
  rolesOf,
  seasonSpan,
  signed,
  type Page,
  type SeasonRow,
} from '../../lib/people';

export function getStaticPaths() {
  return PEOPLE.pages.map((page) => ({ params: { slug: page.slug }, props: { page } }));
}

interface Props {
  page: Page;
}

const { page } = Astro.props;
const roles = rolesOf(page);
const label = rolesLabel(page);
const through = PEOPLE.through_season;

const sections = roles.map((role) => {
  const person = personOf(role, page[role]!);
  // 新しいシーズンを上に。「その他」にまとめたシーズンも行として残す（消すと割り出せるのではなく、
  // 載せていないことを見せるため）
  const rows: { season: number; row: SeasonRow | null }[] = [
    ...person.seasons.map((row) => ({ season: row.season, row })),
    ...person.pooled_seasons.map((season) => ({ season, row: null })),
  ].sort((a, b) => b.season - a.season);
  return { role, info: roleOf(role), person, rows, latest: person.seasons.at(-1) ?? null };
});
---

<Base
  title={`${page.name} ${label}の成績`}
  description={`ばんえい競馬の${label}・${page.name}のシーズン別の勝率・回収率と、人気から見込まれる勝ち数との差。`}
>
  <h1>{page.name} {label}の成績</h1>
  <p class="meta">
    {through} シーズン（{seasonSpan(through)}）まで・毎年 5/1 に前のシーズンを締めて更新
  </p>
  {
    !page.name_confirmed && (
      <p class="meta">名前はレース結果の略称表記です（正式名を確かめられていません）。</p>
    )
  }
  {
    sections.map(({ info, person, rows, latest }) => (
      <section>
        {roles.length > 1 && <h2>{info.name}</h2>}
        {latest && (
          <p class="lede">
            {latest.season} シーズンは {count(latest.n)} {info.verb}で {count(latest.wins)} 勝
            （勝率 {pct(latest.win_rate)}）。乗った馬の人気から見込まれる勝ち数との差は
            {signed(latest.wins_over_expected)} 勝。
          </p>
        )}
        <div class="matrix">
          <table>
            <thead>
              <tr>
                <th scope="col">シーズン</th>
                <th scope="col">{info.runs}</th>
                {COLUMNS.map((c) => <th scope="col">{c.name}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map(({ season, row }) =>
                row ? (
                  <tr>
                    <th scope="row">{season}</th>
                    <td>{count(row.n)}</td>
                    {COLUMNS.map((c) => <td>{c.fmt(row[c.key])}</td>)}
                  </tr>
                ) : (
                  <tr>
                    <th scope="row">{season}</th>
                    <td class="empty" colspan={COLUMNS.length + 1}>
                      —（その他にまとめたため非表示）
                    </td>
                  </tr>
                ),
              )}
              {person.career && (
                <tr class="total">
                  <th scope="row">通算</th>
                  <td>{count(person.career.n)}</td>
                  {COLUMNS.map((c) => <td>{c.fmt(person.career![c.key])}</td>)}
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {person.pooled_seasons.length > 0 && (
          <p class="meta">通算は「その他」にまとめたシーズンを除いた合計です。</p>
        )}
        {person.seasons.length >= 2 && (
          <>
            <LineChart
              data={person.seasons.map((s) => ({ season: s.season, diff: s.wins_over_expected }))}
              xKey="season"
              yKey="diff"
              title="人気から見込まれる勝ち数との差"
              subtitle="シーズンごと。太い横線が 0 で、上にあるほど人気から見込まれるより多く勝った"
              xUnit="シーズン"
              yUnit="勝"
              xFormat={(v) => String(v)}
              refValue={0}
              tooltip={(d) => `${d.season} シーズン — ${signed(d.diff)} 勝`}
            />
            <DataTable
              data={person.seasons.map((s) => ({ season: s.season, diff: s.wins_over_expected }))}
              columns={[
                { key: 'season', label: 'シーズン', format: (v) => String(v) },
                { key: 'diff', label: '見込みとの差（勝）', format: signed },
              ]}
            />
          </>
        )}
      </section>
    ))
  }
  <div class="note">
    <p>
      <strong>見込み勝ち数</strong>は、出走ごとに「そのシーズン全体で、その人気の馬が勝った割合」を
      足し上げたものです。見込みとの差が正なら、人気以上に勝っています。回収率と同じく、
      1 シーズンの値は偶然で大きく振れます。
    </p>
    <p>
      あるシーズンの出走が 30 件に満たない人は、そのシーズンだけ個人の欄に載せず「その他」に
      まとめています（<a href="/people/">騎手・調教師の一覧</a>）。勝率・回収率の定義は
      <a href="/explore/">探索</a>と同じです。
    </p>
  </div>
</Base>
```

- [ ] **Step 3: 一覧のページ**

`web/src/pages/people/index.astro` を新規作成:

```astro
---
import Base from '../../layouts/Base.astro';
import { count, pct } from '../../lib/explore';
import { PEOPLE, ROLES, pageOf, pageUrl, rolesLabel, seasonSpan, signed } from '../../lib/people';

const through = PEOPLE.through_season;
const boards = ROLES.map((role) => {
  const rows = PEOPLE.roles[role.key].people
    .flatMap((person) => {
      const row = person.seasons.find((s) => s.season === through);
      return row ? [{ row, page: pageOf(role.key, person.key) }] : [];
    })
    .sort((a, b) => b.row.wins - a.row.wins || b.row.win_rate - a.row.win_rate);
  const other = PEOPLE.roles[role.key].seasons.find((s) => s.season === through)?.other ?? null;
  return { role, rows, other };
});
const active = PEOPLE.pages.filter((p) => p.active);
const past = PEOPLE.pages.filter((p) => !p.active);
---

<Base
  title="騎手・調教師の成績"
  description="ばんえい競馬の騎手・調教師ごとの、シーズン別の勝率・回収率と、人気から見込まれる勝ち数との差。"
>
  <h1>騎手・調教師の成績</h1>
  <p class="meta">
    {through} シーズン（{seasonSpan(through)}）まで・毎年 5/1 に前のシーズンを締めて更新
  </p>
  {
    boards.map(({ role, rows, other }) => (
      <section>
        <h2>
          {through} シーズンの{role.name}
        </h2>
        <div class="matrix">
          <table>
            <thead>
              <tr>
                <th scope="col">順位</th>
                <th scope="col">名前</th>
                <th scope="col">{role.runs}</th>
                <th scope="col">勝ち数</th>
                <th scope="col">勝率</th>
                <th scope="col">単勝回収率</th>
                <th scope="col">複勝回収率</th>
                <th scope="col">見込みとの差</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ row, page }, i) => (
                <tr>
                  <td>{i + 1}</td>
                  <th scope="row">
                    <a href={pageUrl(page)}>{page.name}</a>
                  </th>
                  <td>{count(row.n)}</td>
                  <td>{count(row.wins)}</td>
                  <td>{pct(row.win_rate)}</td>
                  <td>{pct(row.win_roi)}</td>
                  <td>{pct(row.place_roi)}</td>
                  <td>{signed(row.wins_over_expected)}</td>
                </tr>
              ))}
              {other && (
                <tr class="total">
                  <td />
                  <th scope="row">その他（{other.people_count} 人）</th>
                  <td>{count(other.n)}</td>
                  <td>{count(other.wins)}</td>
                  <td>{pct(other.win_rate)}</td>
                  <td>{pct(other.win_roi)}</td>
                  <td>{pct(other.place_roi)}</td>
                  <td>{signed(other.wins_over_expected)}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    ))
  }
  <h2>全員</h2>
  <h3>{through} シーズンに出走あり</h3>
  <ul>
    {
      active.map((p) => (
        <li>
          <a href={pageUrl(p)}>{p.name}</a>（{rolesLabel(p)}）
        </li>
      ))
    }
  </ul>
  <h3>それより前</h3>
  <ul>
    {
      past.map((p) => (
        <li>
          <a href={pageUrl(p)}>{p.name}</a>（{rolesLabel(p)}）
        </li>
      ))
    }
  </ul>
  <div class="note">
    <p>
      <strong>見込みとの差</strong>は、実際の勝ち数から「乗った（管理する）馬の人気から見込まれる
      勝ち数」を引いたものです。見込みは、出走ごとにそのシーズン全体のその人気の勝率を足し上げます。
    </p>
    <p>
      あるシーズンの出走が 30 件に満たない人は、そのシーズンだけ個人の欄に載せず「その他」に
      まとめています。消すと全体からの引き算で値が分かってしまうためです。「その他」も 30 件に
      満たないときは、そのシーズンの出走が少ない人から順に加えます。
    </p>
    <p>名前の一部は、レース結果の略称表記（3 文字）のままです。</p>
  </div>
</Base>
```

- [ ] **Step 4: ナビに足す**

`web/src/layouts/Base.astro` のナビを次にする:

```astro
        <nav>
          <a href="/">ホーム</a>
          <a href="/explore/">探索</a>
          <a href="/people/">騎手・調教師</a>
          <a href="/data/">データについて</a>
        </nav>
```

- [ ] **Step 5: ビルドして確かめる**

```bash
(cd web && npm run build)
find web/dist/people -name index.html | wc -l
uv run python -c "import json; print(len(json.load(open('web/src/data/people.json', encoding='utf-8'))['pages']) + 1)"
grep -rl "<script" web/dist/people | wc -l
uv run python -m banei.svgcheck web/dist
```

Expected: 1 行目と 2 行目が同じ数（ページ数 + 一覧 1）、`<script>` を含むファイル 0、SVG の違反 0 件。

ページの中身を確かめる（Review Focus）:

```bash
uv run python - <<'EOF'
import json
from pathlib import Path
d = json.load(open("web/src/data/people.json", encoding="utf-8"))
dist = Path("web/dist/people")
def html(page): return (dist / page["slug"] / "index.html").read_text(encoding="utf-8")
def seasons(page):
    return [person(r, page[r]) for r in ("jockey", "trainer") if page[r]]
def person(role, key):
    return next(p for p in d["roles"][role]["people"] if p["key"] == key)
# 個人の欄が 1 シーズンだけの役割しか無い人には図を出さない
one = next((p for p in d["pages"] if all(len(x["seasons"]) == 1 for x in seasons(p))), None)
if one is None:
    print("個人の欄が 1 シーズンだけの人はいない（図を出さない場合は確かめられない）")
else:
    assert "<svg" not in html(one), one
pooled = next(p for p in d["pages"] if any(x["pooled_seasons"] for x in seasons(p)))
assert "その他にまとめたため非表示" in html(pooled), pooled
both = next(p for p in d["pages"] if p["jockey"] and p["trainer"])
assert html(both).count("<h2>") >= 2, both  # 役割ごとの見出し
print("ok:", one and one["slug"], pooled["slug"], both["slug"])
EOF
```

Expected: `ok: …`。1 シーズンだけの人がいなかった場合は、その旨を完了報告に書く。

- [ ] **Step 6: 日本語の URL がプレビューで開けることを確かめる**

```bash
(cd web && npx astro preview --port 4329 > /dev/null 2>&1 &)
for i in $(seq 1 30); do curl -s -o /dev/null http://localhost:4329/ && break; sleep 1; done
SLUG=$(uv run python -c "import json; print(json.load(open('web/src/data/people.json', encoding='utf-8'))['pages'][0]['slug'])")
ENC=$(uv run python -c "import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))" "$SLUG")
curl -s -o /dev/null -w '%{http_code}\n' "http://localhost:4329/people/$ENC/"
curl -s -o /dev/null -w '%{http_code}\n' "http://localhost:4329/people/"
pkill -f "astro preview --port 4329"
```

Expected: `200` が 2 行。Cloudflare Pages でも同じに開けるかは公開後に確かめる（この計画では公開しない。完了報告に残課題として書く）。

- [ ] **Step 7: コミット**

```bash
git add web/src/lib/people.ts web/src/pages/people web/src/layouts/Base.astro
git commit -F - <<'EOF'
騎手・調教師の一覧と 1 人 1 ページを足す

騎手・調教師の名前で検索して来る読者と、予想の材料を探す読者のためのページ。条件で分けた表は
載せず、シーズンごとの成績と「人気から見込まれる勝ち数との差」だけにした（条件で分けると
大半の人で 30 件ルールを満たせない）。「その他」にまとめたシーズンも行として残す。
載せていないことを見せ、通算がそのシーズンを除いた合計だと分かるようにするため。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 8: ドキュメントの更新

**Files:**
- Modify: `docs/architecture.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: architecture.md §3.4 のページ数を書き換える**

次の行:

```
- 残るのは 馬 5,501 + 騎手 51 + 調教師 47 + 分析軸・記事のページ ≈ **6,000ページ**
```

を次にする:

```
- 残るのは 騎手・調教師 約 90 + 分析軸（探索 UI 73）・記事のページ。馬ページ（5,501）を足しても ≈ **6,000ページ**
  （馬ページは今の公開ルールではほぼ作れない。docs/superpowers/specs/2026-10-14-people-pages-design.md §2.1）
```

- [ ] **Step 2: architecture.md §3.4 の人の切り口を書き換える**

次の 2 行:

```
- 騎手・調教師を含めると、この規則では騎手の表の 53〜100% が「その他」になる（実測）。
  人の切り口は Phase 4 で決める
```

を次にする:

```
- 騎手・調教師を含めると、この規則では騎手の表の 53〜100% が「その他」になる（実測）。
  そのため騎手・調教師は、条件で分けない「1 人 × 1 シーズン」の成績と派生指標だけのページにした
  （設計: docs/superpowers/specs/2026-10-14-people-pages-design.md）。30 件未満の人・シーズンは
  シーズンごとに「その他」へまとめる
```

- [ ] **Step 3: architecture.md §4 のリポジトリ構成を書き換える**

```
│   └── export/                 # 【公開データの唯一の出口】集計 → JSON（探索 UI は explore/）
```

を次にする:

```
│   └── export/                 # 【公開データの唯一の出口】集計 → JSON（探索 UI は explore/、騎手・調教師は people.json）
```

```
│   ├── src/pages/              # 全て SSG（集計ページ・馬/騎手ページ）
```

を次にする:

```
│   ├── src/pages/              # 全て SSG（集計ページ・探索 UI・騎手/調教師ページ）
```

- [ ] **Step 4: architecture.md の Phase 4 を書き換える**

`### Phase 4 — 馬・騎手ページ / SEO（1週間）` から `### Phase 5 — 当日予想` の直前までを次にする:

```markdown
### Phase 4 — 騎手・調教師ページ / 馬ページ / SEO

**騎手・調教師ページ**（設計: docs/superpowers/specs/2026-10-14-people-pages-design.md）

- [x] シーズンごとの成績と派生指標（人気から見込まれる勝ち数との差）を export で集計（`people.json`）
- [x] 正式名の対応表（`src/banei/export/people.toml`）。出典で確かめた人だけ。URL は略称から作る
- [x] 一覧と 1 人 1 ページ。SVG のはみ出し検査（`python -m banei.svgcheck web/dist`）
- [ ] ブラウザでの目視（ダークモード・幅 375px）と公開。公開後に日本語の URL が Cloudflare Pages で開けることを確かめる

**馬ページ** — 今の公開ルールではほぼ作れない（2025 シーズンに 30 回以上走った馬は 0 頭）。作るなら、
版の差の単位を「馬 1 頭の 1 シーズン成績」まで認めるか（公開方針の変更）を先に決める

- [ ] 方針を決める

**SEO まわり** — 独自ドメインと noindex を外す時期とあわせて設計する

- [ ] sitemap、構造化データ、内部リンク

検索の裾を取りにいくのはここ（「ばんえい 〇〇（騎手名）」等）。生データ転載サイトとの差別化は、むしろ**集計・分析の質**で行う — 着順表を並べても同じことをしている先行サイトに勝てない。

```

- [ ] **Step 5: architecture.md §9 の表を書き換える**

```
| 馬ページに「直近5走」のような明細を載せるか | Phase 4 の前。厳密に方針を守るなら載せず、集計のみにする |
```

を次にする:

```
| 馬ページを作るか（版の差の単位を馬 1 頭の 1 シーズン成績まで認めるか） | 騎手・調教師ページの公開後。今のルールではほぼ作れない（people-pages-design.md §2.1） |
```

- [ ] **Step 6: CLAUDE.md の構成を書き換える**

```
  export/     【公開データの唯一の出口】集計 → web/src/data/*.json（探索 UI は explore/*.json）
```

を次にする:

```
  export/     【公開データの唯一の出口】集計 → web/src/data/*.json（探索 UI は explore/*.json、
              騎手・調教師は people.json。正式名は people.toml の対応表）
```

`net.py` の行の下に足す:

```
  svgcheck.py ビルドした SVG のはみ出し検査（uv run python -m banei.svgcheck web/dist）
```

- [ ] **Step 7: CLAUDE.md の「探索 UI は年 1 回だけ変わる」に人のページを足す**

見出し `## 探索 UI は年 1 回だけ変わる` を `## 探索 UI と騎手・調教師ページは年 1 回だけ変わる` にし、
その節の最初の段落の後に次の段落を足す:

```markdown
騎手・調教師ページ（`web/src/data/people.json`）も同じく締めたシーズンまで。1 人 × 1 シーズンの
出走が 30 件未満なら、そのシーズンだけ「その他」にまとめる（まとめ方はシーズンごとに独立）。名前は
`src/banei/export/people.toml` の対応表で付け、**出典で確かめた人だけを書く**。表に無い略称は略称の
ままページになり、export が「対応表に無い略称」と警告する（止まらない）。5/1 に新人の警告が出たら、
公式の紹介ページで確かめて表に足す。表の修正は表示だけが変わり、締めの検査には引っかからない。
`people.json` も手で消さない（消すと、締めたシーズンの変化を比べる基準が無くなる）。
```

同じ節の手順の 2 の末尾（「判断の理由をコミットに書く」の後）に足す:

```markdown
   騎手・調教師ページ（`people.json`）で止まったときは、変わった人・シーズンの出走数の差がすべて
   0 か 30 以上なら公開してよい。その場合だけ `people.json` を削除して `banei export` をやり直す
```

- [ ] **Step 8: CLAUDE.md の進捗を書き換える**

`uv run pytest -q` の件数を数えてから、次の行:

```
- **次は Phase 4（騎手・馬ページ）**。人の切り口は版の差の規則で大半が「その他」になるので、
  設計から決める。組み合わせオッズのバックフィルはフェーズ非依存で並行して進める
```

を次にする（`<実行日>` は JST の実行した日付、`<件数>` は数えた件数に置き換える）:

```
- **Phase 4 のうち騎手・調教師ページ 実装済み・未公開**（<実行日>）— 1 人 × 1 シーズンの成績と
  「人気から見込まれる勝ち数との差」だけを載せ、30 件未満はシーズンごとに「その他」へまとめる
  （設計 docs/superpowers/specs/2026-10-14-people-pages-design.md）。実データの export で「その他」が
  設計時の測定（騎手 11・調教師 8）と一致し、ビルドで約 90 ページ・JS ゼロ・SVG のはみ出し 0 を確認済み。
  テストは全 <件数> 件。**ブラウザでの目視（ダークモード・幅 375px）と公開はまだ**。公開後に日本語の
  URL が Cloudflare Pages で開けることを確かめる
- **馬ページは今の公開ルールではほぼ作れない**（2025 シーズンに 30 回以上走った馬は 0 頭）。作るなら
  公開方針から決める。SEO まわりは独自ドメインと合わせて。組み合わせオッズのバックフィルは並行して進める
```

- [ ] **Step 9: コミット**

```bash
uv run ruff check . && uv run pytest -q
git add docs/architecture.md CLAUDE.md
git commit -F - <<'EOF'
騎手・調教師ページの仕組みと、馬ページを見送った理由を記録する

次に作業する人が、人のページも年 1 回しか変わらないこと、対応表には出典で確かめた名前しか
書かないこと、5/1 に新人の警告が出たときの対応を知らずに困らないようにするため。
馬ページは「馬 5,501 ページ」の前提が実測で崩れた（30 回以上走る馬がいない）ので、ページ数の
見積もりと未決事項を書き換えた。

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```
