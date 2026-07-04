# Regular Options Filtered Forward Exit Evidence Capture

- Status: `exit_completion_appended`.
- Open candidates: `1`.
- Completion rows ready: `1`.
- Completion rows appended: `1`.
- Latest completed market day: `2026-06-05`.
- Reject counts: `{}`.

This script appends completion events only to the filtered forward matched-row log. It reads trusted quote stores in read-only mode and never imports quotes, submits orders, creates tracked positions, or changes scanner policy.
