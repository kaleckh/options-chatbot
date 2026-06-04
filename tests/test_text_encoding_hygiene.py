from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {".py", ".md", ".ts", ".tsx", ".js", ".json"}
RECURSIVE_SCAN_ROOTS = (
    ROOT / "python-backend",
    ROOT / "scripts",
    ROOT / "src",
    ROOT / "tests",
    ROOT / "docs",
    ROOT / "data" / "contracts",
)
SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
}
MOJIBAKE_MARKERS = {
    "\ufffd": "unicode replacement character",
    "\u00ef\u00bf\u00bd": "mojibake spelling of replacement character",
    "\u00e2\u0080": "misdecoded UTF-8 punctuation prefix",
    "\u00e2\u0094": "misdecoded UTF-8 box-drawing prefix",
    "\u00e2\u009d": "misdecoded UTF-8 symbol prefix",
    "\u00c3\u00a2": "double-encoded UTF-8 prefix",
    "\u00c3\u0083": "double-encoded UTF-8 prefix",
}


def _active_text_files() -> list[Path]:
    files = [
        path
        for path in ROOT.iterdir()
        if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS
    ]
    for root in RECURSIVE_SCAN_ROOTS:
        if not root.exists():
            continue
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS
        )
    return sorted(set(files))


class TextEncodingHygieneTests(unittest.TestCase):
    def test_active_source_docs_and_contracts_do_not_contain_mojibake(self):
        findings: list[str] = []
        for path in _active_text_files():
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                findings.append(f"{path.relative_to(ROOT)}: not valid UTF-8 ({exc})")
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                for marker, label in MOJIBAKE_MARKERS.items():
                    if marker in line:
                        findings.append(
                            f"{path.relative_to(ROOT)}:{line_number}: {label}"
                        )

        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
