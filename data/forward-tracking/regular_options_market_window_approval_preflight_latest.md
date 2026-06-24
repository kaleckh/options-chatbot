# Regular Options Market-Window Approval Preflight

Generated: `2026-06-21T20:50:48Z`.

Status: `blocked_market_closed`.

## Safety Boundary

- Read-only: `True`.
- Append allowed: `False`.
- Cohort append performed: `False`.
- Broker/live/auto-track/promotion allowed: `False` / `False` / `False` / `False`.
- Quote import or evidence mutation: `False` / `False`.

## Gate State

- Market-window status: `market_closed`.
- Operator approval granted: `False`.
- Candidate JSONL supplied: `False`.
- Candidate rows valid for future approval review: `False`.
- Candidate rejects: `{}`.

## Current Proof Readback

- Volatility goal-loop state: `log_missing_blocker`.
- Volatility strict rows: `0` / `30`.
- Volatility strict USD PF lower bound: `None`.
- Bullish-pullback layer4 protocol: `protocol_ready_waiting_for_market_window_and_operator_approval`.
- Historical side-aware net/PF/PF-LB: `45610.0` / `3.7414` / `2.27`.
- Historical rows are forward proof: `False`.
- Historical blockers: `{'missing_required_quote_rows': 3, 'zero_or_untradable_rows': 6, 'source_mark_mismatch_rows': 129}`.

## Next Operator Action

wait_for_valid_market_window_then_run_preflight_again
