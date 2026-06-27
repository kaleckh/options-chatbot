# Regular Options Strict Forward 30 Exit Evidence Plan

Status: `exit_evidence_plan_waiting_for_open_forward_rows`.

- Open forward entries: `0`.
- Pending exit-evidence rows: `0`.
- Open rows with existing evidence: `0`.
- Exit evidence path: `data/forward-tracking/phase2_regular_options_forward_paper_shadow_exit_evidence.jsonl`.
- Required fields: `["selection_id", "exit_quote_source", "exit_quote_timestamp_utc", "exit_bid", "exit_ask", "policy_exit_condition", "net_pnl_usd"]`.

This plan is read-only. It lists exact-exit evidence requirements for already-open Phase 2 forward rows and does not write evidence, append cohort rows, import quotes, enable live validation, auto-track positions, submit broker orders, lower proof bars, or count historical rows as forward proof.

