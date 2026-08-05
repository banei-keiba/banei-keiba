#!/usr/bin/env bash
#
# SQLite の生データを非公開リポジトリのリリースアセットへ退避する。
#
#   ./scripts/backup-db.sh [--dry-run]
#
# 各 DB について VACUUM INTO でスナップショットを作る。これは収集中でも一貫性のある
# コピーが取れ、同時に断片化も解消される。その後 gzip して gh release へ上げる。
#
# アセットは git 履歴に入らないため、日次で回してもリポジトリは肥大化しない。
#
# リリース構成:
#   latest              毎回上書き。復元時はここから取る
#   snapshot-YYYY-MM    月内は上書き。取り違え時の巻き戻し用
#
# 前提: gh CLI が認証済みであること（gh auth login）。
# 退避先は必ず private リポジトリであること。生データを含むため、public だと
# 本体のデータ公開方針（docs/architecture.md §3.4）に反する。

set -euo pipefail

REPO="${BANEI_BACKUP_REPO:-banei-keiba/banei-db-backup}"
DATA_DIR="${BANEI_DATA_DIR:-data}"
DBS=(banei.db odds.db)

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

# 生データを public リポジトリへ上げてしまう事故を防ぐ
if [[ "$(gh repo view "$REPO" --json isPrivate --jq .isPrivate)" != "true" ]]; then
  echo "エラー: $REPO が private ではない。生データの退避先にできない" >&2
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

month="$(date +%Y-%m)"
tags=(latest "snapshot-$month")

ensure_release() {
  local tag="$1"
  if ! gh release view "$tag" --repo "$REPO" >/dev/null 2>&1; then
    gh release create "$tag" --repo "$REPO" \
      --title "$tag" \
      --notes "banei.db / odds.db のスナップショット（scripts/backup-db.sh が生成）" \
      >/dev/null
  fi
}

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

  for tag in "${tags[@]}"; do
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "  [dry-run] upload $REPO $tag/$name.gz"
    else
      echo "  upload $REPO $tag/$name.gz"
      ensure_release "$tag"
      gh release upload "$tag" "$snap.gz" --repo "$REPO" --clobber
    fi
  done
done

if [[ $DRY_RUN -eq 1 ]]; then
  echo "dry-run 完了（アップロードは行っていない）"
else
  echo "退避完了: $REPO"
fi
