from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class WebsiteAnalysisRequest(BaseModel):
    url: HttpUrl


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_required_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("This field must contain a non-empty explanation.")
    return normalized


def _validate_required_items(values: list[str]) -> list[str]:
    normalized = [value.strip() for value in values if value.strip()]
    if not normalized:
        raise ValueError("Provide at least one evidence-based item or an explanation.")
    return normalized


class BusinessOverview(StrictModel):
    business_name: str | None = None
    business_description: str | None = None
    business_category: str | None = None
    website_purpose: str | None = None
    brand_advantages: list[str] = Field(default_factory=list)
    brand_positioning: str | None = None

class Competitor(StrictModel):
    competitor_name: str = Field(min_length=1)
    competitor_website: str = Field(min_length=1)
    description: str = Field(min_length=1)
    products_and_services: list[str] = Field(min_length=1)
    strengths: list[str] = Field(min_length=1)
    competitive_advantages: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(min_length=1)
    comparison_with_analyzed_business: str = Field(min_length=1)

    @field_validator(
        "competitor_name",
        "competitor_website",
        "description",
        "comparison_with_analyzed_business",
    )
    @classmethod
    def require_nonempty_text(cls, value: str) -> str:
        return _validate_required_text(value)

    @field_validator("products_and_services", "strengths", "weaknesses")
    @classmethod
    def require_nonempty_items(cls, values: list[str]) -> list[str]:
        return _validate_required_items(values)


class SearchQuery(StrictModel):
    query: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    search_intent: str = Field(min_length=1)
    business_relevance: str = Field(min_length=1)
    relevance_score: float = Field(default=0.9, ge=0, le=1)
    target_audience: str = Field(min_length=1)

    @field_validator("platform")
    @classmethod
    def normalize_platform(cls, value: str) -> str:
        normalized = value.strip()
        aliases = {
            "Google": "Google Search",
            "X": "X (Twitter)",
            "Twitter": "X (Twitter)",
        }
        return aliases.get(normalized, normalized)


class SEOAnalysis(StrictModel):
    primary_keywords: list[str] = Field(default_factory=list)
    secondary_keywords: list[str] = Field(default_factory=list)
    long_tail_keywords: list[str] = Field(default_factory=list)
    suggested_seo_title: str | None = None
    suggested_meta_description: str | None = None
    content_improvements: list[str] = Field(default_factory=list)
    content_ideas: list[str] = Field(default_factory=list)


class ProductOrService(StrictModel):
    name: str = Field(min_length=1)
    description: str | None = None
    industry: str | None = None
    target_customer: str | None = None
    benefits: list[str] = Field(default_factory=list)


class TargetAudience(StrictModel):
    primary_audience: str | None = None
    secondary_audience: str | None = None
    industries: list[str] = Field(default_factory=list)
    business_types: list[str] = Field(default_factory=list)
    customer_profiles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    customer_needs: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    audience_segments: list[str] = Field(default_factory=list)


class SWOTAnalysis(StrictModel):
    strengths: list[str] = Field(min_length=1)
    weaknesses: list[str] = Field(min_length=1)
    opportunities: list[str] = Field(min_length=1)
    threats: list[str] = Field(min_length=1)

    @field_validator("strengths", "weaknesses", "opportunities", "threats")
    @classmethod
    def require_nonempty_items(cls, values: list[str]) -> list[str]:
        return _validate_required_items(values)


class WebsiteAnalysis(StrictModel):
    model_config = ConfigDict(extra="forbid")

    business_overview: BusinessOverview
    competitor_analysis: list[Competitor] = Field(default_factory=list, max_length=5)
    search_queries: list[SearchQuery] = Field(min_length=5, max_length=5)
    seo_analysis: SEOAnalysis
    products_and_services: list[ProductOrService] = Field(default_factory=list, max_length=5)
    target_audience: TargetAudience
    swot_analysis: SWOTAnalysis

    @model_validator(mode="after")
    def require_supported_platforms(self) -> "WebsiteAnalysis":
        required = {"Google Search", "Facebook", "Instagram", "LinkedIn", "X (Twitter)"}
        platform_aliases = {
            "Google": "Google Search",
            "X": "X (Twitter)",
            "Twitter": "X (Twitter)",
        }
        platforms = {
            platform_aliases.get(item.platform.strip(), item.platform.strip())
            for item in self.search_queries
        }
        if platforms != required:
            raise ValueError(
                "search_queries must contain exactly one query for Google Search, "
                "Facebook, Instagram, LinkedIn, and X (Twitter)"
            )
        return self


class ExtractedWebsiteData(StrictModel):
    title: str = ""
    meta_description: str = ""
    open_graph: dict[str, str] = Field(default_factory=dict)
    headings: list[str] = Field(default_factory=list)
    content: str = ""


class PublicSearchResult(StrictModel):
    title: str
    url: str
    content: str
    query: str


class AnalysisSources(StrictModel):
    direct_extraction_success: bool
    extraction_status: str
    extraction_error: str | None = None
    tavily_search_used: bool
    search_results: list[PublicSearchResult] = Field(default_factory=list)


class WebsiteAnalysisResponse(StrictModel):
    success: bool
    message: str
    website: str
    extracted_data: ExtractedWebsiteData
    sources: AnalysisSources
    analysis: WebsiteAnalysis
    competitor_analysis_status: Literal[
        "complete",
        "incomplete",
        "insufficient_search_results",
        "search_failed",
        "analysis_failed",
    ] = "insufficient_search_results"
    competitor_analysis_message: str = (
        "We could not identify reliable competitors from the available search results."
    )
