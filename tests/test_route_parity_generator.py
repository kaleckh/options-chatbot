import unittest

from scripts import generate_route_parity as route_parity


class RouteParityGeneratorTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
