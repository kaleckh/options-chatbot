# Regular Options Open-Risk Executable Review

Generated at: `2026-06-08T16:36:01Z`

Qualifying outcome: named open-risk position reviewed with exact current executable exit evidence.

## Position

- Row: `537`
- Lane: `volatility_expansion_observation`
- Ticker: `QQQ`
- Structure: `QQQ260618C00728000` / `QQQ260618C00750000` call vertical, one contract
- Entry execution debit: `9.0405`, basis `spread_ask_bid`
- Prior latest review: `2026-06-06T14:00:04.496347-06:00`, exit value `3.784`, net P&L `-58.2639%`, recommendation `HOLD`

## Exact Current Quotes

Source: `thetadata_opra_nbbo_1m` via `http://127.0.0.1:25503/v3/option/history/quote`

Request: `symbol=QQQ`, `expiration=20260618`, `date=20260608`, `interval=1m`, `start_time=12:31`, `end_time=12:34`, `right=call`, `strike_range=80`.

Current-day ThetaData quote history required an exact expiration; wildcard expiration returned parameter validation, not feed exhaustion.

| Leg | Contract | Timestamp UTC | Bid | Ask | Executable side |
| --- | --- | --- | ---: | ---: | --- |
| Long exit | `QQQ260618C00728000` | `2026-06-08T16:34:00Z` | `8.43` | `8.49` | bid |
| Short cover | `QQQ260618C00750000` | `2026-06-08T16:34:00Z` | `1.87` | `1.91` | ask |

## Executable Exit

- Pricing rule: long option exit uses bid; short option cover uses ask.
- Executable spread exit value: `8.43 - 1.91 = 6.52`
- Gross P&L: `(6.52 - 9.0405) * 100 * 1 = -$252.05`
- Fee assumption: `$2.60` total
- Net P&L: `-$254.65`
- Net P&L percent: `-28.1677%`
- Slippage assumption: no additional slippage beyond executable bid/ask side pricing.

## Decision

Recommendation: `HOLD`

Risk decision: `hold_under_existing_stop_target_time_rules`

Reason: exact executable exit value `6.52` is above the configured stop exit price `1.2747`, below the profit target exit price `22.6013`, and before the configured time-exit threshold. No close action is recorded here because broker orders and trading-row mutations are prohibited in this loop.

Boundary: this is a read-only current exact executable open-risk review. It is not production proof, a broker fill, a realized P&L row, a lane promotion, a scanner policy change, or a stop/sizing change.
