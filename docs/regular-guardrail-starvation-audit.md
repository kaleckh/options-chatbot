# Regular Guardrail Starvation Audit

- Generated: `2026-06-26T17:04:08Z`
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

- `momentum`: `50`
- `option_liquidity`: `18`
- `history_or_liquidity`: `9`
- `tech_score`: `6`
- `direction_score`: `2`
- `min_history`: `0`
- `signal_index`: `0`
- `direction_filter`: `0`

## Leading Drop Details

- `momentum`: `50` - close > SMA50, ret20 > 2%, and -4% < ret5 < 0.25% (`AA, AAPL, ABBV, AMD, AMT, AMZN, ARM, BA`)
- `option_liquidity`: `10` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_open_interest (`AA, ALB, CCJ, COPX, ETN, MP, SCCO, TT`)
- `history_or_liquidity`: `8` - underlying history/liquidity gate; tier=thin (`CLF, COST, DE, EQR, GS, LIN, LMT, SPG`)
- `option_liquidity`: `4` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_volume,low_leg_open_interest (`RTX, CARR, NRG, TECK`)
- `option_liquidity`: `2` - illiquid_quote: wide_leg_spread (`IWM, BHP`)
- `option_liquidity`: `1` - illiquid_quote: wide_leg_spread,low_leg_volume,low_leg_open_interest (`DIA`)
- `tech_score`: `1` - tech_score 46.9 below 65.0 (`QQQ`)
- `tech_score`: `1` - tech_score 53.4 below 65.0 (`SPY`)

## Interpretation

- Inspect blocked candidate rows before loosening promoted profitability guardrails.
