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
MAX_COMPETITOR_DISCOVERY_RESULTS = 21
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
SOCIAL_MEDIA_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "youtube.com",
)
EDITORIAL_DOMAINS = (
    "bbc.com",
    "bbc.co.uk",
    "capterra.com",
    "cnn.com",
    "crunchbase.com",
    "forbes.com",
    "nytimes.com",
    "g2.com",
    "medium.com",
    "reuters.com",
    "theverge.com",
    "techcrunch.com",
    "theguardian.com",
    "wikipedia.org",
)
EDITORIAL_PATH_PARTS = (
    "/article",
    "/blog",
    "/news",
    "/press",
    "/review",
    "/stories",
)
EDITORIAL_TITLE_TERMS = (
    "alternatives to",
    "best alternatives",
    "best website",
    "competitors of",
    "company news",
    "how to",
    "press release",
    "top 10",
    "top alternatives",
    "tutorial",
    "vs.",
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


def build_competitor_search_queries(
    company: str,
    category: str = "",
    products_and_services: list[str] | None = None,
    target_audience: str = "",
    repair_attempt: int = 0,
) -> list[str]:
    company = company.strip()[:120] or "the analyzed business"
    category = category.strip()[:120] or "related industry"
    offerings = ", ".join(
        item.strip()[:100]
        for item in (products_and_services or [])
        if isinstance(item, str) and item.strip()
    )[:240] or category
    audience = target_audience.strip()[:120] or "similar customers"

    if repair_attempt == 0:
        queries = [
            f"{company} competitors",
            f"Best alternatives to {company}",
            f"{category} alternatives",
            f"{company} vs alternatives",
            f"Companies offering {offerings}",
            f"{category} companies similar to {company}",
            f"{company} alternatives in {category}",
        ]
    elif repair_attempt == 1:
        queries = [
            f"{offerings} providers serving {audience}",
            f"leading {category} providers like {company}",
            f"{company} competitor official websites",
        ]
    else:
        queries = [
            f"{category} solutions for {audience}",
            f"businesses competing with {company} in {category}",
            f"{offerings} companies for {audience}",
        ]
    return list(dict.fromkeys(query[:300] for query in queries))


def _host_is_under(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def _competitor_name_from_result(title: str, hostname: str) -> str:
    name = re.split(r"\s*[|–—:]\s*|\s+-\s+", title.strip(), maxsplit=1)[0].strip()
    name = re.sub(
        r"\s+(official (website|site|products?|services?|features?)|"
        r"products and services|homepage|home page|home)$",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip(" -|:")
    if not name or name.lower() in {"home", "welcome", "official website"}:
        labels = hostname.lower().removeprefix("www.").split(".")
        if len(labels) >= 3 and labels[-2] in {"ac", "co", "com", "gov", "net", "org"}:
            name = labels[-3]
        elif len(labels) >= 2:
            name = labels[-2]
        else:
            name = labels[0]
        name = re.sub(r"[-_]+", " ", name).title()
    return name[:120]


def _is_editorial_result(title: str, url: str, hostname: str) -> bool:
    lowered_title = title.lower()
    lowered_path = urlsplit(url).path.lower()
    return (
        _host_is_under(hostname, EDITORIAL_DOMAINS)
        or any(part in lowered_path for part in EDITORIAL_PATH_PARTS)
        or any(term in lowered_title for term in EDITORIAL_TITLE_TERMS)
    )


def process_competitor_search_results(
    results: list[dict[str, Any]],
    analyzed_url: str,
    analyzed_company: str,
    business_category: str = "",
) -> list[dict[str, Any]]:
    analyzed_host = (
        (urlsplit(analyzed_url).hostname or "").lower().removeprefix("www.")
    )
    analyzed_name = re.sub(
        r"[^a-z0-9]+", "", analyzed_company.lower()
    )
    candidates_by_host: dict[str, dict[str, Any]] = {}
    seen_names: set[str] = set()

    for result in results:
        if not isinstance(result, dict):
            continue
        url = result.get("url")
        title = result.get("title")
        content = result.get("content")
        if not all(isinstance(value, str) and value.strip() for value in (url, title, content)):
            continue
        normalized_url = _normalized_result_url(url)
        if not normalized_url:
            continue
        parsed = urlsplit(normalized_url)
        hostname = (parsed.hostname or "").lower().removeprefix("www.")
        if (
            not hostname
            or hostname == analyzed_host
            or hostname.endswith(f".{analyzed_host}")
            or _host_is_under(hostname, SOCIAL_MEDIA_DOMAINS)
            or _is_editorial_result(title, normalized_url, hostname)
        ):
            continue

        name = _competitor_name_from_result(title, hostname)
        name_key = re.sub(r"[^a-z0-9]+", "", name.lower())
        if not name_key or name_key == analyzed_name or name_key in seen_names:
            continue
        content_text = re.sub(r"\s+", " ", content).strip()[:MAX_SNIPPET_CHARACTERS]
        sentences = re.split(r"(?<=[.!?])\s+", content_text)
        description = " ".join(sentences[:2]).strip()[:500] or content_text[:500]
        offering_sentences = [
            sentence.strip()
            for sentence in sentences
            if re.search(
                r"\b(offer|provides?|speciali[sz]es?|products?|services?)\b",
                sentence,
                re.IGNORECASE,
            )
        ]
        products_services = [sentence[:200] for sentence in offering_sentences[:3]]
        candidate = {
            "name": name,
            "website": f"{parsed.scheme}://{parsed.netloc}",
            "description": description,
            "products_services": products_services,
            "similarity": (
                f"Identified from the {result.get('query', 'competitor discovery')} "
                f"search in the {business_category or 'related'} market."
            ),
            "source_url": normalized_url,
        }
        existing = candidates_by_host.get(hostname)
        if existing is None or len(candidate["description"]) > len(existing["description"]):
            candidates_by_host[hostname] = candidate
            seen_names.add(name_key)

    candidates = list(candidates_by_host.values())
    logger.info(
        "[COMPETITOR] Extracted %s potential competitors",
        len(candidates),
    )
    return candidates


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
    products_and_services: list[str] | None = None,
    target_audience: str = "",
    repair_attempt: int = 0,
) -> dict[str, Any]:
    company = analyzed_company.strip()[:120] or _company_name_from_url(url, {})
    category = business_category.strip()[:120]
    queries = build_competitor_search_queries(
        company,
        category,
        products_and_services,
        target_audience,
        repair_attempt,
    )
    logger.info("[COMPETITOR] Generated queries: %s", queries)
    if not TAVILY_API_KEY:
        return {
            "success": False,
            "error_code": "not_configured",
            "error": "Tavily search is not configured.",
        }

    results, errors = await _search_queries(
        queries,
        max_results_per_query=3,
        result_limit=MAX_COMPETITOR_DISCOVERY_RESULTS,
        requested_url=url,
        preferred_names={query: company for query in queries},
    )
    logger.info("[COMPETITOR] Tavily returned %s results", len(results))
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
