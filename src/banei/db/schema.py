"""SQLite のスキーマと接続ヘルパー。

レース結果（banei.db）とオッズ（odds.db）を別ファイルに分けているのは、
収集を並行実行してもロック競合しないようにするため。分析時は ATTACH で結合する。
"""

import sqlite3
from pathlib import Path

RACES_SCHEMA = """
CREATE TABLE IF NOT EXISTS races (
  race_date  TEXT NOT NULL,          -- YYYY-MM-DD
  race_no    INTEGER NOT NULL,
  name       TEXT,
  distance_m INTEGER,
  weather    TEXT,
  moisture   REAL,                   -- 馬場水分
  conditions TEXT,                   -- 条件行の生テキスト
  PRIMARY KEY (race_date, race_no)
);
CREATE TABLE IF NOT EXISTS results (
  race_date  TEXT NOT NULL,
  race_no    INTEGER NOT NULL,
  horse_no   INTEGER NOT NULL,
  horse_id   TEXT,                   -- keiba.go.jp の k_lineageLoginCode
  bracket    INTEGER,
  finish     INTEGER,                -- 着順（数値でない場合は NULL）
  status     TEXT,                   -- 着順欄の生テキスト（取消・中止など）
  horse_name TEXT,
  affiliation TEXT,
  sex        TEXT,
  age        INTEGER,
  weight_carried INTEGER,            -- 積載重量
  jockey     TEXT,
  trainer    TEXT,
  horse_weight INTEGER,
  horse_weight_diff INTEGER,
  time_str   TEXT,
  time_sec   REAL,
  margin     TEXT,
  popularity INTEGER,
  PRIMARY KEY (race_date, race_no, horse_no)
);
CREATE TABLE IF NOT EXISTS payouts (
  race_date   TEXT NOT NULL,
  race_no     INTEGER NOT NULL,
  bet_type    TEXT NOT NULL,
  combination TEXT NOT NULL,
  amount      INTEGER,               -- 100円あたり払戻金額
  popularity  INTEGER,
  PRIMARY KEY (race_date, race_no, bet_type, combination)
);
CREATE TABLE IF NOT EXISTS scraped_days (
  race_date  TEXT PRIMARY KEY,
  n_races    INTEGER,
  scraped_at TEXT
);
"""

ODDS_SCHEMA = """
CREATE TABLE IF NOT EXISTS odds (
  race_date  TEXT NOT NULL,
  race_no    INTEGER NOT NULL,
  horse_no   INTEGER NOT NULL,
  horse_name TEXT,
  win_odds   REAL,               -- 単勝確定オッズ
  place_min  REAL,               -- 複勝レンジ下限
  place_max  REAL,
  PRIMARY KEY (race_date, race_no, horse_no)
);
CREATE TABLE IF NOT EXISTS odds_meta (
  race_date  TEXT NOT NULL,
  race_no    INTEGER NOT NULL,
  n_horses   INTEGER,
  scraped_at TEXT,
  PRIMARY KEY (race_date, race_no)
);
CREATE TABLE IF NOT EXISTS combo_odds (
  race_date  TEXT NOT NULL,
  race_no    INTEGER NOT NULL,
  bet_type   TEXT NOT NULL,
  combination TEXT NOT NULL,
  odds       REAL,               -- ワイドはレンジ下限
  odds_max   REAL,               -- ワイドのみ
  PRIMARY KEY (race_date, race_no, bet_type, combination)
);
CREATE TABLE IF NOT EXISTS combo_meta (
  race_date  TEXT NOT NULL,
  race_no    INTEGER NOT NULL,
  bet_type   TEXT NOT NULL,
  n_combos   INTEGER,
  scraped_at TEXT,
  PRIMARY KEY (race_date, race_no, bet_type)
);
"""


def connect(path: Path | str, schema: str | None = None) -> sqlite3.Connection:
    """書き込み用に接続する。schema を渡すと未作成のテーブルを作る。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=60)
    if schema:
        con.executescript(schema)
    return con


def connect_readonly(path: Path | str) -> sqlite3.Connection:
    """読み取り専用で接続する。収集中の DB を参照するときに使う。"""
    return sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True, timeout=60)
