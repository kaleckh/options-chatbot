# Decisions

## 2026-05-25: Narrow Active Work To Regular Options And AI Commodity Options

Active project work is limited to the regular supervised options lane and the AI commodity / commodity-infrastructure options lane for the foreseeable future.

The crypto options lane, Polymarket lane, and day-trading lane are out of scope for implementation, performance work, research cycles, documentation work, and automation work unless the user explicitly asks to archive, remove, repair, or reopen one of those lanes. The day-trading lane is paused rather than deleted.

Future agents should avoid optimizing or debugging `crypto_options/*`, `src/lib/polymarket/*`, `src/lib/day-trading/*`, and related lane-specific scripts/tests/docs unless that work is required by shared infrastructure for the active regular options or AI commodity options lanes.

## 2026-05-23: Make Bullish Pullback The Main Supervised Options Lane

The main supervised options scanner now defaults to `bullish_pullback_observation`, surfaced as Bullish Pullback Primary. It is a managed broad liquid-universe bullish call-vertical lane, not observation-only, and it keeps starter sizing while SPY/QQQ remain the currently historical-ready subset during closed forward Alpaca OPRA evidence collection.

`tracked_winner_primary` remains selectable, but it is secondary shape guidance because it was derived from previously tracked winners rather than a clean closed-forward OPRA proof loop. `quality90_debit55_canary` remains the proof/control yardstick and requires executable OPRA paper candidates.

No lane should be treated as promoted for sizing beyond the coded caps until closed forward Alpaca OPRA results show positive expectancy and pass the configured proof gates.

## 2026-05-22: Keep Alpaca OPRA As Preferred Proof, Add ThetaData NBBO Import Readiness

The commodity lane remains locked to Alpaca SIP/OPRA forward captures for the preferred proof path because the current repo artifacts isolate `alpaca_opra_daily_snapshot` as the accepted proof source and show only 2 of 100 required shared dates.

Historical Alpaca option bars and trades remain research-only because they do not preserve executable bid/ask BBO. Latest quote/snapshot surfaces count only when captured forward into the exact store.

ThetaData v3 historical option quotes are a valid OPRA-backed acquisition candidate if a licensed Standard/Pro terminal is available. A new importer was added to normalize ThetaData v3 NBBO rows into the existing historical option snapshot schema, but those rows must be isolated by source label and audited before any proof claim.

An authenticated Alpaca access probe on 2026-05-22 confirmed that the configured credentials can read historical option bars and trades and current/latest OPRA quote surfaces, but the suspected historical option quotes route `GET /v1beta1/options/quotes` returns 404. Until Alpaca exposes account-accessible historical bid/ask quotes, Alpaca can only accelerate the exact proof path through forward-captured latest OPRA snapshots.
