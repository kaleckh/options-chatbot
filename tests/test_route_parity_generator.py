import unittest
from unittest.mock import patch

from scripts import generate_route_parity as route_parity


class RouteParityGeneratorTests(unittest.TestCase):
    def test_generated_route_inventory_artifacts_are_current(self):
        routes = route_parity.load_next_routes()
        backend_routes = route_parity.load_fastapi_routes()
        client_fetches = route_parity.load_client_fetches()
        inventory = route_parity.build_inventory(routes, backend_routes, client_fetches)

        self.assertEqual(
            route_parity.OUTPUT_PATH.read_text(encoding="utf-8"),
            route_parity.render(routes, backend_routes, client_fetches),
        )
        self.assertEqual(
            route_parity.JSON_OUTPUT_PATH.read_text(encoding="utf-8"),
            route_parity.render_inventory_json(inventory),
        )

    def test_extract_client_fetch_paths_normalizes_queries_and_template_segments(self):
        source = """
        fetch("/api/profile?type=equity");
        fetchWithTimeout(`/api/positions/${closingPosition.id}/close`, { method: "POST" });
        fetch("http://localhost:8100/api/health");
        fetch("/not-api");
        fetch(input);
        """

        self.assertEqual(
            route_parity.extract_client_fetch_paths(source),
            ["/api/profile", "/api/positions/[param]/close", "/api/health"],
        )

    def test_dynamic_client_fetch_matches_next_dynamic_route(self):
        self.assertTrue(
            route_parity._route_pattern_matches(
                "/api/positions/[id]/close",
                "/api/positions/[param]/close",
            )
        )
        self.assertFalse(
            route_parity._route_pattern_matches(
                "/api/positions/[id]/close",
                "/api/positions/review",
            )
        )

    def test_validation_errors_flag_client_fetches_without_mounted_next_routes(self):
        errors = route_parity._validation_errors(
            routes=[
                route_parity.NextRoute(
                    method="GET",
                    browser_path="/api/profile",
                    next_path="src/app/api/profile/route.ts",
                    fastapi_path="/api/profile",
                )
            ],
            backend_routes=[route_parity.FastApiRoute(method="GET", path="/api/profile")],
            client_fetches=[
                route_parity.ClientFetch(
                    source_path="src/components/example.tsx",
                    browser_path="/api/backend-only",
                )
            ],
        )

        self.assertEqual(
            errors,
            ["Client fetch has no matching Next route: /api/backend-only from src/components/example.tsx"],
        )

    def test_validation_errors_flag_absolute_api_fetches_that_bypass_next_routes(self):
        errors = route_parity._validation_errors(
            routes=[
                route_parity.NextRoute(
                    method="GET",
                    browser_path="/api/profile",
                    next_path="src/app/api/profile/route.ts",
                    fastapi_path="/api/profile",
                )
            ],
            backend_routes=[route_parity.FastApiRoute(method="GET", path="/api/profile")],
            client_fetches=[
                route_parity.ClientFetch(
                    source_path="src/components/example.tsx",
                    browser_path="/api/profile",
                    absolute_url=True,
                )
            ],
        )

        self.assertEqual(
            errors,
            ["Client fetch must use a relative Next route, not an absolute API URL: /api/profile from src/components/example.tsx"],
        )

    def test_next_only_operator_session_route_is_not_a_missing_fastapi_error(self):
        routes = [
            route_parity.NextRoute(
                method="POST",
                browser_path="/api/operator/session",
                next_path="src/app/api/operator/session/route.ts",
                fastapi_path="/api/operator/session",
            )
        ]

        self.assertEqual(route_parity._validation_errors(routes, [], []), [])
        rendered = route_parity.render(routes, [], [])
        self.assertIn("Next-only: local operator session unlock", rendered)

    def test_next_route_classification_extracts_auth_intent_and_store_contract(self):
        contracts = route_parity.load_route_contract_metadata()
        route = route_parity.NextRoute(
            method="POST",
            browser_path="/api/positions",
            next_path="src/app/api/positions/route.ts",
            fastapi_path="/api/positions",
        )

        contract = route_parity.classify_next_route(route, contracts)

        self.assertEqual(contract.auth_boundary, "local_operator")
        self.assertEqual(contract.intent, "x-trading-desk-mutation: create_tracked_position")
        self.assertEqual(contract.contract_id, "tracked_positions_create")
        self.assertEqual(contract.store, "postgres_tracked_positions")
        self.assertEqual(contract.lifecycle, "create")

    def test_next_route_classification_extracts_generic_route_lifecycle_contract(self):
        contracts = route_parity.load_route_contract_metadata()
        route = route_parity.NextRoute(
            method="POST",
            browser_path="/api/scan",
            next_path="src/app/api/scan/route.ts",
            fastapi_path="/api/scan",
        )

        contract = route_parity.classify_next_route(route, contracts)

        self.assertEqual(contract.auth_boundary, "local_operator")
        self.assertEqual(contract.intent, "none")
        self.assertEqual(contract.contract_id, "scan_run")
        self.assertEqual(contract.store, "forward_evidence_artifacts")
        self.assertEqual(contract.lifecycle, "live_scan_run")
        self.assertEqual(contract.record_class, "scan_result")

    def test_validation_errors_flag_mutating_next_routes_without_operator_auth(self):
        source = """
        export async function POST(req) {
            return jsonWithRouteLifecycle({ ok: true }, "scan_run");
        }
        """
        with patch.object(route_parity, "_read_route_source", return_value=source):
            errors = route_parity._validation_errors(
                routes=[
                    route_parity.NextRoute(
                        method="POST",
                        browser_path="/api/scan",
                        next_path="src/app/api/scan/route.ts",
                        fastapi_path="/api/scan",
                    )
                ],
                backend_routes=[
                    route_parity.FastApiRoute(method="POST", path="/api/scan"),
                ],
                client_fetches=[],
            )

        self.assertEqual(
            errors,
            [
                "Mutating Next route must require local operator auth: POST /api/scan from src/app/api/scan/route.ts",
            ],
        )

    def test_validation_errors_flag_authenticated_mutating_next_routes_without_contract(self):
        source = """
        export async function POST(req) {
            const guard = requireLocalOperator(req);
            if (guard) return guard;
            return Response.json({ ok: true });
        }
        """
        with patch.object(route_parity, "_read_route_source", return_value=source):
            errors = route_parity._validation_errors(
                routes=[
                    route_parity.NextRoute(
                        method="POST",
                        browser_path="/api/test-mutation",
                        next_path="src/app/api/test-mutation/route.ts",
                        fastapi_path="/api/test-mutation",
                    )
                ],
                backend_routes=[
                    route_parity.FastApiRoute(method="POST", path="/api/test-mutation"),
                ],
                client_fetches=[],
            )

        self.assertEqual(
            errors,
            [
                "Mutating Next route must declare a route lifecycle/store contract: POST /api/test-mutation from src/app/api/test-mutation/route.ts",
            ],
        )

    def test_validation_errors_flag_unknown_or_mismatched_mutation_contracts(self):
        unknown_source = """
        export async function POST(req) {
            const guard = requireLocalOperator(req);
            if (guard) return guard;
            return jsonWithRouteLifecycle({ ok: true }, "missing_contract");
        }
        """
        with patch.object(route_parity, "_read_route_source", return_value=unknown_source):
            unknown_errors = route_parity._validation_errors(
                routes=[
                    route_parity.NextRoute(
                        method="POST",
                        browser_path="/api/test-mutation",
                        next_path="src/app/api/test-mutation/route.ts",
                        fastapi_path="/api/test-mutation",
                    )
                ],
                backend_routes=[
                    route_parity.FastApiRoute(method="POST", path="/api/test-mutation"),
                ],
                client_fetches=[],
            )

        self.assertIn(
            "Route references unknown route contract: POST /api/test-mutation uses missing_contract from src/app/api/test-mutation/route.ts",
            unknown_errors,
        )

        mismatched_source = """
        export async function POST(req) {
            const guard = requireLocalOperator(req);
            if (guard) return guard;
            return jsonWithRouteLifecycle({ ok: true }, "predictions_read");
        }
        """
        with patch.object(route_parity, "_read_route_source", return_value=mismatched_source):
            mismatch_errors = route_parity._validation_errors(
                routes=[
                    route_parity.NextRoute(
                        method="POST",
                        browser_path="/api/predictions/grade",
                        next_path="src/app/api/predictions/grade/route.ts",
                        fastapi_path="/api/predictions/grade",
                    )
                ],
                backend_routes=[
                    route_parity.FastApiRoute(method="POST", path="/api/predictions/grade"),
                ],
                client_fetches=[],
            )

        self.assertIn(
            "Route method and contract disagree: POST /api/predictions/grade uses predictions_read declared as GET",
            mismatch_errors,
        )
        self.assertIn(
            "Route path and contract disagree: POST /api/predictions/grade uses predictions_read declared for /api/predictions",
            mismatch_errors,
        )

    def test_validation_errors_flag_backend_only_mutation_without_lifecycle_override(self):
        errors = route_parity._validation_errors(
            routes=[],
            backend_routes=[
                route_parity.FastApiRoute(method="POST", path="/api/backend-mutation"),
            ],
            client_fetches=[],
        )

        self.assertEqual(
            errors,
            ["Backend-only mutating route must declare a lifecycle override: POST /api/backend-mutation"],
        )

    def test_render_includes_route_auth_and_backend_only_inventory(self):
        routes = [
            route_parity.NextRoute(
                method="POST",
                browser_path="/api/scan",
                next_path="src/app/api/scan/route.ts",
                fastapi_path="/api/scan",
            )
        ]
        backend_routes = [
            route_parity.FastApiRoute(method="POST", path="/api/scan"),
            route_parity.FastApiRoute(method="POST", path="/api/market-data/cache-stats/reset"),
        ]

        rendered = route_parity.render(routes, backend_routes, [])

        self.assertIn("## Route Auth And Mutation Inventory", rendered)
        self.assertIn("| POST /api/scan | live_scan_run | local_operator | none | scan_run | forward_evidence_artifacts | python-backend/main.py /api/scan and forward_options_ledger.py |", rendered)
        self.assertIn("## Backend-Only Auth And Mutation Inventory", rendered)
        self.assertIn("| POST /api/market-data/cache-stats/reset | market_data_cache_reset | backend_bridge_token_when_configured | backend_only | backend/domain | python-backend |", rendered)

    def test_json_inventory_exposes_route_mutation_contracts(self):
        routes = route_parity.load_next_routes()
        backend_routes = route_parity.load_fastapi_routes()
        inventory = route_parity.build_inventory(routes, backend_routes, route_parity.load_client_fetches())
        browser_routes = {
            (route["method"], route["browser_path"]): route
            for route in inventory["mounted_browser_routes"]
        }
        backend_only_routes = {
            (route["method"], route["path"]): route
            for route in inventory["backend_only_routes"]
        }

        self.assertEqual(inventory["artifact"], "route_mutation_inventory")
        self.assertFalse(inventory["runtime_use"])
        self.assertEqual(len(browser_routes), len(routes))
        self.assertEqual(
            inventory["sources"]["client_fetch_roots"],
            [root.relative_to(route_parity.ROOT).as_posix() for root in route_parity.CLIENT_FETCH_ROOTS],
        )

        tracked_create = browser_routes[("POST", "/api/positions")]
        self.assertTrue(tracked_create["mutating"])
        self.assertEqual(tracked_create["auth_boundary"], "local_operator")
        self.assertEqual(tracked_create["lifecycle"], "create")
        self.assertEqual(tracked_create["intent_labels"], ["x-trading-desk-mutation: create_tracked_position"])
        self.assertEqual(tracked_create["contract_ids"], ["tracked_positions_create"])
        self.assertEqual(tracked_create["stores"], ["postgres_tracked_positions"])

        profile_save = browser_routes[("PUT", "/api/profile")]
        self.assertEqual(profile_save["intent_labels"], ["x-strategy-lab-mutation: save_strategy_profile"])
        self.assertEqual(profile_save["stores"], ["strategy_profile_files"])

        scan = browser_routes[("POST", "/api/scan")]
        self.assertEqual(scan["intent_labels"], [])
        self.assertEqual(scan["contract_ids"], ["scan_run"])
        self.assertEqual(scan["stores"], ["forward_evidence_artifacts"])
        self.assertEqual(scan["lifecycle"], "live_scan_run")

        operator_unlock = browser_routes[("POST", "/api/operator/session")]
        self.assertTrue(operator_unlock["next_only"])
        self.assertEqual(operator_unlock["auth_boundary"], "next_only_session")

        cache_reset = backend_only_routes[("POST", "/api/market-data/cache-stats/reset")]
        self.assertTrue(cache_reset["mutating"])
        self.assertEqual(cache_reset["auth_boundary"], "backend_bridge_token_when_configured")
        self.assertEqual(cache_reset["lifecycle"], "market_data_cache_reset")

        self.assertEqual(inventory["validation"]["errors"], [])
        self.assertTrue(any(fetch["browser_path"] == "/api/scan" for fetch in inventory["client_fetches"]))
        for route in inventory["mounted_browser_routes"]:
            if route["mutating"]:
                self.assertTrue(route["contract_ids"], route)
                self.assertTrue(route["stores"], route)
                self.assertTrue(route["record_classes"], route)
                self.assertNotIn(route["lifecycle"], {"read", "write", "delete"}, route)
            if route["mutating"] and not route["next_only"]:
                self.assertNotEqual(route["auth_boundary"], "missing_local_operator")
        for route in inventory["backend_only_routes"]:
            if route["mutating"]:
                self.assertNotEqual(route["lifecycle"], "backend_write")

    def test_json_inventory_declares_scope_non_goals(self):
        inventory = route_parity.build_inventory(
            route_parity.load_next_routes(),
            route_parity.load_fastapi_routes(),
            route_parity.load_client_fetches(),
        )
        serialized = "\n".join(inventory["non_goals"])
        for phrase in [
            "route payload shape",
            "auth behavior",
            "proof semantics",
            "scanner policy",
            "DB schema",
            "future storage ownership map",
        ]:
            self.assertIn(phrase, serialized)


if __name__ == "__main__":
    unittest.main()
