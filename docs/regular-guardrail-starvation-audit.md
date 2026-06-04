# Regular Guardrail Starvation Audit

- Generated: `2026-06-04T17:07:02Z`
- Status: `guardrail_starvation_detected`
- Playbooks completed/requested: `14` / `14`
- Candidate/returned totals: `15` / `15`
- Candidate guardrail decisions: `{'blocked': 9, 'clear': 6}`
- Starvation playbooks: `['short_term', 'speculative', 'bullish_momentum', 'tracked_winner_primary', 'quality90_debit55_canary', 'tracked_winner_observation']`
- Zero-candidate playbooks: `5`
- Market open at run: `True`
- All configured ticker scopes audited: `True`
- Commodity playbooks included: `True`

## Leading Upstream Drops

- `direction_filter`: `109`
- `momentum`: `99`
- `option_liquidity`: `92`
- `history_or_liquidity`: `54`
- `tech_score`: `33`
- `min_history`: `0`
- `signal_index`: `0`
- `direction_score`: `0`

## Leading Drop Details

- `direction_filter`: `71` - put not in allowed directions call (`AMZN, BA, COIN, DIS, GOOGL, JNJ, KO, MCD`)
- `momentum`: `56` - momentum/trend signal not met (`AAPL, AMT, DIA, IWM, JPM, LLY, META, NEM`)
- `history_or_liquidity`: `54` - underlying history/liquidity gate; tier=thin (`CAT, CLF, COST, DE, EQR, GS, LIN, LMT`)
- `momentum`: `43` - close > SMA50, ret20 > 2%, and -4% < ret5 < 0.25% (`AA, ABBV, AMD, AMZN, ARM, BA, BAC, C`)
- `option_liquidity`: `42` - illiquid_quote: wide_leg_spread (`AMD, BAC, C, FCX, MSFT, OXY, SLB, SMCI`)
- `direction_filter`: `38` - call not in allowed directions put (`AA, ABBV, AMD, ARM, BAC, C, COP, CVX`)
- `option_liquidity`: `15` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage (`AA, ABBV, SMCI, ARM, FCX, MCD, T, AMT`)
- `option_liquidity`: `10` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_open_interest (`ARM, AA, ALB, CEG, ETN, GEV, MP, SCCO`)

## Interpretation

- Inspect blocked candidate rows before loosening promoted profitability guardrails.
