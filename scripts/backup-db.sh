#!/usr/bin/env bash
#
# SQLite の生データを Cloudflare R2（非公開バケット）へ退避する。
#
#   ./scripts/backup-db.sh [--dry-run]
#
# 各 DB について VACUUM INTO でスナップショットを作る。これは収集中でも一貫性のある
# コピーが取れ、同時に断片化も解消される。その後 gzip して R2 へ置く。
#
# キー構成:
#   latest/<name>.gz            毎回上書き。復元時はこれを取る
#   snapshots/<YYYY-MM>/<name>.gz  月内は上書き。取り違え時の巻き戻し用
#
# 前提: Cloudflare アカウントと `npx wrangler login` 済みであること。
# バケットは public access を有効にしないこと（生データの置き場のため）。

set -euo pipefail

BUCKET="${BANEI_R2_BUCKET:-banei-private}"
DATA_DIR="${BANEI_DATA_DIR:-data}"
DBS=(banei.db odds.db)

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

month="$(date +%Y-%m)"

for name in "${DBS[@]}"; do
  src="$DATA_DIR/$name"
  if [[ ! -f "$src" ]]; then
    echo "エラー: $src が見つからない" >&2
    exit 1
  fi

  echo "=== $name ==="
  snap="$WORK/$name"
  sqlite3 "$src" "VACUUM INTO '$snap'"

  check="$(sqlite3 "$snap" 'PRAGMA integrity_check;')"
  if [[ "$check" != "ok" ]]; then
    echo "エラー: $name のスナップショットが壊れている: $check" >&2
    exit 1
  fi

  gzip -9 "$snap"
  before=$(stat -c%s "$src")
  after=$(stat -c%s "$snap.gz")
  printf '  %s -> %s (%.1f%%)\n' \
    "$(numfmt --to=iec "$before")" "$(numfmt --to=iec "$after")" \
    "$(awk "BEGIN{print 100*$after/$before}")"

  for key in "latest/$name.gz" "snapshots/$month/$name.gz"; do
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "  [dry-run] put $BUCKET/$key"
    else
      echo "  put $BUCKET/$key"
      npx --yes wrangler r2 object put "$BUCKET/$key" \
        --file "$snap.gz" --remote --force >/dev/null
    fi
  done
done

if [[ $DRY_RUN -eq 1 ]]; then
  echo "dry-run 完了（アップロードは行っていない）"
else
  echo "退避完了: $BUCKET"
fi
