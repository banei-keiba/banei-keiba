"""レート制限付き HTTP クライアント。3 つのスクレイパーで共有する。"""

import sys
import time

import requests

from banei.config import REQUEST_INTERVAL, USER_AGENT


class Fetcher:
    """1 リクエスト / interval 秒を守り、失敗時は 3 回まで再試行する。"""

    def __init__(self, interval: float = REQUEST_INTERVAL, user_agent: str = USER_AGENT):
        self.interval = interval
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self._last = 0.0

    def get(self, url: str, params: dict | None = None) -> str:
        wait = self._last + self.interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            try:
                self._last = time.monotonic()
                resp = self.session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                return resp.text
            except requests.RequestException as e:
                if attempt == 2:
                    raise
                print(f"  リトライ {attempt + 1}/2: {e}", file=sys.stderr)
                time.sleep(5 * (attempt + 1))
        raise AssertionError("unreachable")
