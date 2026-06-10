# Regular Guardrail Starvation Audit

- Generated: `2026-06-10T17:09:40Z`
- Status: `guardrail_starvation_detected`
- Playbooks completed/requested: `14` / `14`
- Candidate/returned totals: `1` / `1`
- Candidate guardrail decisions: `{'blocked': 1}`
- Starvation playbooks: `['ai_commodity_infra_observation']`
- Zero-candidate playbooks: `13`
- Market open at run: `True`
- All configured ticker scopes audited: `True`
- Commodity playbooks included: `True`

## Leading Upstream Drops

- `momentum`: `131`
- `direction_filter`: `93`
- `option_liquidity`: `61`
- `history_or_liquidity`: `55`
- `tech_score`: `48`
- `direction_score`: `13`
- `min_history`: `0`
- `signal_index`: `0`

## Leading Drop Details

- `momentum`: `82` - momentum/trend signal not met (`AA, ARM, COP, CVX, DIA, GOOGL, IWM, PFE`)
- `direction_filter`: `63` - put not in allowed directions call (`AAPL, AMD, AMZN, BA, COIN, DIS, FCX, META`)
- `history_or_liquidity`: `54` - underlying history/liquidity gate; tier=thin (`CAT, CLF, COST, DE, EQR, GS, LIN, LMT`)
- `momentum`: `49` - close > SMA50, ret20 > 2%, and -4% < ret5 < 0.25% (`AA, AAPL, ABBV, AMD, AMT, AMZN, ARM, BA`)
- `direction_filter`: `30` - call not in allowed directions put (`ABBV, AMT, BAC, C, JNJ, JPM, KO, LLY`)
- `option_liquidity`: `19` - illiquid_quote: wide_leg_spread (`C, JNJ, KO, PG, BA, COIN, MSTR, NFLX`)
- `option_liquidity`: `9` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_volume (`AMT, PG, ABBV, JNJ, COIN, T`)
- `option_liquidity`: `9` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_open_interest (`AMZN, META, ALB, CARR, GEV, NRG, SCCO, URA`)

## Interpretation

- Inspect blocked candidate rows before loosening promoted profitability guardrails.
