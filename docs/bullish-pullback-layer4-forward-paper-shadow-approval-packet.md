# Bullish-Pullback Layer4 Forward Paper-Shadow Approval Packet

This packet is informational until a future valid market-data window. It does not approve appending rows by itself.

Approval, if later granted, is limited to append-only full-denominator paper-shadow candidate rows for:

- lane: `bullish_pullback_observation`
- layer: `layer_4_clean_exact`
- variant: `sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1`
- allowed symbols: `["IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"]`

Any future approval must still forbid broker orders, live validation, auto-track, quote import, historical repair, scanner/strategy/stop/sizing/proof-bar changes, protected-holdout consumption, evidence-store mutation outside the approved append path, and promotion.

Before approval, candidate rows must pass the read-only validator and report `cohort_append_performed=false`.
