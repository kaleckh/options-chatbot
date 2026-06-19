# Regular Guardrail Starvation Audit

- Generated: `2026-06-18T17:05:50Z`
- Status: `guardrail_starvation_detected`
- Playbooks completed/requested: `3` / `3`
- Candidate/returned totals: `1` / `1`
- Candidate guardrail decisions: `{'blocked': 1}`
- Starvation playbooks: `['ai_commodity_infra_observation']`
- Zero-candidate playbooks: `2`
- Market open at run: `True`
- All configured ticker scopes audited: `True`
- Commodity playbooks included: `True`

## Leading Upstream Drops

- `momentum`: `57`
- `option_liquidity`: `11`
- `history_or_liquidity`: `9`
- `ev_floor`: `5`
- `tech_score`: `4`
- `min_history`: `0`
- `signal_index`: `0`
- `direction_score`: `0`

## Leading Drop Details

- `momentum`: `47` - close > SMA50, ret20 > 2%, and -4% < ret5 < 0.25% (`AA, AAPL, AMD, AMZN, ARM, BA, BAC, C`)
- `momentum`: `10` - momentum/trend signal not met (`QQQ, SPY, ALB, CCJ, CEG, MP, RIO, SLV`)
- `history_or_liquidity`: `9` - underlying history/liquidity gate; tier=thin (`AMT, CAT, COST, DE, EQR, GS, LIN, LMT`)
- `ev_floor`: `5` - {'direction_score': #} (`IWM, AA, BHP, ETN, FCX`)
- `option_liquidity`: `5` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage (`CARR, COPX, NVT, SCCO, TECK`)
- `option_liquidity`: `3` - illiquid_quote: wide_leg_spread (`ABBV, LLY, UNH`)
- `option_liquidity`: `2` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_open_interest (`PWR, TT`)
- `option_liquidity`: `1` - illiquid_quote: wide_leg_spread,low_leg_volume,low_leg_open_interest (`DIA`)

## Interpretation

- Inspect blocked candidate rows before loosening promoted profitability guardrails.
