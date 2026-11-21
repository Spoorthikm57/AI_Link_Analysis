import asyncio
import logging
import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from tavily import (
    AsyncTavilyClient,
    BadRequestError,
    InvalidAPIKeyError,
    MissingAPIKeyError,
    TavilyKeylessLimitError,
    UsageLimitExceededError,
)

from app.config import TAVILY_API_KEY, TAVILY_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

MAX_RESULTS = 8
MAX_SNIPPET_CHARACTERS = 1_200
MAX_COMPETITORS_TO_ENRICH = 2
SEARCH_QUERIES_PER_REQUEST = (
    "{company} company overview",
    "{company} products and services",
    "{company} industry and business model",
    "{company} target customers and audience",
    "{company} competitors and alternatives",
    "{company} SEO marketing and online presence",
)
COMPETITOR_SEARCH_QUERIES = (
    "{competitor} official website products and services features",
    "{competitor} strengths weaknesses vs {company}",
)

_client: AsyncTavilyClient | None = None


def _company_name_from_url(url: str, extracted_data: dict[str, Any]) -> str:
    parsed = urlsplit(url)
    segments = [part for part in parsed.path.split("/") if part]
    if parsed.hostname and parsed.hostname.lower().endswith("linkedin.com"):
        if not segments:
            return "LinkedIn"
        if len(segments) >= 2 and segments[0].lower() in {"company", "school"}:
            slug = re.sub(r"-\d+$", "", segments[1])
            return re.sub(r"[-_]+", " ", slug).strip() or "the company"

    title = str(extracted_data.get("title", "")).strip()
    if title:
        return title[:120]

    hostname = (parsed.hostname or "").lower().removeprefix("www.")
    parts = hostname.split(".")
    if (
        len(parts) >= 3
        and len(parts[-1]) == 2
        and parts[-2] in {"ac", "co", "com", "gov", "net", "org"}
    ):
        hostname = parts[-3]
    elif len(parts) >= 2:
        hostname = parts[-2]
    name = re.sub(r"[-_]+", " ", hostname).strip()
    return name or "the company"


def build_company_search_queries(
    url: str,
    extracted_data: dict[str, Any] | None = None,
) -> list[str]:
    company = _company_name_from_url(url, extracted_data or {})
    return [template.format(company=company) for template in SEARCH_QUERIES_PER_REQUEST]


def _normalized_result_url(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            return None
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"
    except ValueError:
        return None


def _result_priority(
    url: str,
    score: float,
    requested_url: str | None,
    preferred_name: str | None = None,
) -> tuple[int, float]:
    result_host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    requested_host = (
        (urlsplit(requested_url).hostname or "").lower().removeprefix("www.")
        if requested_url
        else ""
    )
    official_domain = bool(
        requested_host
        and (result_host == requested_host or result_host.endswith(f".{requested_host}"))
    )
    if preferred_name:
        brand_tokens = [
            token
            for token in re.findall(r"[a-z0-9]+", preferred_name.lower())
            if len(token) >= 4
            and token not in {"company", "corporation", "limited", "group"}
        ]
        official_domain = official_domain or any(
            token in result_host for token in brand_tokens
        )
    credible_domain = (
        result_host.endswith((".gov", ".edu"))
        or any(
            domain in result_host
            for domain in ("linkedin.com", "crunchbase.com", "reuters.com", "bloomberg.com")
        )
    )
    return (2 if official_domain else int(credible_domain), score)


def _get_client() -> AsyncTavilyClient:
    global _client
    if _client is None:
        _client = AsyncTavilyClient(api_key=TAVILY_API_KEY)
    return _client


async def _search_queries(
    queries: list[str],
    *,
    max_results_per_query: int,
    result_limit: int,
    requested_url: str | None = None,
    preferred_names: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[Exception]]:
    client = _get_client()
    semaphore = asyncio.Semaphore(3)

    async def search_one(query: str) -> tuple[str, dict[str, Any] | Exception]:
        try:
            async with semaphore:
                result = await client.search(
                    query=query,
                    search_depth="basic",
                    max_results=max_results_per_query,
                    include_answer=False,
                    include_raw_content=False,
                    timeout=TAVILY_TIMEOUT_SECONDS,
                )
            return query, result
        except (
            BadRequestError,
            InvalidAPIKeyError,
            MissingAPIKeyError,
            TavilyKeylessLimitError,
            UsageLimitExceededError,
            httpx.HTTPError,
        ) as error:
            return query, error

    outcomes = await asyncio.gather(*(search_one(query) for query in queries))
    results_by_url: dict[str, dict[str, Any]] = {}
    errors = []

    for query, outcome in outcomes:
        if isinstance(outcome, Exception):
            errors.append(outcome)
            logger.warning(
                "Tavily search failed: error_type=%s",
                type(outcome).__name__,
            )
            continue

        for item in outcome.get("results", []):
            if not isinstance(item, dict):
                continue
            url_value = item.get("url")
            normalized_url = (
                _normalized_result_url(url_value)
                if isinstance(url_value, str)
                else None
            )
            title = item.get("title")
            content = item.get("content") or item.get("raw_content") or ""
            if not normalized_url or not isinstance(title, str) or not isinstance(content, str):
                continue
            try:
                score = float(item.get("score", 0.0))
            except (TypeError, ValueError):
                score = 0.0

            candidate = {
                "title": title.strip()[:500],
                "url": url_value,
                "content": content.strip()[:MAX_SNIPPET_CHARACTERS],
                "query": query,
                "score": score,
                "preferred_name": (preferred_names or {}).get(query),
            }
            if not candidate["title"] or not candidate["content"]:
                continue

            existing = results_by_url.get(normalized_url)
            if existing is None or candidate["score"] > existing["score"]:
                results_by_url[normalized_url] = candidate

    results = sorted(
        results_by_url.values(),
        key=lambda item: (
            _result_priority(
                item["url"],
                item["score"],
                requested_url,
                item.get("preferred_name"),
            )
        ),
        reverse=True,
    )[:result_limit]
    return results, errors


async def search_company_information(
    url: str,
    extracted_data: dict[str, Any] | None = None,
    *,
    discovery_only: bool = False,
) -> dict[str, Any]:
    if not TAVILY_API_KEY:
        return {
            "success": False,
            "error_code": "not_configured",
            "error": "Tavily search is not configured.",
        }

    company = _company_name_from_url(url, extracted_data or {})
    queries = (
        [f"{company} products services competitors alternatives"]
        if discovery_only
        else build_company_search_queries(url, extracted_data)
    )
    results, errors = await _search_queries(
        queries,
        max_results_per_query=3,
        result_limit=3 if discovery_only else MAX_RESULTS,
        requested_url=url,
    )

    if not results:
        return {
            "success": False,
            "error_code": (
                "timeout"
                if errors and all(isinstance(error, httpx.TimeoutException) for error in errors)
                else "unavailable" if errors else "no_results"
            ),
            "error": "Tavily did not return usable public search results.",
        }

    return {
        "success": True,
        "results": [
            {key: item[key] for key in ("title", "url", "content", "query")}
            for item in results
        ],
        "partial_failure": bool(errors),
    }


async def search_competitor_discovery(
    url: str,
    analyzed_company: str,
    business_category: str = "",
) -> dict[str, Any]:
    if not TAVILY_API_KEY:
        return {
            "success": False,
            "error_code": "not_configured",
            "error": "Tavily search is not configured.",
        }

    company = analyzed_company.strip()[:120] or _company_name_from_url(url, {})
    category = business_category.strip()[:120]
    queries = [
        f"{company} competitors",
        f"{category + ' alternatives' if category else company + ' alternatives'}",
    ]
    results, errors = await _search_queries(
        queries,
        max_results_per_query=3,
        result_limit=6,
        requested_url=url,
        preferred_names={query: company for query in queries},
    )
    if not results:
        return {
            "success": False,
            "error_code": (
                "timeout"
                if errors and all(isinstance(error, httpx.TimeoutException) for error in errors)
                else "unavailable" if errors else "no_results"
            ),
            "error": "Tavily did not return usable competitor discovery results.",
        }
    return {
        "success": True,
        "results": [
            {key: item[key] for key in ("title", "url", "content", "query")}
            for item in results
        ],
        "partial_failure": bool(errors),
    }


async def search_competitor_information(
    competitors: list[dict[str, Any]],
    analyzed_company: str,
) -> dict[str, Any]:
    if not TAVILY_API_KEY:
        return {
            "success": False,
            "error_code": "not_configured",
            "error": "Tavily search is not configured.",
        }

    queries = []
    preferred_names = {}
    for competitor in competitors[:MAX_COMPETITORS_TO_ENRICH]:
        name = competitor.get("competitor_name")
        if not isinstance(name, str) or not name.strip():
            continue
        competitor_queries = [
            template.format(
                competitor=name.strip()[:120],
                company=analyzed_company.strip()[:120] or "the analyzed business",
            )
            for template in COMPETITOR_SEARCH_QUERIES
        ]
        queries.extend(competitor_queries)
        preferred_names.update(
            {query: name.strip() for query in competitor_queries}
        )

    if not queries:
        return {"success": False, "error_code": "no_competitors", "results": []}

    results, errors = await _search_queries(
        queries,
        max_results_per_query=2,
        result_limit=MAX_COMPETITORS_TO_ENRICH * len(COMPETITOR_SEARCH_QUERIES) * 2,
        preferred_names=preferred_names,
    )
    if not results:
        return {
            "success": False,
            "error_code": (
                "timeout"
                if errors and all(isinstance(error, httpx.TimeoutException) for error in errors)
                else "unavailable" if errors else "no_results"
            ),
            "error": "Tavily did not return usable competitor search results.",
        }

    return {
        "success": True,
        "results": [
            {key: item[key] for key in ("title", "url", "content", "query")}
            for item in results
        ],
        "partial_failure": bool(errors),
    }


async def close_search_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
