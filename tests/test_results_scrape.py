"""レース結果収集の「今日」判定のテスト。

日次ワークフローは JST の未明に動くが、GitHub ランナーのローカル時刻は UTC。
ランナーのローカル日付で「今日」を判定していたため、JST では前日になった開催日が
UTC ではまだ当日扱いになり「未来日」として飛ばされ、取り込みが毎回 1 日遅れていた
（2026-10-10 開催分は 10/11 の実行で飛ばされ、10/12 の実行で取れた）。
手元（JST）では再現しないので、時刻を差し替えて確かめる。
"""

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from banei.ingest import results

FIXTURES = Path(__file__).parent / "fixtures"
RACE_DATES = ["2026-10-10", "2026-10-11"]
# 10/10 開催分を飛ばした実際の日次実行の時刻（JST では 10/11 05:27）
RUNNER_NOW = dt.datetime(2026, 10, 10, 20, 27, tzinfo=dt.UTC)


class FakeFetcher:
    """開催スケジュール・レース一覧・成績ページを合成 HTML で返す Fetcher の代役。"""

    def get(self, url, params=None):
        if url.endswith("MonthlyConveneInfoTop"):
            return "".join(
                f'<a href="/KeibaWeb/TodayRaceInfo/RaceList?k_raceDate={d.replace("-", "/")}'
                f'&k_babaCode={results.BABA_CODE}">{d}</a>'
                for d in RACE_DATES
            )
        if url.endswith("RaceList"):
            return (
                '<a href="/KeibaWeb/TodayRaceInfo/RaceMarkTable?'
                f'k_raceDate={params["k_raceDate"]}&k_raceNo=1&k_babaCode={results.BABA_CODE}">1R</a>'
            )
        if url.endswith("RaceMarkTable"):
            return (FIXTURES / "result_page.html").read_text(encoding="utf-8")
        raise AssertionError(f"想定外の URL: {url}")


@pytest.fixture
def scraped_days(tmp_path, monkeypatch):
    monkeypatch.setattr(results, "Fetcher", lambda *a, **k: FakeFetcher())
    monkeypatch.setattr(results, "_now", lambda: RUNNER_NOW)
    db = tmp_path / "banei.db"
    results.scrape("2026-10", "2026-10", db, interval=0)
    con = sqlite3.connect(db)
    days = {row[0] for row in con.execute("SELECT race_date FROM scraped_days")}
    con.close()
    return days


def test_race_day_is_scraped_next_morning_on_utc_runner(scraped_days):
    assert "2026-10-10" in scraped_days


def test_today_in_jst_is_still_skipped(scraped_days):
    """当日分は未確定のレースが残りうる。scraped_days に入った日は取り直さないので取らない。"""
    assert "2026-10-11" not in scraped_days
