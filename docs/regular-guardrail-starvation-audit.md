# Regular Guardrail Starvation Audit

- Generated: `2026-06-03T17:07:56Z`
- Status: `guardrail_starvation_detected`
- Playbooks completed/requested: `14` / `14`
- Candidate/returned totals: `7` / `7`
- Candidate guardrail decisions: `{'blocked': 3, 'clear': 4}`
- Starvation playbooks: `['speculative', 'ai_commodity_infra_observation']`
- Zero-candidate playbooks: `9`
- Market open at run: `True`
- All configured ticker scopes audited: `True`
- Commodity playbooks included: `True`

## Leading Upstream Drops

- `option_liquidity`: `116`
- `direction_filter`: `114`
- `momentum`: `85`
- `history_or_liquidity`: `60`
- `tech_score`: `20`
- `min_history`: `0`
- `signal_index`: `0`
- `direction_score`: `0`

## Leading Drop Details

- `direction_filter`: `74` - put not in allowed directions call (`AMZN, BA, COIN, DIS, GOOGL, JNJ, JPM, KO`)
- `history_or_liquidity`: `60` - underlying history/liquidity gate; tier=thin (`AMT, CAT, CLF, COST, DE, EQR, GS, LIN`)
- `momentum`: `47` - close > SMA50, ret20 > 2%, and -4% < ret5 < 0.25% (`AA, AAPL, ABBV, AMD, AMZN, ARM, BA, BAC`)
- `option_liquidity`: `41` - illiquid_quote: wide_leg_spread (`AAPL, AMD, BAC, C, FCX, MSFT, NVDA, OXY`)
- `direction_filter`: `40` - call not in allowed directions put (`AA, AAPL, ABBV, AMD, ARM, BAC, C, DIA`)
- `momentum`: `38` - momentum/trend signal not met (`COP, CVX, LLY, SLB, TSLA, UNH, XOM, SQM`)
- `option_liquidity`: `12` - illiquid_quote: wide_leg_spread,low_leg_volume,low_leg_open_interest (`IWM, DIA, XLK, LLY, DIS, JNJ, NEM, RTX`)
- `option_liquidity`: `11` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage (`AA, ARM, AMD, OXY, CEG, COPX, NVT, RIO`)

## Interpretation

- Inspect blocked candidate rows before loosening promoted profitability guardrails.
