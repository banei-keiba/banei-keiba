"""取得失敗時のふるまいのテスト。

2026-08-06 のバックフィルで、オッズパークが GitHub ランナーからのアクセスに
500 を返し続ける状態になった。当時の実装は残り 1,600 件を叩き続けたうえ、
実行が中断されて取得済み約 1,400 レース分がまるごと失われた。その再発防止。
"""

import sqlite3

import pytest
import requests

from banei.db.schema import RACES_SCHEMA
from banei.ingest import combo_odds, odds

ODDS_HTML = (
    '<table><tr><th>枠番</th><th>馬番</th><th>馬名</th><th>単勝</th><th>複勝</th></tr>'
    '<tr><td>1</td><td>1</td><td>馬</td><td>3.4</td><td>1.1 - 1.9</td></tr></table>'
)


def build_races_db(path, n_races=60):
    con = sqlite3.connect(path)
    con.executescript(RACES_SCHEMA)
    for i in range(n_races):
        con.execute("INSERT INTO races VALUES (?,?,?,?,?,?,?)",
                    ("2026-01-01", i, "テスト", 200, "曇", 3.0, "条件"))
        con.execute(
            "INSERT INTO results (race_date,race_no,horse_no,status,horse_name)"
            " VALUES ('2026-01-01',?,1,'1','馬')", (i,))
    con.commit()
    con.close()


@pytest.fixture
def dbs(tmp_path):
    races = tmp_path / "banei.db"
    build_races_db(races)
    return races, tmp_path / "odds.db"


class FlakyFetcher:
    """指定回数だけ成功し、その後はずっと失敗する Fetcher の代役。"""

    def __init__(self, ok_times: int):
        self.ok_times = ok_times
        self.calls = 0

    def get(self, url, params=None):
        self.calls += 1
        if self.calls <= self.ok_times:
            return ODDS_HTML
        raise requests.HTTPError('500 Server Error')


class TestOddsAbortsOnRepeatedFailure:
    def test_stops_after_consecutive_failures(self, dbs, monkeypatch):
        races, odds_db = dbs
        fetcher = FlakyFetcher(ok_times=5)
        monkeypatch.setattr(odds, 'Fetcher', lambda *a, **k: fetcher)

        odds.scrape(races, odds_db, interval=0, max_consecutive_failures=3)

        # 5 件成功 + 3 件失敗で打ち切り。60 件を叩き切らない。
        assert fetcher.calls == 8

    def test_successful_work_is_kept(self, dbs, monkeypatch):
        races, odds_db = dbs
        monkeypatch.setattr(odds, 'Fetcher', lambda *a, **k: FlakyFetcher(ok_times=5))
        odds.scrape(races, odds_db, interval=0, max_consecutive_failures=3)

        con = sqlite3.connect(odds_db)
        assert con.execute('SELECT COUNT(*) FROM odds_meta').fetchone()[0] == 5
        con.close()

    def test_failed_races_are_not_marked_done(self, dbs, monkeypatch):
        """失敗したレースは odds_meta を書かない = 次回の実行で再挑戦できる。"""
        races, odds_db = dbs
        monkeypatch.setattr(odds, 'Fetcher', lambda *a, **k: FlakyFetcher(ok_times=5))
        odds.scrape(races, odds_db, interval=0, max_consecutive_failures=3)

        # 2 回目は全て成功する Fetcher にすると、残りを取りにいく
        monkeypatch.setattr(odds, 'Fetcher', lambda *a, **k: FlakyFetcher(ok_times=1000))
        odds.scrape(races, odds_db, interval=0, max_consecutive_failures=3)

        con = sqlite3.connect(odds_db)
        assert con.execute('SELECT COUNT(*) FROM odds_meta').fetchone()[0] == 60
        con.close()

    def test_intermittent_failure_does_not_abort(self, dbs, monkeypatch):
        """単発の失敗では止まらない（連続でなければカウンタが戻る）。"""
        races, odds_db = dbs

        class Intermittent(FlakyFetcher):
            """4 件に 1 件だけ失敗する。連続はしない。"""

            def get(self, url, params=None):
                self.calls += 1
                if self.calls % 4 == 0:
                    raise requests.HTTPError('500 Server Error')
                return ODDS_HTML

        fetcher = Intermittent(ok_times=0)
        monkeypatch.setattr(odds, 'Fetcher', lambda *a, **k: fetcher)
        odds.scrape(races, odds_db, interval=0, max_consecutive_failures=3)

        assert fetcher.calls == 60  # 最後まで回りきる

    def test_limit_bounds_the_run(self, dbs, monkeypatch):
        races, odds_db = dbs
        fetcher = FlakyFetcher(ok_times=1000)
        monkeypatch.setattr(odds, 'Fetcher', lambda *a, **k: fetcher)
        odds.scrape(races, odds_db, interval=0, limit=10)
        assert fetcher.calls == 10


class TestComboOddsAbortsOnRepeatedFailure:
    def test_single_failure_does_not_raise(self, dbs, monkeypatch):
        """以前は例外がそのまま上がり、実行全体が落ちて成果を失っていた。"""
        races, odds_db = dbs
        monkeypatch.setattr(combo_odds, 'Fetcher', lambda *a, **k: FlakyFetcher(ok_times=0))
        combo_odds.scrape('umaren', None, races, odds_db, interval=0,
                          max_consecutive_failures=3)

    def test_stops_after_consecutive_failures(self, dbs, monkeypatch):
        races, odds_db = dbs
        fetcher = FlakyFetcher(ok_times=2)
        monkeypatch.setattr(combo_odds, 'Fetcher', lambda *a, **k: fetcher)
        combo_odds.scrape('umaren', None, races, odds_db, interval=0,
                          max_consecutive_failures=3)
        assert fetcher.calls == 5
