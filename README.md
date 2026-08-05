# banei-keiba

ばんえい競馬（帯広）のデータ収集・分析。

レース結果とオッズを収集して SQLite に蓄積し、LightGBM で勝率モデルを学習して
バックテストする。将来的にはここで得られた集計・分析結果を Web サイトとして公開する。

技術方針とロードマップは [docs/architecture.md](docs/architecture.md) を参照。

## データ公開方針

**スクレイピングした生データをそのまま表示・配布しない。** 公開するのは集計値・派生指標・
分析結果のみで、個別レースの着順表やオッズ一覧は出さない。判断基準は「そのページを全部
集めれば元のデータベースが復元できてしまうか」。詳細は
[docs/architecture.md §3.4](docs/architecture.md)。

このリポジトリに `.db` ファイルは含まれない（`data/` は .gitignore 済み）。

## セットアップ

```bash
uv sync --all-extras
```

収集だけを行う場合は重い ML 依存を省ける。

```bash
uv sync
```

## 使い方

データは既定で `data/` 配下に置かれる（`BANEI_DATA_DIR` で変更可）。

```bash
# レース結果を収集（keiba.go.jp）
uv run banei scrape --start 2024-01 --end 2024-12

# 単勝・複勝の確定オッズを収集（オッズパーク）
uv run banei odds

# 組み合わせ券種の確定オッズ（三連単は重いので期間を絞る）
uv run banei combo-odds --types umatan,umaren,wide,sanrenpuku
uv run banei combo-odds --types sanrentan --since 2020-04-01

# 払戻金ベースの戦略バックテスト
uv run banei backtest

# 実オッズを使った EV バックテスト
uv run banei backtest-ev
```

いずれの収集コマンドも 1 リクエスト/秒で、取得済みのレースはスキップする。
中断してもそのまま再実行すれば続きから取得できる。

## データ

| DB | テーブル | 内容 |
|---|---|---|
| `banei.db` | `races` | レース情報（レース名・距離・天候・**馬場水分**・条件） |
| | `results` | 着順（馬名・性齢・積載重量・騎手・調教師・馬体重・タイム・人気） |
| | `payouts` | 払戻金（単勝〜三連単、100円あたり） |
| | `scraped_days` | 取得済み開催日の管理 |
| `odds.db` | `odds` | 単勝・複勝の確定オッズ |
| | `combo_odds` | 馬単・馬複・ワイド・三連複・三連単の確定オッズ |

主キーは `(race_date, race_no [, horse_no])`。着順が付かない馬は `finish` が NULL で
`status` に理由（取消・除外・中止・失格）が入る。

レース結果とオッズを別ファイルに分けているのは、収集を並行実行してもロック競合しない
ようにするため。分析時は `ATTACH 'odds.db' AS o` で結合する。

確定オッズは払戻金（÷100）との照合で完全一致を検証済み。

## バックアップ

生データは非公開リポジトリのリリースアセットへ退避する。

```bash
./scripts/backup-db.sh
```

`VACUUM INTO` で一貫性のあるスナップショットを取り（収集中でも安全）、`integrity_check` を
通してから gzip して上げる。92MB → 22MB。復元は:

```bash
gh release download latest --repo banei-keiba/banei-db-backup --dir data
gunzip data/banei.db.gz data/odds.db.gz
```

詳細は [docs/architecture.md](docs/architecture.md) の Phase 0 を参照。

## 開発

```bash
uv run ruff check .
uv run pytest
```

## 注意

- スクレイピングは 1 リクエスト/秒を守り、User-Agent に本リポジトリの URL を含めている
- 予想・バックテストの結果は的中を保証するものではない。バックテストは確定オッズで
  購入できたという仮定に基づいており（スリッページ未考慮）、実際の成績より楽観的になる
