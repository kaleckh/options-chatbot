# Regular Guardrail Starvation Audit

- Generated: `2026-06-05T18:59:48Z`
- Status: `upstream_zero_candidate_scan_pressure`
- Playbooks completed/requested: `14` / `14`
- Candidate/returned totals: `0` / `0`
- Candidate guardrail decisions: `{}`
- Starvation playbooks: `[]`
- Zero-candidate playbooks: `14`
- Market open at run: `True`
- All configured ticker scopes audited: `True`
- Commodity playbooks included: `True`

## Leading Upstream Drops

- `momentum`: `106`
- `direction_filter`: `102`
- `option_liquidity`: `76`
- `history_or_liquidity`: `55`
- `direction_score`: `36`
- `tech_score`: `27`
- `min_history`: `0`
- `signal_index`: `0`

## Leading Drop Details

- `momentum`: `62` - momentum/trend signal not met (`AAPL, IWM, JNJ, LLY, META, MSFT, NEM, NVDA`)
- `direction_filter`: `59` - put not in allowed directions call (`AMZN, BA, COIN, DIS, GOOGL, KO, MCD, MSTR`)
- `history_or_liquidity`: `54` - underlying history/liquidity gate; tier=thin (`CAT, CLF, COST, DE, EQR, GS, LIN, LMT`)
- `momentum`: `44` - close > SMA50, ret20 > 2%, and -4% < ret5 < 0.25% (`AA, ABBV, AMD, AMT, AMZN, ARM, BA, BAC`)
- `direction_filter`: `43` - call not in allowed directions put (`AA, ABBV, AMD, AMT, ARM, BAC, C, COP`)
- `option_liquidity`: `24` - illiquid_quote: wide_leg_spread (`ABBV, BAC, C, SLB, JPM, AMZN, BA, COIN`)
- `option_liquidity`: `22` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage (`AA, AMT, ARM, JPM, SMCI, ABBV, FCX, PFE`)
- `option_liquidity`: `11` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_open_interest (`LLY, MCD, T, WMT, AA, ALB, CEG, COPX`)

## Interpretation

- Current no-pick state is upstream scanner/data/liquidity pressure, not promoted guardrail starvation.
