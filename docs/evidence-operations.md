# Evidence Operations

This is the operational contract for evidence stores that cannot be recreated by replay. Calendar-time forward evidence is treated as product data, not cache.

## Authoritative Host

The current authoritative evidence host is declared in `data/contracts/evidence-host-policy.json`:

- `authoritative_host`: `KaesDevice`
- evidence home: `C:/Users/kalec/options-chatbot`
- source-of-truth stores:
  - Postgres tracked positions via `DATABASE_URL`
  - `chat_history.db`
  - `data/options-validation/forward_tracking_authoritative.db`
  - `data/options-validation/options_history.db`

Non-authoritative hosts may run read-only reports after sync, but they must not append forward evidence or mutate the named stores. `scripts/log_scan_picks.py` fails closed on a non-authoritative host before scan/fill log writes, forward-ledger writes, tracked-position review, or auto-track work. If the evidence home changes, update `data/contracts/evidence-host-policy.json` and the scheduled task host together.

## Backups

Nightly local backup command:

```powershell
npm run evidence:backup
```

The backup script writes ignored bundles under `data/backups/<timestamp>/`, keeps a manifest in each bundle, and prunes local bundles older than `14` days. SQLite stores are copied through the SQLite backup API. Postgres tracked positions are dumped with `pg_dump --format=custom` from `OPTIONS_BACKUP_DATABASE_URL` or `DATABASE_URL`.

Weekly off-machine copy command:

```powershell
$env:OPTIONS_BACKUP_WEEKLY_COPY_DIR = "D:\options-evidence-backups"
npm run evidence:backup:weekly
```

Use an external drive, iCloud/OneDrive folder, NAS, or another off-machine target. The weekly copy command copies the completed backup bundle, including its manifest, into an ISO-week subdirectory. Do not commit `data/backups/`.

## Scheduled Scan Heartbeat

Every scheduled scan run writes `data/forward-tracking/scheduled_scan_heartbeat_latest.json` with status, host, commit SHA, branch, run id, scan date, and evidence-host policy. The heartbeat is ignored because it is local scheduler telemetry; builders consume the latest local copy when present.

Health check:

```powershell
npm run scan:heartbeat
```

`scripts/build_project_operator_gateboard.py` and `scripts/build_monthly_all_lanes_profitability_audit.py` read the heartbeat and expose `days_since_last_scheduled_scan`. The readback goes red after more than `2` market days without a completed scheduled scan.

## Daily Operator Command

Run the low-mutation daily chores from one command:

```powershell
npm run options:daily-ops
```

This chains the open-risk plan, suggested-trade review plan, fill-attempt evidence capture plan, paper-filter monitor, strict paper shortlist, fresh-evidence loop, candidate ledger, and gateboard refresh. The command writes readback artifacts and reports, but it is not a broker action, scanner-policy change, or proof-bar change.

## Retention

Keep curated `*_latest` artifacts when living docs reference them. Treat timestamped run snapshots and one-off pre-repair dumps as local evidence sprawl unless a report explicitly promotes them.

Default retention rule:

- `data/tracked_positions.pre-*.json`: move to backup storage after `90` days unless cited by a current repair report.
- `research_runs/`: compress or archive runs older than `6` months unless referenced by current docs.
- `data/backups/`: local rolling `14` days plus weekly off-machine copy.

Do not delete irreplaceable evidence stores to make the repo smaller. Move bulky local snapshots to backup storage and keep a manifest trail.
