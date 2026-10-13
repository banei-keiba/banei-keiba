"""パス・定数の一元管理。

データディレクトリは `BANEI_DATA_DIR` で差し替えられる（デフォルトはカレントの `data/`）。
`data/` は .gitignore 済み — 生データをリポジトリに入れない方針のため（docs/architecture.md §3.4）。
"""

import datetime as dt
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("BANEI_DATA_DIR", "data"))
RACES_DB = DATA_DIR / "banei.db"
ODDS_DB = DATA_DIR / "odds.db"

# 公開プロジェクトなので連絡先（リポジトリ URL）を含める
USER_AGENT = os.environ.get(
    "BANEI_USER_AGENT",
    "banei-keiba/0.1 (+https://github.com/banei-keiba/banei-keiba)",
)

# リクエスト間隔の既定値（秒）。相手サイトへの負荷を抑えるため 1 秒未満にしない。
REQUEST_INTERVAL = 1.0

# 日付の判定（開催日・探索 UI の締め）は JST で明示的に行う。GitHub ランナーのローカル時刻は
# UTC なので、ローカル日付に頼ると手元では正しくランナーでだけずれる（CLAUDE.md「環境まわり」）。
JST = dt.timezone(dt.timedelta(hours=9), "JST")
