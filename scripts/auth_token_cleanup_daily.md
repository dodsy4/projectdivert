# Daily Auth Token Cleanup (macOS)

This project includes a scheduled cleanup for stale auth lifecycle tokens using `launchd`.
The scheduled runner is installed into `~/Library/Application Support/projectdivert/` so it can run in the background without macOS blocking access to `~/Documents`.

## What It Runs

`$HOME/Library/Application Support/projectdivert/auth-token-cleanup-runner.sh`

That runner executes:

Batch SQL deletes equivalent to:

`auth-token-cleanup --retention-days <N> --batch-size <N>`

Defaults:
- retention days: `30`
- batch size: `500`

## 1) Ensure your env file has DB settings

By default, the scheduler loads:

`$HOME/.projectdivert-auth-cleanup.env`

If you use a different file, pass it with `--env-file`.

## 2) Install daily schedule

From project root:

```bash
chmod +x scripts/install_daily_auth_token_cleanup_launchd.sh scripts/uninstall_daily_auth_token_cleanup_launchd.sh
./scripts/install_daily_auth_token_cleanup_launchd.sh --hour 3 --minute 15
```

Optional flags:
- `--env-file /absolute/path/to/env-file`
- `--retention-days 30`
- `--batch-size 500`
- `--label com.projectdivert.auth-token-cleanup`

## 3) Verify job

```bash
launchctl print "gui/$(id -u)/com.projectdivert.auth-token-cleanup"
```

Run immediately (without waiting for schedule):

```bash
launchctl kickstart -k "gui/$(id -u)/com.projectdivert.auth-token-cleanup"
```

Watch logs:

```bash
tail -f "$HOME/Library/Logs/projectdivert/auth-token-cleanup.log" \
        "$HOME/Library/Logs/projectdivert/auth-token-cleanup.error.log"
```

## 4) Uninstall

```bash
./scripts/uninstall_daily_auth_token_cleanup_launchd.sh
```
