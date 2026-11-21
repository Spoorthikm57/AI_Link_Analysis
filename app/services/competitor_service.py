import logging
import re
from typing import Any
from urllib.parse import urlsplit

from app.services.llm_service import generate_competitor_analysis
from app.services.search_service import (
    process_competitor_search_results,
    search_competitor_discovery,
)

logger = logging.getLogger(__name__)

MAX_REPAIR_ATTEMPTS = 2
MINIMUM_COMPETITORS = 3
UNAVAILABLE_TEXT = "insufficient publicly available information"


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        item.strip()
        for item in value
        if isinstance(item, str)
        and item.strip()
        and UNAVAILABLE_TEXT not in item.strip().lower()
    ]


def _usable_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip()
    if not normalized or UNAVAILABLE_TEXT in normalized.lower():
        return ""
    return normalized


def _business_information(
    analysis: dict[str, Any],
    extracted_data: dict[str, Any],
    website_url: str,
) -> dict[str, Any]:
    overview = analysis.get("business_overview")
    overview = overview if isinstance(overview, dict) else {}
    products = analysis.get("products_and_services")
    products = products if isinstance(products, list) else []
    product_names = [
        _usable_text(item.get("name"))
        for item in products
        if isinstance(item, dict)
        and _usable_text(item.get("name"))
    ]
    audience = analysis.get("target_audience")
    audience = audience if isinstance(audience, dict) else {}
    audience_values = [
        _usable_text(audience.get("primary_audience")),
        _usable_text(audience.get("secondary_audience")),
        *_text_list(audience.get("industries")),
        *_text_list(audience.get("business_types")),
    ]
    target_audience = ", ".join(
        item.strip() for item in audience_values if isinstance(item, str) and item.strip()
    )[:300]
    hostname = (urlsplit(website_url).hostname or "").removeprefix("www.")
    business_name = (
        _usable_text(overview.get("business_name"))
        or _usable_text(extracted_data.get("title"))
        or hostname
        or "the analyzed business"
    )
    return {
        "business_name": business_name[:120],
        "business_category": _usable_text(overview.get("business_category"))[:120],
        "business_description": _usable_text(overview.get("business_description"))[:500],
        "products_and_services": product_names[:5],
        "target_audience": target_audience,
    }


def _merge_candidates(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for candidate in [*existing, *incoming]:
        host = (urlsplit(str(candidate.get("website", ""))).hostname or "").lower()
        if host:
            merged[host.removeprefix("www.")] = candidate
    return list(merged.values())


def _merge_competitors(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for competitor in [*existing, *incoming]:
        host = (
            urlsplit(str(competitor.get("competitor_website", ""))).hostname or ""
        ).lower().removeprefix("www.")
        name = re.sub(
            r"[^a-z0-9]+",
            "",
            str(competitor.get("competitor_name", "")).lower(),
        )
        key = host or name
        if key and key not in merged:
            merged[key] = competitor
    return list(merged.values())[:5]


def _supported_existing_competitors(
    existing: Any,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(existing, list):
        return []
    candidates_by_host = {
        (urlsplit(str(candidate.get("website", ""))).hostname or "")
        .lower()
        .removeprefix("www."): candidate
        for candidate in candidates
    }
    supported = []
    for competitor in existing:
        if not isinstance(competitor, dict):
            continue
        host = (
            urlsplit(str(competitor.get("competitor_website", ""))).hostname or ""
        ).lower().removeprefix("www.")
        candidate = candidates_by_host.get(host)
        if candidate is None:
            continue
        normalized = dict(competitor)
        normalized["competitor_name"] = candidate["name"]
        normalized["competitor_website"] = candidate["website"]
        normalized.setdefault(
            "competitive_advantages",
            normalized.get("strengths", []),
        )
        supported.append(normalized)
    return supported


async def discover_competitors(
    website_url: str,
    analysis: dict[str, Any],
    extracted_data: dict[str, Any],
) -> dict[str, Any]:
    logger.info("[COMPETITOR] Starting competitor discovery")
    business = _business_information(analysis, extracted_data, website_url)
    candidates: list[dict[str, Any]] = []
    competitors: list[dict[str, Any]] = []
    tavily_results: list[dict[str, Any]] = []
    search_succeeded = False
    search_failed = False
    generation_failed = False
    last_search_error = ""
    existing_competitors = analysis.get("competitor_analysis")

    for repair_attempt in range(MAX_REPAIR_ATTEMPTS + 1):
        if repair_attempt:
            logger.info(
                "[COMPETITOR] Starting repair attempt %s",
                repair_attempt,
            )
        try:
            discovery = await search_competitor_discovery(
                website_url,
                business["business_name"],
                business["business_category"],
                products_and_services=business["products_and_services"],
                target_audience=business["target_audience"],
                repair_attempt=repair_attempt,
            )
        except Exception:
            logger.exception(
                "[COMPETITOR] Tavily discovery raised an exception on attempt %s",
                repair_attempt,
            )
            search_failed = True
            last_search_error = "unavailable"
            continue

        if discovery.get("success"):
            search_succeeded = True
            new_results = discovery.get("results", [])
            if isinstance(new_results, list):
                tavily_results.extend(
                    item for item in new_results if isinstance(item, dict)
                )
            potential_competitors = process_competitor_search_results(
                new_results if isinstance(new_results, list) else [],
                website_url,
                business["business_name"],
                business["business_category"],
            )
            candidates = _merge_candidates(candidates, potential_competitors)
            competitors = _merge_competitors(
                competitors,
                _supported_existing_competitors(existing_competitors, candidates),
            )
        else:
            last_search_error = str(discovery.get("error_code") or "unavailable")
            search_failed = last_search_error not in {"no_results"}

        if candidates:
            generated = await generate_competitor_analysis(business, candidates)
            if generated.get("success"):
                new_competitors = generated.get("competitors", [])
                competitors = _merge_competitors(
                    competitors,
                    new_competitors if isinstance(new_competitors, list) else [],
                )
                logger.info(
                    "[COMPETITOR] Groq generated %s competitors",
                    len(new_competitors) if isinstance(new_competitors, list) else 0,
                )
            else:
                generation_failed = True
                logger.warning(
                    "[COMPETITOR] Groq generation failed: code=%s",
                    generated.get("error_code", "unknown"),
                )

        if len(competitors) >= MINIMUM_COMPETITORS:
            break
        logger.info(
            "[COMPETITOR] Validation failed: competitor analysis incomplete"
        )

    if len(competitors) >= MINIMUM_COMPETITORS:
        status = "complete"
        message = f"Found and analyzed {len(competitors)} competitors."
    elif generation_failed and candidates:
        if competitors:
            status = "incomplete"
            message = (
                "AI competitor generation was unavailable or incomplete; only "
                f"{len(competitors)} candidate-backed competitors are shown."
            )
        else:
            status = "analysis_failed"
            message = (
                "Competitor candidates were found, but AI comparison could not "
                "be generated. Please retry."
            )
    elif not search_succeeded and search_failed:
        status = "search_failed"
        message = (
            "Competitor search could not be completed. Please retry later."
        )
    elif competitors:
        status = "incomplete"
        message = (
            f"Competitor search returned only {len(competitors)} reliable "
            "businesses; results may be incomplete."
        )
    else:
        status = "insufficient_search_results"
        message = (
            "We could not identify reliable competitors from the available "
            f"search results.{f' Search status: {last_search_error}.' if last_search_error else ''}"
        )

    logger.info("[COMPETITOR] Final competitor count: %s", len(competitors))
    return {
        "competitors": competitors,
        "status": status,
        "message": message,
        "search_results": tavily_results,
        "search_succeeded": search_succeeded,
    }
