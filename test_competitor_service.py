import unittest
from unittest.mock import AsyncMock, patch

from app.services import competitor_service


def _result(name: str, domain: str) -> dict:
    return {
        "title": f"{name} | Business software",
        "url": f"https://{domain}/products",
        "content": f"{name} provides planning software for small businesses.",
        "query": "business software competitors",
    }


def _generated(name: str, domain: str) -> dict:
    return {
        "competitor_name": name,
        "competitor_website": f"https://{domain}",
        "description": f"{name} provides planning software.",
        "products_and_services": ["Planning software"],
        "strengths": ["Flexible product"],
        "competitive_advantages": ["Flexible product"],
        "weaknesses": ["Smaller market presence"],
        "comparison_with_analyzed_business": "AI-generated inference: serves a similar audience.",
    }


class CompetitorServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_repairs_incomplete_results_and_deduplicates_competitors(self):
        search = AsyncMock(
            side_effect=[
                {"success": True, "results": [_result("Northstar", "northstar.example")]},
                {
                    "success": True,
                    "results": [
                        _result("Northstar", "northstar.example"),
                        _result("Brightline", "brightline.example"),
                        _result("Cedar", "cedar.example"),
                    ],
                },
            ]
        )
        generate = AsyncMock(
            side_effect=[
                {"success": True, "competitors": [_generated("Northstar", "northstar.example")]},
                {
                    "success": True,
                    "competitors": [
                        _generated("Northstar", "northstar.example"),
                        _generated("Brightline", "brightline.example"),
                        _generated("Cedar", "cedar.example"),
                    ],
                },
            ]
        )

        with (
            patch.object(competitor_service, "search_competitor_discovery", new=search),
            patch.object(competitor_service, "generate_competitor_analysis", new=generate),
        ):
            result = await competitor_service.discover_competitors(
                "https://acme.example",
                {
                    "business_overview": {
                        "business_name": "Acme",
                        "business_category": "Business software",
                    },
                    "products_and_services": [{"name": "Planning software"}],
                    "target_audience": {"primary_audience": "Small businesses"},
                },
                {"title": "Acme"},
            )

        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(result["competitors"]), 3)
        self.assertEqual(search.await_count, 2)
        self.assertEqual(
            search.await_args_list[0].args[1],
            "Acme",
        )
        self.assertEqual(
            search.await_args_list[0].kwargs["products_and_services"],
            ["Planning software"],
        )
        self.assertIn(
            "Small businesses",
            search.await_args_list[0].kwargs["target_audience"],
        )
        self.assertEqual(search.await_args_list[1].kwargs["repair_attempt"], 1)
        self.assertEqual(generate.await_count, 2)

    async def test_returns_search_failed_status_after_bounded_attempts(self):
        search = AsyncMock(
            return_value={
                "success": False,
                "error_code": "unavailable",
                "results": [],
            }
        )
        with patch.object(competitor_service, "search_competitor_discovery", new=search):
            result = await competitor_service.discover_competitors(
                "https://acme.example",
                {"business_overview": {"business_name": "Acme"}},
                {},
            )

        self.assertEqual(result["status"], "search_failed")
        self.assertEqual(len(result["competitors"]), 0)
        self.assertEqual(search.await_count, 3)

    async def test_explains_incomplete_results_when_groq_generation_is_rate_limited(self):
        search_results = [
            _result("Northstar", "northstar.example"),
            _result("Brightline", "brightline.example"),
        ]
        search = AsyncMock(
            return_value={"success": True, "results": search_results}
        )
        generate = AsyncMock(
            side_effect=[
                {"success": True, "competitors": []},
                {"success": False, "error_code": "groq_unavailable"},
                {"success": False, "error_code": "groq_unavailable"},
            ]
        )
        existing_competitors = [
            _generated("Northstar", "northstar.example"),
            _generated("Brightline", "brightline.example"),
        ]

        with (
            patch.object(competitor_service, "search_competitor_discovery", new=search),
            patch.object(competitor_service, "generate_competitor_analysis", new=generate),
        ):
            result = await competitor_service.discover_competitors(
                "https://acme.example",
                {
                    "business_overview": {"business_name": "Acme"},
                    "competitor_analysis": existing_competitors,
                },
                {},
            )

        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(len(result["competitors"]), 2)
        self.assertIn("AI competitor generation", result["message"])
        self.assertEqual(search.await_count, 3)


if __name__ == "__main__":
    unittest.main()
