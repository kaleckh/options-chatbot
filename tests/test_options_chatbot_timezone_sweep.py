from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OptionsChatbotTimezoneSweepTests(unittest.TestCase):
    def test_options_chatbot_has_no_naive_datetime_now_calls(self) -> None:
        source = (ROOT / "options_chatbot.py").read_text(encoding="utf8")
        matches = [
            f"{line_no}: {line.strip()}"
            for line_no, line in enumerate(source.splitlines(), start=1)
            if re.search(r"\bdatetime\.now\(\s*\)", line)
        ]
        self.assertEqual(
            [],
            matches,
            "Use datetime.now(_ET) or datetime.now(timezone.utc) by intent in options_chatbot.py.",
        )
