# Regular Guardrail Starvation Audit

- Generated: `2026-06-12T17:07:53Z`
- Status: `guardrail_starvation_detected`
- Playbooks completed/requested: `14` / `14`
- Candidate/returned totals: `2` / `2`
- Candidate guardrail decisions: `{'blocked': 2}`
- Starvation playbooks: `['ai_commodity_infra_observation']`
- Zero-candidate playbooks: `13`
- Market open at run: `True`
- All configured ticker scopes audited: `True`
- Commodity playbooks included: `True`

## Leading Upstream Drops

- `momentum`: `122`
- `direction_filter`: `97`
- `option_liquidity`: `73`
- `history_or_liquidity`: `55`
- `tech_score`: `49`
- `ev_floor`: `4`
- `min_history`: `0`
- `signal_index`: `0`

## Leading Drop Details

- `momentum`: `76` - momentum/trend signal not met (`ABBV, AMD, AMT, ARM, DIA, DIS, FCX, IWM`)
- `direction_filter`: `65` - put not in allowed directions call (`AA, AAPL, AMZN, COIN, COP, CVX, GOOGL, META`)
- `history_or_liquidity`: `54` - underlying history/liquidity gate; tier=thin (`CAT, CLF, COST, DE, EQR, GS, LIN, LMT`)
- `momentum`: `46` - close > SMA50, ret20 > 2%, and -4% < ret5 < 0.25% (`AA, AAPL, AMD, AMZN, ARM, BA, BAC, C`)
- `option_liquidity`: `42` - illiquid_quote: wide_leg_spread (`BAC, C, JNJ, JPM, KO, RTX, UNH, AMZN`)
- `direction_filter`: `32` - call not in allowed directions put (`BA, BAC, C, JNJ, JPM, KO, LLY, MCD`)
- `option_liquidity`: `12` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage (`PG, SBUX, JNJ, JPM, RTX, CVX, CARR, GEV`)
- `option_liquidity`: `7` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_volume (`PLD, WELL, LLY, AMT`)

## Interpretation

- Inspect blocked candidate rows before loosening promoted profitability guardrails.
