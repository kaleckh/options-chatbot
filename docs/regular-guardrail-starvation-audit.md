# Regular Guardrail Starvation Audit

- Generated: `2026-06-16T17:04:38Z`
- Status: `guardrail_starvation_detected`
- Playbooks completed/requested: `3` / `3`
- Candidate/returned totals: `5` / `5`
- Candidate guardrail decisions: `{'blocked': 5}`
- Starvation playbooks: `['volatility_expansion_observation', 'ai_commodity_infra_observation']`
- Zero-candidate playbooks: `1`
- Market open at run: `True`
- All configured ticker scopes audited: `True`
- Commodity playbooks included: `True`

## Leading Upstream Drops

- `momentum`: `54`
- `option_liquidity`: `14`
- `history_or_liquidity`: `9`
- `tech_score`: `4`
- `ev_floor`: `1`
- `min_history`: `0`
- `signal_index`: `0`
- `direction_score`: `0`

## Leading Drop Details

- `momentum`: `47` - close > SMA50, ret20 > 2%, and -4% < ret5 < 0.25% (`AA, AAPL, AMD, AMZN, ARM, BA, BAC, C`)
- `history_or_liquidity`: `9` - underlying history/liquidity gate; tier=thin (`CAT, CLF, COST, DE, EQR, GS, LIN, LMT`)
- `option_liquidity`: `9` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage (`AMT, CARR, COPX, ETN, NVT, PWR, SCCO, TECK`)
- `momentum`: `7` - momentum/trend signal not met (`CEG, GEV, MP, NRG, SLV, URA, VRT`)
- `option_liquidity`: `3` - illiquid_quote: wide_leg_spread (`ABBV, LLY, BHP`)
- `option_liquidity`: `1` - illiquid_quote: wide_leg_spread,low_leg_volume,low_leg_open_interest (`DIA`)
- `ev_floor`: `1` - {'direction_score': #} (`AA`)
- `tech_score`: `1` - tech_score 51.4 below 65.0 (`ALB`)

## Interpretation

- Inspect blocked candidate rows before loosening promoted profitability guardrails.
