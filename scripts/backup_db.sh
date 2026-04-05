#!/usr/bin/env bash
# backup_db.sh — Create a timestamped backup of the DuckDB data file.
#
# Usage:
#   bash scripts/backup_db.sh
#
# Cron (daily at 02:00):
#   0 2 * * * cd /home/d-tuned/projects/gap-lens-dilution-filter && bash scripts/backup_db.sh
#
# Keeps the last 7 daily backups; older ones are removed automatically.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_SRC="$PROJECT_ROOT/data/filter.duckdb"
BACKUP_DIR="$PROJECT_ROOT/data/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DEST="$BACKUP_DIR/filter_${TIMESTAMP}.duckdb"

if [ ! -f "$DB_SRC" ]; then
    echo "ERROR: Database not found at $DB_SRC"
    exit 1
fi

mkdir -p "$BACKUP_DIR"
cp "$DB_SRC" "$DEST"
echo "Backup created: $DEST"

# Prune backups older than 7 days
find "$BACKUP_DIR" -name "filter_*.duckdb" -mtime +7 -delete
REMAINING=$(find "$BACKUP_DIR" -name "filter_*.duckdb" | wc -l)
echo "Backups retained: $REMAINING"
