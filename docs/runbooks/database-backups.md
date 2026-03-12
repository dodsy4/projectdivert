# Database Backups

## Scope
This runbook covers:
- manual Postgres backups
- daily local backup automation on macOS via `launchd`
- basic archive verification and restore drill steps

## Environment
The backup scripts use either:
- `DATABASE_URL`, or
- `PGHOST` / `PGPORT` / `PGDATABASE` / `PGUSER` / `PGPASSWORD` / `PGSSLMODE`

For Neon, use the same connection settings you use for migrations and smoke tests.

If your server version is newer than the local PostgreSQL client, point the scripts at a newer client install with:
- `PG_BIN_DIR=/opt/homebrew/opt/postgresql@18/bin`

Example install on Apple Silicon Macs:

```bash
brew install postgresql@18
```

## Manual Backup
Create a full custom-format archive:

```bash
cd /Users/louisdods/Documents/GitHub/projectdivert
PG_BIN_DIR=/opt/homebrew/opt/postgresql@18/bin \
  ./scripts/db_backup.sh --output-dir "$HOME/Backups/projectdivert" --retention-days 14
```

Create a schema-only backup:

```bash
./scripts/db_backup.sh --schema-only --output-dir "$HOME/Backups/projectdivert"
```

The script writes:
- the backup archive (`.dump` or `.sql`)
- a JSON manifest next to it with `sha256`, file path, size, and timestamp

## Restore Drill
List archive contents:

```bash
pg_restore --list "$HOME/Backups/projectdivert/projectdivert-db_neondb_YYYYMMDDTHHMMSSZ.dump" | head
```

Restore into a scratch database:

```bash
createdb projectdivert_restore_drill
pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  --dbname projectdivert_restore_drill \
  "$HOME/Backups/projectdivert/projectdivert-db_neondb_YYYYMMDDTHHMMSSZ.dump"
```

Verify expected tables exist:

```bash
psql projectdivert_restore_drill -c "\dt"
```

Destroy the scratch database after verification:

```bash
dropdb projectdivert_restore_drill
```

Use the explicit drill checklist while doing this:
- [restore-drill-checklist.md](/Users/louisdods/Documents/GitHub/projectdivert/docs/runbooks/restore-drill-checklist.md)

Or run the scripted drill:

```bash
cd /Users/louisdods/Documents/GitHub/projectdivert
source .venv/bin/activate
export FLASK_APP=app.py
PG_BIN_DIR=/opt/homebrew/opt/postgresql@18/bin \
  bash ./scripts/restore_drill.sh --backup-file "$HOME/Backups/projectdivert/projectdivert-db_neondb_YYYYMMDDTHHMMSSZ.dump"
```

## Daily Automation (macOS)
Create an env file outside protected folders:

```bash
cat > "$HOME/.projectdivert-db-backup.env" <<'EOF'
PGHOST=your-db-host
PGPORT=5432
PGDATABASE=your-db-name
PGUSER=your-db-user
PGPASSWORD=replace-me
PGSSLMODE=require
BACKUP_OUTPUT_DIR=$HOME/Backups/projectdivert
BACKUP_RETENTION_DAYS=14
BACKUP_LABEL=projectdivert-db
PG_BIN_DIR=/opt/homebrew/opt/postgresql@18/bin
EOF
chmod 600 "$HOME/.projectdivert-db-backup.env"
```

Install the daily backup job:

```bash
cd /Users/louisdods/Documents/GitHub/projectdivert
./scripts/install_daily_db_backup_launchd.sh \
  --hour 2 --minute 45 \
  --env-file "$HOME/.projectdivert-db-backup.env" \
  --output-dir "$HOME/Backups/projectdivert" \
  --retention-days 14
```

Trigger it immediately:

```bash
launchctl kickstart -k "gui/$(id -u)/com.projectdivert.db-backup"
```

Inspect logs:

```bash
tail -f "$HOME/Library/Logs/projectdivert/db-backup.log" \
  "$HOME/Library/Logs/projectdivert/db-backup.error.log"
```

Remove automation:

```bash
cd /Users/louisdods/Documents/GitHub/projectdivert
./scripts/uninstall_daily_db_backup_launchd.sh
```

## Operational Standard
- Keep at least 14 daily backups.
- Run a restore drill at least once per month.
- Treat missing manifests, checksum mismatch, or unreadable `pg_restore --list` output as a backup failure.
- Do not keep backup env files world-readable.
- Use the release runbook before deploys:
  - [release-and-rollback.md](/Users/louisdods/Documents/GitHub/projectdivert/docs/runbooks/release-and-rollback.md)
