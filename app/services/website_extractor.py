import asyncio
import ipaddress
import logging
import re
import socket
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MAX_HTML_BYTES = 2_000_000
MAX_CONTENT_CHARACTERS = 10_000
DNS_TIMEOUT_SECONDS = 5.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
    "Cache-Control": "no-cache",
}
REMOVED_ELEMENTS = (
    "script",
    "style",
    "noscript",
    "svg",
    "iframe",
    "canvas",
    "template",
    "nav",
    "aside",
    "form",
    "button",
)
LOGIN_REDIRECT_PARTS = (
    "/login",
    "/signin",
    "/authwall",
    "/checkpoint",
    "/accounts/login",
    "/session/new",
)
RESTRICTION_PHRASES = (
    "access denied",
    "your request has been blocked",
    "request has been blocked",
    "you have been blocked",
    "access to this page has been denied",
    "verify you are human",
    "verify that you are human",
    "unusual traffic",
    "automated requests",
    "security check",
    "complete the captcha",
    "robot check",
    "please enable javascript",
    "enable javascript and cookies",
)


def _failure(error_code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"success": False, "error_code": error_code, "error": message, **extra}


def _validate_public_url(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "Enter a valid HTTP or HTTPS website URL."
        if parsed.username is not None or parsed.password is not None:
            return "Website URLs containing credentials cannot be analyzed."
        hostname = parsed.hostname.rstrip(".").lower()
        if hostname == "localhost" or hostname.endswith(".localhost"):
            return "Local and private network addresses cannot be analyzed."
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            return None
        if not address.is_global:
            return "Local and private network addresses cannot be analyzed."
    except ValueError:
        return "Enter a valid HTTP or HTTPS website URL."
    return None


async def _hostname_has_only_public_addresses(hostname: str) -> bool | None:
    try:
        addresses = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(
                hostname,
                None,
                type=socket.SOCK_STREAM,
            ),
            timeout=DNS_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, socket.gaierror):
        return None

    return bool(addresses) and all(
        ipaddress.ip_address(address[4][0]).is_global
        for address in addresses
    )


def _meta_content(soup: BeautifulSoup, *, name: str | None = None, prop: str | None = None) -> str:
    if name:
        tag = soup.find("meta", attrs={"name": name})
    else:
        tag = soup.find("meta", attrs={"property": prop})
    return str(tag.get("content", "")).strip() if tag else ""


def _extract_page(html: str | bytes, final_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    open_graph = {
        key: _meta_content(soup, prop=f"og:{key}")
        for key in ("title", "description", "site_name", "type", "url", "image")
    }

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    title = title or open_graph["title"]
    meta_description = (
        _meta_content(soup, name="description")
        or open_graph["description"]
        or _meta_content(soup, name="twitter:description")
    )

    for element in soup(REMOVED_ELEMENTS):
        element.decompose()
    for element in soup.select(
        '[aria-hidden="true"], [hidden], [role="navigation"], [role="banner"], [role="contentinfo"]'
    ):
        element.decompose()

    headings = []
    for heading in soup.find_all(["h1", "h2", "h3"]):
        text = re.sub(r"\s+", " ", heading.get_text(" ", strip=True))
        if text:
            headings.append(text[:300])
        if len(headings) >= 100:
            break

    content = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))
    content = content[:MAX_CONTENT_CHARACTERS]
    return {
        "success": True,
        "url": final_url,
        "title": title[:500],
        "meta_description": meta_description[:2_000],
        "open_graph": {
            key: value[:2_000] for key, value in open_graph.items() if value
        },
        "headings": headings,
        "content": content,
    }


def _has_meaningful_content(page: dict[str, Any]) -> bool:
    return bool(
        page["meta_description"]
        or page["headings"]
        or any(
            value
            for key, value in page["open_graph"].items()
            if key != "image"
        )
        or len(page["content"].strip()) >= 20
    )


def _is_login_redirect(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return any(part in path for part in LOGIN_REDIRECT_PARTS)


async def extract_website_content(url: str) -> dict[str, Any]:
    invalid_url_message = _validate_public_url(url)
    if invalid_url_message:
        return _failure("invalid_url", invalid_url_message)

    hostname = urlsplit(url).hostname or "unknown host"
    timeout = httpx.Timeout(connect=8.0, read=18.0, write=8.0, pool=8.0)

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            headers=REQUEST_HEADERS,
            trust_env=False,
        ) as client:
            current_url = url
            for redirect_count in range(9):
                current_hostname = urlsplit(current_url).hostname
                if current_hostname:
                    public_addresses = await _hostname_has_only_public_addresses(
                        current_hostname
                    )
                    if public_addresses is None:
                        return _failure(
                            "connection_error",
                            "The website hostname could not be resolved.",
                        )
                    if not public_addresses:
                        return _failure(
                            "invalid_url",
                            "The website resolves to a local or private network address.",
                        )

                async with client.stream("GET", current_url) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location or redirect_count == 8:
                            return _failure(
                                "redirect_error",
                                "The website could not complete its redirects.",
                                upstream_status=response.status_code,
                            )
                        current_url = urljoin(str(response.url), location)
                        invalid_redirect = _validate_public_url(current_url)
                        if invalid_redirect:
                            return _failure(
                                "access_restricted",
                                "The website redirected to an address that cannot be analyzed.",
                            )
                        continue

                    status = response.status_code
                    if status in {401, 403, 404, 429}:
                        error_codes = {
                            401: ("authentication_required", "This website requires authentication to view its content."),
                            403: ("access_restricted", "This website limits automated access, so complete content extraction may not be possible."),
                            404: ("not_found", "The requested page was not found on the website."),
                            429: ("rate_limited", "This website is temporarily limiting automated requests. Please try again later."),
                        }
                        code, message = error_codes[status]
                        logger.warning("Website extraction denied: host=%s status=%s", hostname, status)
                        return _failure(code, message, upstream_status=status)
                    if status >= 500:
                        logger.warning("Website server error: host=%s status=%s", hostname, status)
                        return _failure(
                            "upstream_server_error",
                            "The website's server is temporarily unavailable.",
                            upstream_status=status,
                        )
                    if status >= 400:
                        logger.warning("Website returned client error: host=%s status=%s", hostname, status)
                        return _failure(
                            "access_restricted",
                            "This website did not allow the page to be accessed automatically.",
                            upstream_status=status,
                        )
                    if 300 <= status < 400:
                        return _failure(
                            "redirect_error",
                            "The website could not complete its redirect.",
                            upstream_status=status,
                        )

                    content_type = response.headers.get("content-type", "").lower()
                    if content_type and not any(
                        kind in content_type
                        for kind in ("text/html", "application/xhtml+xml")
                    ):
                        return _failure(
                            "no_extractable_content",
                            "This page does not provide extractable HTML content.",
                        )

                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        remaining = MAX_HTML_BYTES - len(body)
                        body.extend(chunk[:remaining])
                        if len(chunk) >= remaining:
                            break

                    html = bytes(body)
                    final_url = str(response.url)
                break

        if _is_login_redirect(final_url):
            logger.warning("Website redirected to login: host=%s", hostname)
            return _failure(
                "authentication_required",
                "This website redirected the request to a sign-in page. Public content may be limited.",
            )

        lowered_html = html[:100_000].decode("ascii", errors="ignore").lower()
        if any(phrase in lowered_html for phrase in RESTRICTION_PHRASES):
            logger.warning("Website presented a bot/access restriction page: host=%s", hostname)
            return _failure(
                "access_restricted",
                "This website limits automated access, so complete content extraction may not be possible.",
            )

        page = _extract_page(html, final_url)
        if not _has_meaningful_content(page):
            logger.warning("No server-rendered website content: host=%s", hostname)
            return _failure(
                "no_extractable_content",
                "No public content was available in the page response. It may require JavaScript rendering or restrict automated access.",
            )
        return page
    except httpx.TimeoutException as exc:
        logger.warning("Website request timed out: host=%s error=%s", hostname, exc)
        return _failure("timeout", "The website took too long to respond.")
    except httpx.TooManyRedirects as exc:
        logger.warning("Website redirect limit reached: host=%s error=%s", hostname, exc)
        return _failure("redirect_error", "The website could not complete its redirects.")
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Website returned HTTP error: host=%s status=%s",
            hostname,
            exc.response.status_code,
        )
        return _failure(
            "upstream_server_error",
            "The website could not provide content for this request.",
            upstream_status=exc.response.status_code,
        )
    except httpx.ConnectError as exc:
        error_text = str(exc).lower()
        if "ssl" in error_text or "certificate" in error_text:
            logger.warning("Website TLS connection failed: host=%s error=%s", hostname, exc)
            return _failure(
                "ssl_error",
                "A secure connection to the website could not be established.",
            )
        logger.warning("Website connection failed: host=%s error=%s", hostname, exc)
        return _failure(
            "connection_error",
            "The website is temporarily unavailable or could not be reached.",
        )
    except httpx.RequestError as exc:
        logger.warning("Website request failed: host=%s error=%s", hostname, exc)
        return _failure(
            "connection_error",
            "The website is temporarily unavailable or could not be reached.",
        )
    except Exception:
        logger.exception("Unexpected website extraction failure: host=%s", hostname)
        return _failure(
            "internal_error",
            "An internal error occurred while extracting website content.",
        )
