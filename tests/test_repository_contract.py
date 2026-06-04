import inspect
import sys
import unittest
from pathlib import Path
from typing import get_type_hints


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
CONTRACT_PATH = ROOT / "docs" / "repository-contract.md"
INDEX_PATH = ROOT / "docs" / "index.md"
ARCHITECTURE_PATH = ROOT / "docs" / "architecture-overview.md"
API_STORAGE_PATH = ROOT / "docs" / "api-and-storage.md"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from repository_contracts import (
    SUGGESTED_TRADES_REQUIRED_METHODS,
    TRACKED_POSITIONS_OPTIONAL_METHODS,
    TRACKED_POSITIONS_REQUIRED_METHODS,
    SuggestedTradesRepository,
    SupportsCompactPositionList,
    SupportsProfitStatusSnapshot,
    TrackedPositionsRepository,
    TradingDeskPositionRepository,
)
from positions_repository import (
    MemoryTrackedPositionsRepository,
    PostgresTrackedPositionsRepository,
    SqliteTrackedPositionsRepository,
    UnavailableTrackedPositionsRepository,
    create_positions_repository,
)
from suggested_trades_repository import (
    SQLiteSuggestedTradesRepository,
    create_suggested_trades_repository,
)


class RepositoryContractTests(unittest.TestCase):
    def test_repository_contract_doc_names_owners_and_living_links(self):
        doc = CONTRACT_PATH.read_text(encoding="utf-8")
        for expected in (
            "PostgresTrackedPositionsRepository",
            "UnavailableTrackedPositionsRepository",
            "MemoryTrackedPositionsRepository",
            "SqliteTrackedPositionsRepository",
            "SQLiteSuggestedTradesRepository",
            "python-backend/repository_contracts.py",
            "profit_status_snapshot()",
            "Do not add a silent tracked-position SQLite fallback",
        ):
            self.assertIn(expected, doc)

        self.assertIn("docs/repository-contract.md", INDEX_PATH.read_text(encoding="utf-8"))
        self.assertIn("docs/repository-contract.md", ARCHITECTURE_PATH.read_text(encoding="utf-8"))
        self.assertIn("docs/repository-contract.md", API_STORAGE_PATH.read_text(encoding="utf-8"))

    def test_tracked_repositories_satisfy_required_protocol(self):
        repositories = [
            UnavailableTrackedPositionsRepository("tracked unavailable"),
            MemoryTrackedPositionsRepository(),
            SqliteTrackedPositionsRepository(":memory:"),
            PostgresTrackedPositionsRepository("postgresql://example/test"),
        ]
        for repository in repositories:
            with self.subTest(repository=type(repository).__name__):
                self.assertIsInstance(repository, TradingDeskPositionRepository)
                self.assertIsInstance(repository, TrackedPositionsRepository)
                for method in TRACKED_POSITIONS_REQUIRED_METHODS:
                    self.assertTrue(callable(getattr(repository, method, None)), method)

    def test_suggested_repository_satisfies_shared_protocol_without_tracked_capabilities(self):
        repository = SQLiteSuggestedTradesRepository(":memory:")

        self.assertIsInstance(repository, TradingDeskPositionRepository)
        self.assertIsInstance(repository, SuggestedTradesRepository)
        self.assertNotIsInstance(repository, TrackedPositionsRepository)
        for method in SUGGESTED_TRADES_REQUIRED_METHODS:
            self.assertTrue(callable(getattr(repository, method, None)), method)
        self.assertFalse(hasattr(repository, "profit_status_snapshot"))
        self.assertFalse(hasattr(repository, "list_compact_positions"))
        self.assertFalse(hasattr(repository, "update_position"))

    def test_optional_tracked_capabilities_are_separate_from_required_unavailable_surface(self):
        for repository in (
            MemoryTrackedPositionsRepository(),
            SqliteTrackedPositionsRepository(":memory:"),
            PostgresTrackedPositionsRepository("postgresql://example/test"),
        ):
            with self.subTest(repository=type(repository).__name__):
                for method in TRACKED_POSITIONS_OPTIONAL_METHODS:
                    self.assertTrue(callable(getattr(repository, method, None)), method)
                self.assertIsInstance(repository, SupportsCompactPositionList)
                self.assertIsInstance(repository, SupportsProfitStatusSnapshot)

        unavailable = UnavailableTrackedPositionsRepository("tracked unavailable")
        for method in TRACKED_POSITIONS_OPTIONAL_METHODS:
            self.assertFalse(hasattr(unavailable, method), method)

    def test_factory_return_annotations_name_repository_protocols(self):
        self.assertIs(
            get_type_hints(create_positions_repository)["return"],
            TrackedPositionsRepository,
        )
        self.assertIs(
            get_type_hints(create_suggested_trades_repository)["return"],
            SuggestedTradesRepository,
        )

    def test_missing_database_url_returns_unavailable_tracked_repository_contract(self):
        repository = create_positions_repository(None)

        self.assertIsInstance(repository, UnavailableTrackedPositionsRepository)
        self.assertIsInstance(repository, TrackedPositionsRepository)
        self.assertFalse(repository.is_available)
        self.assertIn("DATABASE_URL", repository.error_message)
        self.assertIn("Postgres", repository.error_message)

    def test_position_repository_signature_contracts_remain_stable(self):
        list_signature = inspect.signature(MemoryTrackedPositionsRepository.list_positions)
        self.assertEqual(list_signature.parameters["status"].default, "open")
        self.assertEqual(list_signature.parameters["limit"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(list_signature.parameters["limit"].default, None)
        self.assertEqual(list_signature.parameters["offset"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(list_signature.parameters["offset"].default, 0)

        close_signature = inspect.signature(MemoryTrackedPositionsRepository.close_position)
        self.assertEqual(close_signature.parameters["exit_execution_basis"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(close_signature.parameters["exit_execution_basis"].default, "manual_close")
        self.assertEqual(close_signature.parameters["allow_zero_exit_price"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(close_signature.parameters["allow_zero_exit_price"].default, False)


if __name__ == "__main__":
    unittest.main()
