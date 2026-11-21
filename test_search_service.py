import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.services import search_service


class SearchServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_competitor_discovery_runs_multiple_targeted_queries(self):
        client = AsyncMock()
        client.search.return_value = {
            "results": [
                {
                    "title": "Related company",
                    "url": "https://related.example/about",
                    "content": "A comparable public company.",
                    "score": 0.8,
                }
            ]
        }

        with (
            patch.object(search_service, "TAVILY_API_KEY", "test-key"),
            patch.object(search_service, "_client", client),
        ):
            result = await search_service.search_competitor_discovery(
                "https://example.com",
                "Example",
                "Business software",
            )

        queries = [
            call.kwargs["query"]
            for call in client.search.await_args_list
        ]
        self.assertTrue(result["success"])
        self.assertIn("Example competitors", queries)
        self.assertIn("Business software alternatives", queries)
        self.assertIn("Example vs alternatives", queries)
        self.assertIn("Best alternatives to Example", queries)
        self.assertIn("Companies offering Business software", queries)
        self.assertIn("Business software companies similar to Example", queries)

    async def test_competitor_search_uses_different_repair_queries(self):
        initial = search_service.build_competitor_search_queries(
            "Example",
            "Business software",
            ["Planning tools"],
            "Small businesses",
        )
        repair = search_service.build_competitor_search_queries(
            "Example",
            "Business software",
            ["Planning tools"],
            "Small businesses",
            repair_attempt=1,
        )

        self.assertEqual(len(initial), 7)
        self.assertEqual(len(repair), 3)
        self.assertFalse(set(initial) & set(repair))
        self.assertTrue(any("Small businesses" in query for query in repair))

    async def test_processes_competitors_and_filters_self_articles_and_social_results(self):
        results = [
            {
                "title": "Northstar | Business planning",
                "url": "https://northstar.example/products",
                "content": "Northstar provides planning software for small businesses.",
                "query": "Business software companies similar to Acme",
            },
            {
                "title": "Northstar | Business planning",
                "url": "https://www.northstar.example/about",
                "content": "Northstar provides software and consulting services.",
                "query": "Acme competitors",
            },
            {
                "title": "Acme | Official website",
                "url": "https://acme.example/about",
                "content": "The analyzed company.",
                "query": "Acme competitors",
            },
            {
                "title": "Best competitors this year",
                "url": "https://publisher.example/news/competitors",
                "content": "A news story about competing companies.",
                "query": "Acme competitors",
            },
            {
                "title": "Northstar profile",
                "url": "https://www.linkedin.com/company/northstar",
                "content": "Company profile.",
                "query": "Acme competitors",
            },
            {
                "title": "Brightline | Services",
                "url": "https://brightline.example/blog/services",
                "content": "A blog post.",
                "query": "Acme competitors",
            },
        ]

        candidates = search_service.process_competitor_search_results(
            results,
            "https://acme.example",
            "Acme",
            "Business software",
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["name"], "Northstar")
        self.assertEqual(candidates[0]["website"], "https://northstar.example")
        self.assertTrue(candidates[0]["products_services"])

    async def test_builds_company_queries_from_linkedin_company_slug(self):
        queries = search_service.build_company_search_queries(
            "https://www.linkedin.com/company/acme-industries-1234/"
        )

        self.assertEqual(len(queries), 6)
        self.assertIn("acme industries company overview", queries)
        self.assertIn("acme industries competitors and alternatives", queries)

    async def test_uses_one_bounded_search_for_direct_content_discovery(self):
        client = AsyncMock()
        client.search.return_value = {
            "results": [
                {
                    "title": "Acme alternatives",
                    "url": "https://example.com/alternatives",
                    "content": "Products and competitors for Acme.",
                    "score": 0.8,
                }
            ]
        }

        with (
            patch.object(search_service, "TAVILY_API_KEY", "test-key"),
            patch.object(search_service, "_client", client),
        ):
            result = await search_service.search_company_information(
                "https://example.com",
                {"title": "Acme"},
                discovery_only=True,
            )

        self.assertTrue(result["success"])
        self.assertEqual(client.search.await_count, 1)
        self.assertIn("Acme products services competitors", client.search.await_args.kwargs["query"])

    async def test_searches_each_of_two_competitors_individually(self):
        client = AsyncMock()
        client.search.return_value = {
            "results": [
                {
                    "title": "Competitor result",
                    "url": "https://competitor.example/about",
                    "content": "Public competitor information.",
                    "score": 0.8,
                }
            ]
        }

        with (
            patch.object(search_service, "TAVILY_API_KEY", "test-key"),
            patch.object(search_service, "_client", client),
        ):
            result = await search_service.search_competitor_information(
                [
                    {"competitor_name": "Northstar"},
                    {"competitor_name": "Brightline"},
                    {"competitor_name": "Not searched"},
                ],
                "Acme",
            )

        queries = [
            call.kwargs["query"]
            for call in client.search.await_args_list
        ]
        self.assertTrue(result["success"])
        self.assertEqual(client.search.await_count, 4)
        self.assertTrue(any("Northstar official website" in query for query in queries))
        self.assertTrue(any("Northstar strengths weaknesses vs Acme" in query for query in queries))
        self.assertTrue(any("Brightline official website" in query for query in queries))
        self.assertFalse(any("Not searched" in query for query in queries))

    async def test_deduplicates_search_results_and_handles_api_failures(self):
        client = AsyncMock()
        client.search.return_value = {
            "results": [
                {
                    "title": "Acme official site",
                    "url": "https://example.com/about",
                    "content": "Acme company information.",
                    "score": 0.8,
                },
                {
                    "title": "Acme official site duplicate",
                    "url": "https://EXAMPLE.com/about/",
                    "content": "Duplicate result.",
                    "score": 0.9,
                },
            ]
        }

        with (
            patch.object(search_service, "TAVILY_API_KEY", "test-key"),
            patch.object(search_service, "_client", client),
        ):
            result = await search_service.search_company_information(
                "https://example.com"
            )

        self.assertTrue(result["success"])
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["title"], "Acme official site duplicate")
        self.assertEqual(client.search.await_count, 6)

    async def test_returns_failure_when_every_tavily_query_fails(self):
        client = AsyncMock()
        client.search.side_effect = httpx.TimeoutException("timed out")

        with (
            patch.object(search_service, "TAVILY_API_KEY", "test-key"),
            patch.object(search_service, "_client", client),
        ):
            result = await search_service.search_company_information(
                "https://example.com"
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "timeout")


if __name__ == "__main__":
    unittest.main()
