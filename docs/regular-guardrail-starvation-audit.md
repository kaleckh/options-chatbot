# Regular Guardrail Starvation Audit

- Generated: `2026-06-24T17:05:50Z`
- Status: `guardrail_starvation_detected`
- Playbooks completed/requested: `3` / `3`
- Candidate/returned totals: `2` / `2`
- Candidate guardrail decisions: `{'blocked': 2}`
- Starvation playbooks: `['ai_commodity_infra_observation']`
- Zero-candidate playbooks: `2`
- Market open at run: `True`
- All configured ticker scopes audited: `True`
- Commodity playbooks included: `True`

## Leading Upstream Drops

- `momentum`: `54`
- `option_liquidity`: `15`
- `tech_score`: `9`
- `history_or_liquidity`: `7`
- `min_history`: `0`
- `signal_index`: `0`
- `direction_score`: `0`
- `direction_filter`: `0`

## Leading Drop Details

- `momentum`: `47` - close > SMA50, ret20 > 2%, and -4% < ret5 < 0.25% (`AA, AAPL, ABBV, AMD, AMT, AMZN, ARM, BA`)
- `option_liquidity`: `8` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_open_interest (`AA, ALB, COPX, GEV, SCCO, TECK, URA, XME`)
- `history_or_liquidity`: `7` - underlying history/liquidity gate; tier=thin (`COST, DE, EQR, GS, LIN, LMT, SPG`)
- `momentum`: `7` - momentum/trend signal not met (`DIA, IWM, CARR, ETN, MP, NVT, TT`)
- `option_liquidity`: `2` - illiquid_quote: wide_leg_spread,low_leg_volume (`IWM, UNH`)
- `option_liquidity`: `2` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_volume,low_leg_open_interest (`LLY, XLK`)
- `option_liquidity`: `2` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage (`SQM, VST`)
- `option_liquidity`: `1` - illiquid_quote: wide_leg_spread,low_leg_volume,low_leg_open_interest (`DIA`)

## Interpretation

- Inspect blocked candidate rows before loosening promoted profitability guardrails.
