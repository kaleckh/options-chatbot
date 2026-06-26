# Regular Guardrail Starvation Audit

- Generated: `2026-06-25T17:06:12Z`
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

- `momentum`: `50`
- `option_liquidity`: `22`
- `history_or_liquidity`: `8`
- `tech_score`: `5`
- `ev_floor`: `1`
- `min_history`: `0`
- `signal_index`: `0`
- `direction_score`: `0`

## Leading Drop Details

- `momentum`: `47` - close > SMA50, ret20 > 2%, and -4% < ret5 < 0.25% (`AA, AAPL, ABBV, AMD, AMT, AMZN, ARM, BA`)
- `history_or_liquidity`: `7` - underlying history/liquidity gate; tier=thin (`COST, DE, EQR, GS, LIN, LMT, SPG`)
- `option_liquidity`: `6` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_open_interest (`AA, ALB, COPX, SCCO, URA, VST`)
- `option_liquidity`: `5` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage (`GEV, MP, TT, VRT, XME`)
- `option_liquidity`: `4` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_volume,low_leg_open_interest (`RTX, CARR, NRG, TECK`)
- `momentum`: `3` - momentum/trend signal not met (`DIA, CEG, NVT`)
- `option_liquidity`: `2` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_volume (`LLY, PG`)
- `option_liquidity`: `2` - illiquid_quote: wide_leg_spread,low_leg_open_interest (`DIA, CCJ`)

## Interpretation

- Inspect blocked candidate rows before loosening promoted profitability guardrails.
