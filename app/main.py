from contextlib import asynccontextmanager
import logging
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas import WebsiteAnalysisRequest, WebsiteAnalysisResponse
from app.services.competitor_service import discover_competitors
from app.services.llm_service import (
    analyze_website_with_ai,
    build_partial_analysis,
    close_groq_client,
)
from app.services.search_service import (
    close_search_client,
    search_company_information,
)
from app.services.website_extractor import extract_website_content

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_groq_client()
    await close_search_client()


app = FastAPI(
    title="AI-Powered Website Link Analysis API",
    description="Analyze websites using AI and generate business insights",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://ai-link-analysis-frontend.onrender.com",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def handle_invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    validation_summary = [
        (error.get("type"), error.get("loc"), error.get("msg"))
        for error in exc.errors()
    ]
    logger.warning("Invalid analysis request: %s", validation_summary)
    return JSONResponse(
        status_code=400,
        content={"detail": "Enter a valid website URL to analyze."},
    )


@app.get("/")
def home():
    return {
        "message": "AI Website Link Analysis API is running!"
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/link-analysis", response_model=WebsiteAnalysisResponse)
async def analyze_website(request: WebsiteAnalysisRequest):
    website_url = str(request.url)
    hostname = urlsplit(website_url).hostname or "unknown host"
    try:
        website_data = await extract_website_content(website_url)
    except Exception:
        logger.exception("Unexpected extraction service failure: host=%s", hostname)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while extracting website content.",
        ) from None

    extraction_succeeded = bool(website_data.get("success"))
    extraction_error_code = website_data.get("error_code")
    if extraction_error_code == "invalid_url":
        raise HTTPException(
            status_code=400,
            detail=website_data.get("error", "Enter a valid public website URL."),
        )

    content_size = sum(
        len(str(value).strip())
        for value in (
            website_data.get("content", ""),
            website_data.get("title", ""),
            website_data.get("meta_description", ""),
            " ".join(website_data.get("headings", [])),
        )
    )
    direct_content_is_sufficient = extraction_succeeded and content_size >= 120
    search_results = []
    tavily_search_used = False
    extraction_status = "success"
    if direct_content_is_sufficient:
        try:
            search_result = await search_company_information(
                website_url,
                website_data,
                discovery_only=True,
            )
        except Exception:
            logger.exception(
                "Optional Tavily competitor discovery failed: host=%s",
                hostname,
            )
        else:
            if search_result.get("success") and search_result.get("results"):
                search_results = list(search_result["results"])
                tavily_search_used = True
            else:
                logger.info(
                    "Optional Tavily competitor discovery returned no results: host=%s code=%s",
                    hostname,
                    search_result.get("error_code"),
                )
    else:
        extraction_status = (
            "insufficient_content" if extraction_succeeded else str(extraction_error_code or "failed")
        )
        logger.info(
            "Using Tavily fallback: host=%s extraction_status=%s",
            hostname,
            extraction_status,
        )
        try:
            search_result = await search_company_information(website_url, website_data)
        except Exception:
            logger.exception("Unexpected Tavily search service failure: host=%s", hostname)
            search_result = {
                "success": False,
                "error_code": "unavailable",
                "error": "Public search could not provide information for this website.",
            }

        if not search_result.get("success"):
            logger.warning(
                "Tavily fallback failed: host=%s code=%s",
                hostname,
                search_result.get("error_code"),
            )
            search_results = []
            tavily_search_used = False
        else:
            search_results = list(search_result.get("results", []))
            tavily_search_used = bool(search_results)

    ai_input = dict(website_data)
    ai_input.update(
        {
            "direct_extraction_success": direct_content_is_sufficient,
            "extraction_status": extraction_status,
            "search_results": search_results,
        }
    )
    if not direct_content_is_sufficient and not search_results:
        ai_result = {
            "success": True,
            "analysis": build_partial_analysis(ai_input),
            "partial": True,
            "error": "No sufficient direct or public search evidence was available.",
        }
    else:
        try:
            ai_result = await analyze_website_with_ai(ai_input)
        except Exception:
            logger.exception("Unexpected AI analysis service failure: host=%s", hostname)
            ai_result = {
                "success": True,
                "analysis": build_partial_analysis(ai_input),
                "partial": True,
                "error": "The AI analysis service was unavailable.",
            }

    if not ai_result["success"]:
        status_codes = {
            "rate_limit": 429,
            "timeout": 504,
            "connection_error": 503,
            "invalid_api_key": 500,
            "invalid_response": 503,
        }
        error_messages = {
            "rate_limit": "The analysis service is limiting requests. Please try again later.",
            "timeout": "The analysis request timed out. Please try again.",
            "connection_error": "The analysis service is temporarily unavailable.",
            "invalid_api_key": "Website analysis is temporarily unavailable. Please contact the application administrator.",
            "invalid_response": "The analysis service could not create a complete report from this website.",
            "model_or_request_error": "The analysis service could not process this request. Please try again later.",
            "groq_api_error": "The analysis service is temporarily unavailable.",
        }
        logger.error(
            "AI analysis failed: host=%s code=%s error=%s",
            hostname,
            ai_result.get("error_code"),
            ai_result.get("error"),
        )
        error_code = ai_result.get("error_code")
        raise HTTPException(
            status_code=status_codes.get(error_code, 502),
            detail=error_messages.get(
                error_code,
                "The analysis service could not complete this request.",
            ),
        )

    try:
        competitor_result = await discover_competitors(
            website_url,
            ai_result["analysis"],
            website_data,
        )
    except Exception:
        logger.exception(
            "[COMPETITOR] Unexpected competitor analysis failure: host=%s",
            hostname,
        )
        competitor_result = {
            "competitors": [],
            "status": "search_failed",
            "message": (
                "Competitor discovery could not be completed because of an "
                "unexpected service error. Please retry."
            ),
            "search_results": [],
            "search_succeeded": False,
        }

    ai_result["analysis"]["competitor_analysis"] = competitor_result["competitors"]
    known_urls = {item.get("url") for item in search_results if isinstance(item, dict)}
    for item in competitor_result["search_results"]:
        result_url = item.get("url")
        if result_url and result_url not in known_urls:
            search_results.append(item)
            known_urls.add(result_url)
    tavily_search_used = tavily_search_used or competitor_result["search_succeeded"]

    return {
        "success": True,
        "message": (
            "Partial website analysis returned using public search results."
            if ai_result.get("partial") and tavily_search_used
            else (
                "Website analyzed successfully using public search results."
                if tavily_search_used
                else (
                    "Partial analysis returned; sufficient Groq evidence was not available."
                    if ai_result.get("partial")
                    else "Website analyzed successfully."
                )
            )
        ),
        "website": website_data.get("url", website_url),
        "extracted_data": {
            "title": website_data.get("title", ""),
            "meta_description": website_data.get("meta_description", ""),
            "open_graph": website_data.get("open_graph", {}),
            "headings": website_data.get("headings", []),
            "content": website_data.get("content", ""),
        },
        "sources": {
            "direct_extraction_success": direct_content_is_sufficient,
            "extraction_status": extraction_status,
            "extraction_error": (
                website_data.get("error") if not direct_content_is_sufficient else None
            ),
            "tavily_search_used": tavily_search_used,
            "search_results": search_results,
        },
        "analysis": ai_result["analysis"],
        "competitor_analysis_status": competitor_result["status"],
        "competitor_analysis_message": competitor_result["message"],
    }
