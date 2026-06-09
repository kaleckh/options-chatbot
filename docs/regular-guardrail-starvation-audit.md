# Regular Guardrail Starvation Audit

- Generated: `2026-06-09T17:10:20Z`
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

- `momentum`: `127`
- `direction_filter`: `95`
- `tech_score`: `57`
- `history_or_liquidity`: `55`
- `option_liquidity`: `55`
- `direction_score`: `13`
- `min_history`: `0`
- `signal_index`: `0`

## Leading Drop Details

- `momentum`: `80` - momentum/trend signal not met (`AA, AMD, ARM, DIA, KO, MCD, PFE, PLD`)
- `direction_filter`: `69` - put not in allowed directions call (`AAPL, AMZN, BA, COIN, DIS, FCX, GOOGL, META`)
- `history_or_liquidity`: `54` - underlying history/liquidity gate; tier=thin (`CAT, CLF, COST, DE, EQR, GS, LIN, LMT`)
- `momentum`: `47` - close > SMA50, ret20 > 2%, and -4% < ret5 < 0.25% (`AA, ABBV, AMT, AMZN, ARM, BA, BAC, C`)
- `direction_filter`: `26` - call not in allowed directions put (`ABBV, AMT, BAC, C, COP, CVX, JNJ, JPM`)
- `option_liquidity`: `14` - illiquid_quote: wide_leg_spread (`ABBV, C, JNJ, BA, COIN, MSTR, NFLX, NKE`)
- `option_liquidity`: `11` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage (`JPM, LLY, C, JNJ, DIS, AMD, COIN, MSTR`)
- `option_liquidity`: `9` - illiquid_quote: wide_leg_spread,wide_spread_entry_slippage,low_leg_open_interest (`AMZN, GOOGL, ALB, CCJ, CEG, GEV, MP, SCCO`)

## Interpretation

- Current no-pick state is upstream scanner/data/liquidity pressure, not promoted guardrail starvation.
