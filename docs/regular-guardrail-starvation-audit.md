# Regular Guardrail Starvation Audit

- Generated: `2026-07-10T17:03:02Z`
- Status: `guardrail_starvation_detected`
- Playbooks completed/requested: `3` / `3`
- Candidate/returned totals: `1` / `1`
- Candidate guardrail decisions: `{'blocked': 1}`
- Starvation playbooks: `['volatility_expansion_observation']`
- Zero-candidate playbooks: `2`
- Market open at run: `True`
- All configured ticker scopes audited: `True`
- Commodity playbooks included: `True`

## Leading Upstream Drops

- `momentum`: `56`
- `option_liquidity`: `14`
- `history_or_liquidity`: `9`
- `tech_score`: `5`
- `direction_score`: `2`
- `min_history`: `0`
- `signal_index`: `0`
- `direction_filter`: `0`

## Leading Drop Details

- `momentum`: `45` - close > SMA50, ret20 > 2%, and -4% < ret5 < 0.25% (`AA, AAPL, AMD, AMT, AMZN, ARM, BA, BAC`)
- `momentum`: `11` - momentum/trend signal not met (`IWM, QQQ, AA, CEG, COPX, FCX, GEV, NRG`)
- `history_or_liquidity`: `8` - underlying history/liquidity gate; tier=thin (`CLF, COST, DE, EQR, GS, LIN, LMT, SPG`)
- `option_liquidity`: `4` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_volume,low_leg_open_interest (`ABBV, C, XLK, ALB`)
- `option_liquidity`: `3` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_open_interest (`MP, URA, VST`)
- `option_liquidity`: `2` - illiquid_quote: wide_leg_spread,low_leg_volume,low_leg_open_interest (`IWM, V`)
- `option_liquidity`: `2` - illiquid_quote: wide_leg_spread,low_leg_open_interest (`QQQ, DIA`)
- `option_liquidity`: `2` - illiquid_quote: wide_leg_spread (`BHP, RIO`)

## Interpretation

- Inspect blocked candidate rows before loosening promoted profitability guardrails.
