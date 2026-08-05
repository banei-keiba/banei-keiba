#!/usr/bin/env bash
#
# 過去分の確定オッズを手元から少しずつ埋め、結果をバックアップへ書き戻す。
#
#   ./scripts/backfill-local.sh [件数] [間隔秒]
#   ./scripts/backfill-local.sh 1000 1.0     # 既定
#
# **なぜ手元で回すのか**
# オッズパークは GitHub Actions の IP からのアクセスに HTTP 500 を返す。
# 2026-08-06 に確認した内容:
#   - ランナーからは 200〜1,400 件あたりで全リクエストが 500 になる
#   - 間隔を 1 秒から 2 秒に広げても改善せず、むしろ早く失敗した
#   - **同じレースを手元から叩くと 400 件連続で失敗ゼロ**
# レートやデータの問題ではなく送信元による制限なので、この作業だけは手元で行う。
#
# 日次収集とは DB を共有する。実行中に日次が走ると、こちらが書き戻したときに
# 日次の取得分が巻き戻る。ただし scraped_days も一緒に巻き戻るため、
# 次の日次実行がその日を取り直す（自己修復する）。データは失われない。

set -euo pipefail

REPO="${BANEI_BACKUP_REPO:-banei-keiba/banei-db-backup}"
DATA_DIR="${BANEI_DATA_DIR:-data}"
LIMIT="${1:-1000}"
INTERVAL="${2:-1.0}"

remote_stamp() {
  gh release view latest --repo "$REPO" --json assets --jq '[.assets[].updatedAt] | max'
}

echo "=== 最新のバックアップを取得 ==="
before="$(remote_stamp)"
gh release download latest --repo "$REPO" --dir "$DATA_DIR" --clobber
gunzip -f "$DATA_DIR/banei.db.gz" "$DATA_DIR/odds.db.gz"

remaining() {
  sqlite3 "$DATA_DIR/odds.db" "ATTACH '$DATA_DIR/banei.db' AS b;
    SELECT (SELECT COUNT(*) FROM b.races) - (SELECT COUNT(*) FROM odds_meta);"
}
echo "未取得 $(remaining) レース"

echo "=== オッズを取得（最大 $LIMIT 件・間隔 ${INTERVAL}s）==="
uv run banei odds --limit "$LIMIT" --interval "$INTERVAL"

echo "=== 検証 ==="
uv run banei validate --quiet

after="$(remote_stamp)"
if [[ "$before" != "$after" ]]; then
  echo "警告: 実行中にバックアップが更新された（日次収集と重なった）。" >&2
  echo "  書き戻すと日次の取得分が巻き戻るが、scraped_days も戻るので" >&2
  echo "  次の日次実行が取り直す。データは失われない。" >&2
fi

echo "=== バックアップへ書き戻す ==="
./scripts/backup-db.sh

echo "残り $(remaining) レース"
