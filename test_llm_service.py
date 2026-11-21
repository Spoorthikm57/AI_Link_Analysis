import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from app import main, schemas
from app.services import llm_service


def valid_analysis_payload() -> dict:
    return {
        "business_overview": {
            "business_name": "Example",
            "business_description": "Example business",
            "business_category": "Services",
            "website_purpose": "Describe services",
            "brand_advantages": ["Clear service offering", "Responsive support"],
            "brand_positioning": "A practical service provider for small businesses",
        },
        "competitor_analysis": [
            {
                "competitor_name": "Alternative One",
                "competitor_website": "https://example.org",
                "description": "A relevant alternative.",
                "products_and_services": ["Business tools", "Customer support"],
                "strengths": ["Established", "Accessible", "Documented"],
                "weaknesses": ["Different focus", "Limited scope", "Different audience"],
                "comparison_with_analyzed_business": "Offers a comparable solution.",
            },
            {
                "competitor_name": "Alternative Two",
                "competitor_website": "https://example.net",
                "description": "A related solution.",
                "products_and_services": ["Planning platform", "Reporting"],
                "strengths": ["Broad reach", "Strong ecosystem", "Easy adoption"],
                "weaknesses": ["Less specialized", "Cost", "Complexity"],
                "comparison_with_analyzed_business": "Competes for a similar audience.",
            },
            {
                "competitor_name": "Alternative Three",
                "competitor_website": "https://example.io",
                "description": "A third relevant option.",
                "products_and_services": ["Modern services", "Integrations"],
                "strengths": ["Modern", "Flexible", "Well supported"],
                "weaknesses": ["Smaller community", "Less mature", "Learning curve"],
                "comparison_with_analyzed_business": "Provides an alternative approach.",
            },
        ],
        "search_queries": [
            {
                "query": "example services",
                "platform": "Google Search",
                "search_intent": "Commercial research",
                "business_relevance": "Finds the analyzed business services.",
                "relevance_score": 0.9,
                "target_audience": "Small businesses",
            },
            {"query": "example services", "platform": "Facebook", "search_intent": "Discovery", "business_relevance": "Finds community discussion.", "target_audience": "Small businesses"},
            {"query": "example solutions", "platform": "Instagram", "search_intent": "Discovery", "business_relevance": "Finds visual examples.", "target_audience": "Small businesses"},
            {"query": "example business services", "platform": "LinkedIn", "search_intent": "Professional", "business_relevance": "Finds professional use cases.", "target_audience": "Business leaders"},
            {"query": "example services news", "platform": "X (Twitter)", "search_intent": "Current information", "business_relevance": "Finds updates and discussions.", "target_audience": "Technology users"},
        ],
        "seo_analysis": {
            "primary_keywords": ["example", "example services", "business solutions"],
            "secondary_keywords": ["example help", "example support", "example guide", "example resources", "example solutions"],
            "long_tail_keywords": ["how to use example services", "best example solutions for small business", "example service pricing", "example implementation guide", "example customer support"],
            "suggested_seo_title": "Example",
            "suggested_meta_description": "Example services",
            "content_improvements": ["Clarify services", "Add customer examples", "Improve calls to action"],
            "content_ideas": ["Getting started", "Implementation guide", "Customer stories", "Industry use cases", "Frequently asked questions"],
        },
        "products_and_services": [
            {"name": "Consulting", "description": "Business consulting", "target_customer": "Small businesses", "benefits": ["Expert guidance", "Practical support", "Clear planning"]},
            {"name": "Implementation", "description": "Solution implementation", "target_customer": "Organizations", "benefits": ["Faster adoption", "Reliable setup", "Training"]},
            {"name": "Support", "description": "Ongoing customer support", "target_customer": "All customers", "benefits": ["Issue resolution", "Advice", "Continuity"]},
        ],
        "target_audience": {
            "primary_audience": "Small businesses",
            "secondary_audience": "Business leaders",
            "industries": ["Technology", "Professional services", "Retail"],
            "business_types": ["Small businesses", "Startups", "Enterprises"],
            "customer_profiles": ["Operations leaders", "Small business owners"],
            "locations": ["United States"],
            "customer_needs": ["Reliability", "Guidance", "Affordability"],
            "pain_points": ["Limited expertise", "Time constraints", "Unclear solutions"],
            "interests": ["Business growth", "Automation", "Digital services"],
            "audience_segments": ["Growing businesses", "Digital teams"],
        },
        "swot_analysis": {
            "strengths": ["Relevant expertise", "Clear offering", "Flexible service"],
            "weaknesses": ["Limited public detail", "Small footprint", "Brand awareness"],
            "opportunities": ["Educational content", "Partner ecosystem", "Customer stories"],
            "threats": ["Established competitors", "Changing needs", "Market substitution"],
        },
    }


class LLMServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_accepts_complete_structured_analysis(self) -> None:
        content = json.dumps(valid_analysis_payload())
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

        with patch.object(
            llm_service, "_create_completion", new=AsyncMock(return_value=response)
        ):
            result = await llm_service.analyze_website_with_ai({"content": "Example"})

        self.assertTrue(result["success"])
        self.assertEqual(
            set(result["analysis"]),
            {
                "business_overview",
                "competitor_analysis",
                "search_queries",
                "seo_analysis",
                "products_and_services",
                "target_audience",
                "swot_analysis",
            },
        )

    async def test_retries_an_empty_groq_response_with_correction_prompt(self) -> None:
        empty_response = SimpleNamespace(choices=[])
        corrected_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(valid_analysis_payload())
                    )
                )
            ]
        )

        with (
            patch.object(
                llm_service,
                "_create_completion",
                new=AsyncMock(return_value=empty_response),
            ),
            patch.object(
                llm_service,
                "_create_correction_completion",
                new=AsyncMock(return_value=corrected_response),
            ) as correct,
        ):
            result = await llm_service.analyze_website_with_ai({"content": "Example"})

        self.assertTrue(result["success"])
        correct.assert_awaited_once()

    async def test_repairs_empty_competitor_analysis_with_focused_correction(self) -> None:
        incomplete = valid_analysis_payload()
        incomplete["competitor_analysis"] = []
        incomplete_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(incomplete))
                )
            ]
        )
        corrected_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(valid_analysis_payload()))
                )
            ]
        )

        with (
            patch.object(
                llm_service, "_create_completion", new=AsyncMock(return_value=incomplete_response)
            ),
            patch.object(
                llm_service,
                "_create_correction_completion",
                new=AsyncMock(return_value=corrected_response),
            ) as correct,
        ):
            result = await llm_service.analyze_website_with_ai(
                {
                    "content": "Example business services",
                    "direct_extraction_success": True,
                    "search_results": [],
                }
            )

        self.assertTrue(result["success"])
        self.assertEqual(len(result["analysis"]["competitor_analysis"]), 3)
        correct.assert_awaited_once()
        missing_sections = correct.await_args.args[3]
        self.assertIn("competitor_analysis", missing_sections)

    async def test_rejects_json_that_does_not_match_schema(self) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"unexpected": true}'))]
        )

        with (
            patch.object(llm_service, "_create_completion", new=AsyncMock(return_value=response)),
            patch.object(
                llm_service,
                "_create_correction_completion",
                new=AsyncMock(return_value=response),
            ),
        ):
            result = await llm_service.analyze_website_with_ai({"content": "Example"})

        self.assertTrue(result["success"])
        self.assertTrue(result["partial"])

    async def test_requires_complete_competitor_and_swot_fields(self) -> None:
        payload = valid_analysis_payload()
        payload["competitor_analysis"][0]["strengths"] = []
        payload["swot_analysis"]["threats"] = []

        with self.assertRaises(ValueError):
            schemas.WebsiteAnalysis.model_validate(payload)

    async def test_limits_content_sent_to_model(self) -> None:
        prompt_data = llm_service._build_prompt_data({"content": "x" * 20_000})

        self.assertEqual(len(prompt_data["content"]), llm_service.MAX_CONTENT_CHARACTERS)

    async def test_includes_open_graph_metadata_in_prompt(self) -> None:
        prompt_data = llm_service._build_prompt_data(
            {"open_graph": {"site_name": "Example", "description": "Public summary"}}
        )

        self.assertEqual(
            prompt_data["open_graph"],
            {"site_name": "Example", "description": "Public summary"},
        )

    async def test_returns_a_handled_error_when_groq_connection_fails(self) -> None:
        error = llm_service.APIConnectionError(
            message="Connection failed",
            request=httpx.Request("POST", "https://api.groq.com"),
        )
        with patch.object(
            llm_service,
            "_create_completion",
            new=AsyncMock(side_effect=error),
        ):
            result = await llm_service.analyze_website_with_ai({"content": "Example"})

        self.assertTrue(result["success"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["error_code"], "connection_error")


class AnalysisEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_allows_frontend_development_origin(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app),
            base_url="http://test",
        ) as client:
            response = await client.options(
                "/link-analysis",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:5173",
        )

    async def test_returns_structured_analysis_and_rejects_invalid_url(self) -> None:
        website_data = {
            "success": True,
            "url": "https://example.com",
            "title": "Example",
            "meta_description": "Example description",
            "headings": ["Example heading"],
            "content": "Example content with enough detail to support a direct analysis. " * 4,
        }
        analysis = schemas.WebsiteAnalysis.model_validate(valid_analysis_payload())

        async def extract_website(_url: str) -> dict:
            del _url
            return website_data

        async def analyze_website(_website: dict) -> dict:
            del _website
            return {"success": True, "analysis": analysis.model_dump()}

        with (
            patch.object(main, "extract_website_content", new=extract_website),
            patch.object(main, "analyze_website_with_ai", new=analyze_website),
            patch.object(
                main,
                "search_company_information",
                new=AsyncMock(
                    return_value={"success": False, "error_code": "not_configured"}
                ),
            ) as search,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/link-analysis", json={"url": "https://example.com"}
                )
                invalid_url_response = await client.post(
                    "/link-analysis", json={"url": "not a URL"}
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["analysis"]["business_overview"]["business_name"], "Example")
        self.assertTrue(response.json()["sources"]["direct_extraction_success"])
        self.assertFalse(response.json()["sources"]["tavily_search_used"])
        search.assert_awaited_once()
        self.assertTrue(search.await_args.kwargs["discovery_only"])
        self.assertEqual(invalid_url_response.status_code, 400)

    async def test_uses_public_search_for_blocked_linkedin_and_marks_sources(self) -> None:
        website_data = {
            "success": False,
            "error_code": "access_restricted",
            "error": "Login required.",
        }
        search_results = [
            {
                "title": "Acme company profile",
                "url": "https://example.org/acme",
                "content": "Acme provides business software to small companies.",
                "query": "Acme company overview",
            }
        ]
        analysis = schemas.WebsiteAnalysis.model_validate(valid_analysis_payload())
        with (
            patch.object(
                main,
                "extract_website_content",
                new=AsyncMock(return_value=website_data),
            ),
            patch.object(
                main,
                "search_company_information",
                new=AsyncMock(
                    return_value={"success": True, "results": search_results}
                ),
            ) as search,
            patch.object(
                main,
                "search_competitor_information",
                new=AsyncMock(
                    return_value={"success": False, "error_code": "no_results"}
                ),
            ),
            patch.object(
                main,
                "analyze_website_with_ai",
                new=AsyncMock(return_value={"success": True, "analysis": analysis.model_dump()}),
            ) as analyze,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/link-analysis",
                    json={"url": "https://www.linkedin.com/company/acme-inc/"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["sources"]["direct_extraction_success"])
        self.assertEqual(payload["sources"]["extraction_status"], "access_restricted")
        self.assertTrue(payload["sources"]["tavily_search_used"])
        self.assertEqual(payload["sources"]["search_results"], search_results)
        self.assertEqual(analyze.await_args.args[0]["search_results"], search_results)
        search.assert_awaited_once()

    async def test_enriches_competitors_and_regenerates_analysis_with_search_evidence(self) -> None:
        website_data = {
            "success": True,
            "url": "https://example.com",
            "title": "Example",
            "meta_description": "Example business",
            "headings": ["Example services"],
            "content": "Public website content with enough detail for a direct analysis. " * 3,
        }
        discovery_results = [
            {
                "title": "Example alternatives",
                "url": "https://research.example/alternatives",
                "content": "Northstar is a related service provider.",
                "query": "Example competitors and alternatives",
            }
        ]
        competitor_results = [
            {
                "title": "Northstar official products",
                "url": "https://northstar.example/products",
                "content": "Northstar provides business planning software.",
                "query": "Northstar official website products and services features",
            }
        ]
        analysis = schemas.WebsiteAnalysis.model_validate(valid_analysis_payload())
        with (
            patch.object(
                main,
                "extract_website_content",
                new=AsyncMock(return_value=website_data),
            ),
            patch.object(
                main,
                "search_company_information",
                new=AsyncMock(
                    return_value={"success": True, "results": discovery_results}
                ),
            ),
            patch.object(
                main,
                "search_competitor_information",
                new=AsyncMock(
                    return_value={"success": True, "results": competitor_results}
                ),
            ) as competitor_search,
            patch.object(
                main,
                "analyze_website_with_ai",
                new=AsyncMock(
                    side_effect=[
                        {"success": True, "analysis": analysis.model_dump()},
                        {"success": True, "analysis": analysis.model_dump()},
                    ]
                ),
            ) as analyze,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/link-analysis",
                    json={"url": "https://example.com"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(analyze.await_count, 2)
        self.assertEqual(
            analyze.await_args_list[1].args[0]["search_results"],
            discovery_results + competitor_results,
        )
        self.assertEqual(
            response.json()["sources"]["search_results"],
            discovery_results + competitor_results,
        )
        self.assertEqual(
            competitor_search.await_args.args[1],
            "Example",
        )

    async def test_reports_tavily_failure_without_calling_groq(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app),
            base_url="http://test",
        ) as client:
            with (
                patch.object(
                    main,
                    "extract_website_content",
                    new=AsyncMock(
                        return_value={
                            "success": False,
                            "error_code": "access_restricted",
                            "error": "Website blocks direct access.",
                        }
                    ),
                ),
                patch.object(
                    main,
                    "search_company_information",
                    new=AsyncMock(
                        return_value={
                            "success": False,
                            "error_code": "unavailable",
                            "error": "Tavily API failed.",
                        }
                    ),
                ),
                patch.object(main, "analyze_website_with_ai", new=AsyncMock()) as analyze,
            ):
                response = await client.post(
                    "/link-analysis",
                    json={"url": "https://example.com"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertTrue(response.json()["sources"]["extraction_status"] == "access_restricted")
        self.assertFalse(response.json()["sources"]["tavily_search_used"])
        analyze.assert_not_awaited()

    async def test_rejects_invalid_public_url_before_using_tavily(self) -> None:
        with (
            patch.object(
                main,
                "extract_website_content",
                new=AsyncMock(
                    return_value={
                        "success": False,
                        "error_code": "invalid_url",
                        "error": "Local and private network addresses cannot be analyzed.",
                    }
                ),
            ),
            patch.object(main, "search_company_information", new=AsyncMock()) as search,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/link-analysis",
                    json={"url": "https://127.0.0.1"},
                )

        self.assertEqual(response.status_code, 400)
        search.assert_not_awaited()

    async def test_does_not_send_insufficient_content_to_ai_without_search_results(self) -> None:
        empty_page = {
            "success": True,
            "url": "https://example.com",
            "title": "",
            "meta_description": "",
            "headings": [],
            "content": "",
        }
        with (
            patch.object(
                main,
                "extract_website_content",
                new=AsyncMock(return_value=empty_page),
            ),
            patch.object(
                main,
                "search_company_information",
                new=AsyncMock(
                    return_value={
                        "success": False,
                        "error_code": "no_results",
                    }
                ),
            ),
            patch.object(main, "analyze_website_with_ai", new=AsyncMock()) as analyze,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/link-analysis",
                    json={"url": "https://example.com"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertTrue(response.json()["analysis"])
        analyze.assert_not_awaited()

    async def test_returns_friendly_message_for_incomplete_ai_response(self) -> None:
        website_data = {
            "success": True,
            "url": "https://example.com",
            "title": "Example",
            "meta_description": "",
            "headings": [],
            "content": "Public website content that is sufficiently long for direct analysis. " * 3,
        }
        with (
            patch.object(
                main,
                "extract_website_content",
                new=AsyncMock(return_value=website_data),
            ),
            patch.object(
                main,
                "analyze_website_with_ai",
                new=AsyncMock(
                    return_value={
                        "success": False,
                        "error_code": "invalid_response",
                        "error": "Internal model schema validation details",
                    }
                ),
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/link-analysis",
                    json={"url": "https://example.com"},
                )

        self.assertEqual(response.status_code, 503)
        self.assertIn("could not create a complete report", response.json()["detail"])
        self.assertNotIn("schema validation", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
