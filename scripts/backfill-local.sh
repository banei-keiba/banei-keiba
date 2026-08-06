#!/usr/bin/env bash
#
# 過去分の確定オッズを手元から少しずつ埋め、結果をバックアップへ書き戻す。
#
#   ./scripts/backfill-local.sh [件数] [間隔秒] [種別]
#   ./scripts/backfill-local.sh 2000 1.0          # 単複オッズ（既定）
#   ./scripts/backfill-local.sh 500  1.0 combo    # 組み合わせ4券種（1レース4req）
#
# **なぜ手元で回すのか**
# オッズパークには送信元ごとの累積クォータ（時間窓ベース）がある。
# 2026-08-06 の実測:
#   - GitHub ランナー 1秒間隔: 約1,490件で 500 が出始める
#   - GitHub ランナー 2秒間隔: 約253件（前回の失敗から30分しか空けなかったため、
#                              直前1時間の窓が埋まったまま始まった）
#   - 手元(WSL2) 1秒間隔:      2,400件を連続で完走、失敗ゼロ
# 間隔を広げても効かないのは、制限が瞬間レートではなく累積本数だから。
# GitHub Actions の IP は全ユーザー共有で他人の分も枠を食うため、枠が小さい。
# 手元が無制限という証拠はないので、区切って回し実行の合間を空けること。
#
# 日次収集とは DB を共有する。実行中に日次が走ると、こちらが書き戻したときに
# 日次の取得分が巻き戻る。ただし scraped_days も一緒に巻き戻るため、
# 次の日次実行がその日を取り直す（自己修復する）。データは失われない。

set -euo pipefail

REPO="${BANEI_BACKUP_REPO:-banei-keiba/banei-db-backup}"
DATA_DIR="${BANEI_DATA_DIR:-data}"
LIMIT="${1:-1000}"
INTERVAL="${2:-1.0}"
KIND="${3:-odds}"

case "$KIND" in
  odds)  ;;
  combo) ;;
  *) echo "種別は odds か combo" >&2; exit 1 ;;
esac

remote_stamp() {
  gh release view latest --repo "$REPO" --json assets --jq '[.assets[].updatedAt] | max'
}

echo "=== 最新のバックアップを取得 ==="
before="$(remote_stamp)"
gh release download latest --repo "$REPO" --dir "$DATA_DIR" --clobber
gunzip -f "$DATA_DIR/banei.db.gz" "$DATA_DIR/odds.db.gz"

remaining() {
  if [[ "$KIND" == "combo" ]]; then
    # 4券種ぶんなので「レース数 × 4 - 取得済み」
    sqlite3 "$DATA_DIR/odds.db" "ATTACH '$DATA_DIR/banei.db' AS b;
      SELECT (SELECT COUNT(*) FROM b.races) * 4
             - (SELECT COUNT(*) FROM combo_meta WHERE bet_type <> '三連単');"
  else
    sqlite3 "$DATA_DIR/odds.db" "ATTACH '$DATA_DIR/banei.db' AS b;
      SELECT (SELECT COUNT(*) FROM b.races) - (SELECT COUNT(*) FROM odds_meta);"
  fi
}
echo "未取得 $(remaining) 件（$KIND）"

echo "=== オッズを取得（最大 $LIMIT・間隔 ${INTERVAL}s・$KIND）==="
if [[ "$KIND" == "combo" ]]; then
  uv run banei combo-odds --limit "$LIMIT" --interval "$INTERVAL"
else
  uv run banei odds --limit "$LIMIT" --interval "$INTERVAL"
fi

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

echo "残り $(remaining) 件"
