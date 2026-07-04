# Regular Guardrail Starvation Audit

- Generated: `2026-07-02T17:10:15Z`
- Status: `upstream_zero_candidate_scan_pressure`
- Playbooks completed/requested: `3` / `3`
- Candidate/returned totals: `0` / `0`
- Candidate guardrail decisions: `{}`
- Starvation playbooks: `[]`
- Zero-candidate playbooks: `3`
- Market open at run: `True`
- All configured ticker scopes audited: `True`
- Commodity playbooks included: `True`

## Leading Upstream Drops

- `momentum`: `51`
- `option_liquidity`: `25`
- `history_or_liquidity`: `9`
- `tech_score`: `2`
- `min_history`: `0`
- `signal_index`: `0`
- `direction_score`: `0`
- `direction_filter`: `0`

## Leading Drop Details

- `momentum`: `45` - close > SMA50, ret20 > 2%, and -4% < ret5 < 0.25% (`AA, AAPL, ABBV, AMD, AMT, AMZN, ARM, BA`)
- `history_or_liquidity`: `9` - underlying history/liquidity gate; tier=thin (`CLF, COST, DE, EQR, GS, LIN, LMT, SPG`)
- `option_liquidity`: `7` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_open_interest (`AA, ALB, COPX, ETN, MP, SCCO, URA`)
- `option_liquidity`: `6` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage (`PG, FCX, NVT, PWR, VRT, XME`)
- `momentum`: `6` - momentum/trend signal not met (`BHP, CARR, NRG, SLV, TECK, TT`)
- `option_liquidity`: `3` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_volume,low_leg_open_interest (`CAT, PM, SBUX`)
- `option_liquidity`: `3` - illiquid_quote: wide_leg_spread,low_leg_open_interest (`C, QQQ, CCJ`)
- `option_liquidity`: `3` - illiquid_quote: wide_leg_spread (`JPM, CEG, RIO`)

## Interpretation

- Current no-pick state is upstream scanner/data/liquidity pressure, not promoted guardrail starvation.
