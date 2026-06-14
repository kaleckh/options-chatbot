from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.scan_heartbeat import (
    build_scan_heartbeat_health,
    market_days_since,
    write_scan_heartbeat,
)


class ScanHeartbeatTests(unittest.TestCase):
    def test_market_days_since_counts_only_market_days_after_last_run(self) -> None:
        days = market_days_since(
            "2026-06-05T18:00:00Z",
            as_of_utc="2026-06-10T18:00:00Z",
        )
        self.assertEqual(days, 3)

    def test_health_fails_when_heartbeat_is_missing_or_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "heartbeat.json"

            missing = build_scan_heartbeat_health(
                heartbeat_path=heartbeat,
                as_of_utc="2026-06-10T18:00:00Z",
            )
            self.assertEqual(missing["state"], "fail")
            self.assertEqual(missing["status"], "missing")

            write_scan_heartbeat(
                status="completed",
                heartbeat_path=heartbeat,
                run_completed_at_utc="2026-06-05T18:00:00Z",
                scan_date="2026-06-05",
                provenance={
                    "host": "KaesDevice",
                    "commit_sha": "abcdef123456",
                    "short_commit_sha": "abcdef123456",
                    "branch": "main",
                    "run_id": "scheduled_scan:test",
                },
            )
            stale = build_scan_heartbeat_health(
                heartbeat_path=heartbeat,
                as_of_utc="2026-06-10T18:00:00Z",
            )
            self.assertEqual(stale["state"], "fail")
            self.assertEqual(stale["status"], "stale")
            self.assertEqual(stale["days_since_last_scheduled_scan"], 3)

    def test_recent_heartbeat_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "heartbeat.json"
            write_scan_heartbeat(
                status="completed",
                heartbeat_path=heartbeat,
                run_completed_at_utc="2026-06-09T18:00:00Z",
                scan_date="2026-06-09",
                provenance={
                    "host": "KaesDevice",
                    "commit_sha": "abcdef123456",
                    "short_commit_sha": "abcdef123456",
                    "branch": "main",
                    "run_id": "scheduled_scan:test",
                },
            )

            health = build_scan_heartbeat_health(
                heartbeat_path=heartbeat,
                as_of_utc="2026-06-10T18:00:00Z",
            )

        self.assertEqual(health["state"], "pass")
        self.assertEqual(health["status"], "fresh")
        self.assertEqual(health["days_since_last_scheduled_scan"], 1)


if __name__ == "__main__":
    unittest.main()
