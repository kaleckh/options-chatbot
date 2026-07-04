# ThetaData Terminal Runbook

This runbook owns local ThetaData readiness for regular supervised-options quote imports. It is operational memory, not a proof artifact.

## Current Runtime

- Current local terminal: `C:\Users\kalec\Downloads\ThetaTerminalv3.jar`
- Current Java runtime: `C:\Users\kalec\theta-java21\jdk-21.0.11+10-jre\bin\java.exe`
- Current v3 config: `C:\Users\kalec\Downloads\config.toml`
- Current repo URL: `http://127.0.0.1:25503`
- Current stdout/stderr files: `C:\Users\kalec\ThetaData\ThetaTerminal\logs\thetaterminal-v3-stdout.log` and `C:\Users\kalec\ThetaData\ThetaTerminal\logs\thetaterminal-v3-stderr.log`

Do not echo, paste, or commit the credential file contents. Use the credential file path only.

The old `C:\Users\kalec\ThetaData\ThetaTerminal\config_0.properties` is a v1.7-era file with `HTTP_PORT=25510`; it is not the current repo's ThetaData v3 runtime path.

## Start Terminal

```powershell
$java = 'C:\Users\kalec\theta-java21\jdk-21.0.11+10-jre\bin\java.exe'
$jar = 'C:\Users\kalec\Downloads\ThetaTerminalv3.jar'
$creds = 'C:\Users\kalec\ThetaData\creds.txt'
$out = 'C:\Users\kalec\ThetaData\ThetaTerminal\logs\thetaterminal-v3-stdout.log'
$err = 'C:\Users\kalec\ThetaData\ThetaTerminal\logs\thetaterminal-v3-stderr.log'

Start-Process -FilePath $java `
  -ArgumentList @('-jar', $jar, '--creds-file', $creds) `
  -WorkingDirectory 'C:\Users\kalec\Downloads' `
  -WindowStyle Hidden `
  -RedirectStandardOutput $out `
  -RedirectStandardError $err
```

## Readiness Probe

First check that the port is listening:

```powershell
Get-NetTCPConnection -LocalPort 25503
Get-Content C:\Users\kalec\ThetaData\ThetaTerminal\logs\thetaterminal-v3-stdout.log -Tail 40
```

Then probe the importer itself. The importer dry run is the readiness check because it exercises the same endpoint and parsing path used by the replay queues:

```powershell
uv run --locked python scripts\import_thetadata_options_nbbo.py --symbols QQQ,SPY --date-from 2026-05-21 --date-to 2026-05-21 --snapshot-kind intraday --start-time 10:27:00 --end-time 10:27:00 --interval 1m --min-dte 28 --max-dte 28 --right call --theta-url http://127.0.0.1:25503 --timeout 60 --dry-run --json
```

Do not use `/v3/system/status` as the repo readiness check. The current v3 terminal can return `404` there while the importer endpoint works.

## Quote Import Loop

Use this order when a command-center queue item asks for ThetaData quote imports:

```powershell
npm run options:replay:execution-alternative-coverage
npm run options:plan:execution-alternative-quote-import
```

Run the generated command groups from `data/forward-tracking/regular_options_execution_alternative_quote_import_plan_latest.json`. Dry-run first; if generated rows are nonzero and errors are clean, run the write imports. After the write imports:

```powershell
npm run options:replay:execution-alternative-coverage
npm run options:plan:execution-alternative-quote-import
npm run options:profitability-layer-stack
npm run options:audit:monthly-profitability
npm run options:gateboard
```

For minute-exit quote demand work, use the same service readiness rule and rerun:

```powershell
npm run options:replay:minute-exit-readiness
npm run options:plan:minute-exit-quote-import
npm run options:profitability-layer-stack
npm run options:audit:monthly-profitability
npm run options:gateboard
```

## Failure Rules

- `WinError 10061`, connection refused, or no listener on `25503` means the feed is down. Start ThetaTerminal v3 and rerun the dry-run probe before archiving, quarantining, or declaring quote exhaustion.
- `403 Forbidden` with terminal output showing `Options: FREE` means the local terminal is running but the loaded credentials do not have the required paid options entitlement. Fix or replace `C:\Users\kalec\ThetaData\creds.txt`, restart ThetaTerminal v3, and rerun the provider recheck before retrying imports.
- A feed-down dry run is not evidence that the requested contract/date has no OPRA/NBBO evidence.
- Archive current-source exhausted contracts only after the terminal is reachable and durable exact contract/date attempts still return current-provider no-match evidence.
- Imported quote rows and read-only execution-alternative replay coverage are not production proof. Production proof still requires trusted intraday exact-contract OPRA/NBBO bid/ask plus executable entry, exit, fill, and P&L for the actual trade surface being claimed.

## 2026-06-29 Readback

ThetaTerminal v3 was reachable on `25503`, and the running Java command used `C:\Users\kalec\ThetaData\creds.txt`, but the terminal banner reported `Subscriptions: Stock: FREE Options: FREE Index: FREE Rate: FREE`. The QQQ/SPY option-history probe returned `403 Forbidden`, and the 59-symbol resume artifact now reports `blocked_thetadata_options_entitlement` with no import attempted. This is a credential/entitlement blocker, not a down-terminal blocker.

Later the operator supplied a `td1_prod_...` API key. That key was stored locally at `C:\Users\kalec\ThetaData\api-key.txt` for future use, but it is not a drop-in `--creds-file` value for the current ThetaTerminal builds. Testing it as the password half of a two-line creds file and as a key-only creds file both returned `Invalid credentials`. The original `creds.txt` email/password also returned `Invalid credentials` after the subscription change. To use ThetaTerminal, provide a valid two-line username/password creds file or official ThetaData API-key terminal instructions; do not keep retrying the API key through `--creds-file`.

## 2026-06-08 Readback

ThetaTerminal v3 was started on `25503` and the execution-alternative quote plan's `8` command groups were imported from the local v3 service. The write imports generated `9,710` quote rows, imported `9,500`, and had `0` errors and `0` rejected rows. After rerunning coverage, the execution-alternative replay coverage report moved to `execution_alternative_replay_coverage_ready`: missing quote demands `0`, top-spread true replay P&L rows `12`, and contract-replacement true replay P&L rows `12`. The follow-up quote import plan moved to `no_quote_demands_to_plan`.
