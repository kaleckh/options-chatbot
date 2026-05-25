import unittest

from exact_contract_accounting import (
    contract_resolution_accounting,
    is_exact_contract_resolution,
    split_exact_and_research_trades,
)


class ExactContractAccountingTests(unittest.TestCase):
    def test_exact_resolution_set_is_shared_across_legacy_and_archived_names(self):
        self.assertTrue(is_exact_contract_resolution("exact_contract"))
        self.assertTrue(is_exact_contract_resolution("exact_target_contract"))
        self.assertTrue(is_exact_contract_resolution("exact_archived_contract"))
        self.assertFalse(is_exact_contract_resolution("nearest_listed_contract"))

    def test_accounting_includes_unresolved_candidate_gap(self):
        trades = [
            {"entry_contract_resolution": "exact_target_contract"},
            {"entry_contract_resolution": "exact_archived_contract"},
            {"entry_contract_resolution": "nearest_listed_contract"},
        ]

        accounting = contract_resolution_accounting(
            trades,
            priced_trade_count=3,
            candidate_trade_count=5,
        )
        exact, research = split_exact_and_research_trades(trades)

        self.assertEqual(accounting["exact_contract_match_count"], 2)
        self.assertEqual(accounting["nearest_contract_match_count"], 1)
        self.assertEqual(accounting["unresolved_contract_count"], 2)
        self.assertEqual(len(exact), 2)
        self.assertEqual(len(research), 1)


if __name__ == "__main__":
    unittest.main()
