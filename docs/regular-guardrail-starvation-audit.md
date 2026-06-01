# Regular Guardrail Starvation Audit

- Generated: `2026-06-01T02:44:08Z`
- Status: `upstream_zero_candidate_scan_pressure`
- Playbooks completed/requested: `13` / `13`
- Candidate/returned totals: `0` / `0`
- Candidate guardrail decisions: `{}`
- Starvation playbooks: `[]`
- Zero-candidate playbooks: `13`
- Market open at run: `False`

## Leading Upstream Drops

- `direction_filter`: `115`
- `option_liquidity`: `96`
- `momentum`: `72`
- `history_or_liquidity`: `60`
- `tech_score`: `33`
- `direction_score`: `2`
- `min_history`: `0`
- `signal_index`: `0`

## Leading Drop Details

- `direction_filter`: `65` - put not in allowed directions call (`COIN, COP, CVX, DIS, GOOGL, JNJ, JPM, KO`)
- `history_or_liquidity`: `60` - underlying history/liquidity gate; tier=thin (`AMT, CAT, CLF, COST, DE, EQR, GS, LIN`)
- `direction_filter`: `50` - call not in allowed directions put (`AA, AAPL, ABBV, AMD, AMZN, ARM, BA, C`)
- `momentum`: `47` - close > SMA50, ret20 > 2%, and -4% < ret5 < 0.25% (`AA, AAPL, ABBV, AMD, AMZN, ARM, BA, BAC`)
- `option_liquidity`: `32` - illiquid_quote: wide_leg_spread,stale_leg_quote,stale_quote_freshness (`AMD, C, FCX, MSFT, NKE, PLTR, SMCI, TSLA`)
- `momentum`: `25` - momentum/trend signal not met (`BAC, NEM, PG, PLD, V`)
- `option_liquidity`: `19` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,stale_leg_quote,stale_quote_freshness (`AA, AAPL, ABBV, AMZN, ARM, BA, LLY, SMCI`)
- `option_liquidity`: `15` - no_valid_spread (`AAPL, AMZN, IWM, MSFT, QQQ, SPY, TSLA`)

## Interpretation

- Current no-pick state is upstream scanner/data/liquidity pressure, not promoted guardrail starvation.
