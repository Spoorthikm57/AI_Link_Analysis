import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.services import search_service


class SearchServiceTests(unittest.IsolatedAsyncioTestCase):
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
