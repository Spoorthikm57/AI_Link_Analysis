from typing import Any


INSUFFICIENT_INFORMATION = (
    "Insufficient publicly available information to determine this accurately."
)


def _meaningful(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _meaningful_text(value: Any) -> bool:
    if not _meaningful(value):
        return False
    return str(value).strip().lower() not in {
        "null",
        "none",
        "n/a",
        "not available",
        "unknown",
    }


def _meaningful_list(value: Any) -> bool:
    return isinstance(value, list) and any(
        isinstance(item, str) and bool(item.strip()) for item in value
    )


def validate_analysis_completeness(
    analysis: dict[str, Any],
) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}

    business = analysis.get("business_overview")
    business = business if isinstance(business, dict) else {}
    business_fields = [
        "business_name",
        "business_description",
        "business_category",
        "website_purpose",
        "brand_advantages",
        "brand_positioning",
    ]
    business_missing = []
    for field in business_fields:
        value = business.get(field)
        if field == "brand_advantages":
            complete = _meaningful_list(value)
        else:
            complete = _meaningful_text(value)
        if not complete:
            business_missing.append(field)
    if business_missing:
        missing["business_overview"] = business_missing

    competitors = analysis.get("competitor_analysis")
    competitors_are_list = isinstance(competitors, list)
    competitors = competitors if competitors_are_list else []
    competitor_missing = []
    if not competitors_are_list or len(competitors) < 3:
        competitor_missing.append("at least 3 relevant competitors")
    required_competitor_fields = [
        "competitor_name",
        "competitor_website",
        "description",
        "strengths",
        "weaknesses",
        "comparison_with_analyzed_business",
    ]
    for index, competitor in enumerate(competitors[:5]):
        if not isinstance(competitor, dict):
            competitor_missing.append(f"competitor_{index + 1}")
            continue
        for field in required_competitor_fields:
            value = competitor.get(field)
            complete = _meaningful_list(value) if field in {"strengths", "weaknesses"} else _meaningful_text(value)
            if not complete:
                competitor_missing.append(f"competitor_{index + 1}.{field}")
    if competitor_missing:
        missing["competitor_analysis"] = competitor_missing

    queries = analysis.get("search_queries")
    queries = queries if isinstance(queries, list) else []
    query_missing = []
    required_platforms = {"Google Search", "Facebook", "Instagram", "LinkedIn", "X (Twitter)"}
    platforms = set()
    for index, query in enumerate(queries):
        if not isinstance(query, dict):
            query_missing.append(f"search_query_{index + 1}")
            continue
        platform = str(query.get("platform", "")).strip()
        if platform == "Google":
            platform = "Google Search"
        elif platform in {"X", "Twitter"}:
            platform = "X (Twitter)"
        platforms.add(platform)
        for field in ("query", "platform", "search_intent", "business_relevance", "target_audience"):
            if not _meaningful_text(query.get(field)):
                query_missing.append(f"search_query_{index + 1}.{field}")
    if len(queries) != 5:
        query_missing.append("exactly 5 search query entries")
    if platforms != required_platforms:
        query_missing.append("one entry each for Google Search, Facebook, Instagram, LinkedIn, and X (Twitter)")
    if query_missing:
        missing["search_queries"] = list(dict.fromkeys(query_missing))

    seo = analysis.get("seo_analysis")
    seo = seo if isinstance(seo, dict) else {}
    seo_missing = []
    for field in ("primary_keywords", "secondary_keywords", "long_tail_keywords", "content_improvements", "content_ideas"):
        if not _meaningful_list(seo.get(field)):
            seo_missing.append(field)
    for field in ("suggested_seo_title", "suggested_meta_description"):
        if not _meaningful_text(seo.get(field)):
            seo_missing.append(field)
    if seo_missing:
        missing["seo_analysis"] = seo_missing

    products = analysis.get("products_and_services")
    products = products if isinstance(products, list) else []
    product_missing = []
    if not products:
        product_missing.append("at least 1 relevant product or service")
    for index, product in enumerate(products[:5]):
        if not isinstance(product, dict) or not _meaningful_text(product.get("name")):
            product_missing.append(f"products_and_services_{index + 1}.name")
    if product_missing:
        missing["products_and_services"] = list(dict.fromkeys(product_missing))

    audience = analysis.get("target_audience")
    audience = audience if isinstance(audience, dict) else {}
    audience_missing = []
    audience_text_fields = ("primary_audience", "secondary_audience")
    audience_list_fields = (
        "industries",
        "business_types",
        "customer_profiles",
        "locations",
        "customer_needs",
        "pain_points",
        "interests",
        "audience_segments",
    )
    for field in audience_text_fields:
        if not _meaningful_text(audience.get(field)):
            audience_missing.append(field)
    for field in audience_list_fields:
        if not _meaningful_list(audience.get(field)):
            audience_missing.append(field)
    if audience_missing:
        missing["target_audience"] = audience_missing

    swot = analysis.get("swot_analysis")
    swot = swot if isinstance(swot, dict) else {}
    swot_missing = []
    for field in ("strengths", "weaknesses", "opportunities", "threats"):
        if not _meaningful_list(swot.get(field)):
            swot_missing.append(field)
    if swot_missing:
        missing["swot_analysis"] = swot_missing

    return missing