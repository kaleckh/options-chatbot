from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "replay-profit-contract.md"
INDEX_PATH = ROOT / "docs" / "index.md"
ARCHITECTURE_PATH = ROOT / "docs" / "architecture-overview.md"
API_STORAGE_PATH = ROOT / "docs" / "api-and-storage.md"
SERVICE_PATH = ROOT / "python-backend" / "replay_profit_service.py"


class ReplayProfitContractTests(unittest.TestCase):
    def test_replay_profit_contract_names_owners_and_boundaries(self):
        doc = CONTRACT_PATH.read_text(encoding="utf-8")
        for expected in (
            "wfo_optimizer.run_historical_backtest",
            "python-backend/replay_profit_service.py",
            "metric_truth_audit.py",
            "options_profitability_forensics.py",
            "wfo_optimizer.build_live_options_trade_policy",
            "options_profit_gate.py",
            "options_profit_state.py",
            "options_profit_flywheel.py",
            "docs/proof-evidence-contract.md",
            "docs/scanner-creation-safety-contract.md",
            "GET /api/options-profit/status",
        ):
            self.assertIn(expected, doc)
        self.assertIn("must not import canonical `main.py`", doc)
        self.assertIn("Do not let options-profit status become a proof owner", doc)

    def test_replay_profit_contract_is_linked_from_living_docs(self):
        self.assertIn("docs/replay-profit-contract.md", INDEX_PATH.read_text(encoding="utf-8"))
        self.assertIn("docs/replay-profit-contract.md", ARCHITECTURE_PATH.read_text(encoding="utf-8"))
        self.assertIn("docs/replay-profit-contract.md", API_STORAGE_PATH.read_text(encoding="utf-8"))

    def test_replay_profit_service_declares_expected_readback_functions(self):
        service = SERVICE_PATH.read_text(encoding="utf-8")
        for expected in (
            "def cached_backtest_report",
            "def cached_metric_truth_report",
            "def cached_backtest_experiments",
            "def cached_backtest_profitability_forensics",
            "def cached_backtest_stability",
            "def cached_live_trade_policy_report",
            "def cached_playbook_exit_audit_report",
            "def cached_truth_lane_comparison_report",
            "def build_backtest_summary",
        ):
            self.assertIn(expected, service)


if __name__ == "__main__":
    unittest.main()
