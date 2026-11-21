import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.services import website_extractor


class WebsiteExtractorTests(unittest.IsolatedAsyncioTestCase):
    async def extract_with(
        self,
        handler,
        url="https://example.com",
        public_addresses=True,
    ):
        original_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)

        with patch.object(
            website_extractor.httpx,
            "AsyncClient",
            side_effect=lambda **kwargs: original_client(
                transport=transport,
                **kwargs,
            ),
        ), patch.object(
            website_extractor,
            "_hostname_has_only_public_addresses",
            new=AsyncMock(return_value=public_addresses),
        ):
            return await website_extractor.extract_website_content(url)

    async def test_extracts_metadata_headings_and_clean_text(self):
        page = """
        <html><head>
          <title> Example title <b>with markup</b> </title>
          <meta name="description" content="A useful description">
          <meta property="og:site_name" content="Example">
          <meta property="og:image" content="https://example.com/image.jpg">
          <script>script-only content</script><style>.hidden{}</style>
        </head><body>
          <nav>Navigation clutter</nav><main><h1>Main heading</h1>
          <h2>Section heading</h2><p>Useful page text.</p></main>
          <svg>vector clutter</svg><footer role="contentinfo">Footer clutter</footer>
        </body></html>
        """
        observed_headers = {}

        def handler(request):
            observed_headers.update(request.headers)
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                text=page,
            )

        result = await self.extract_with(handler)

        self.assertTrue(result["success"])
        self.assertEqual(result["title"], "Example title with markup")
        self.assertEqual(result["meta_description"], "A useful description")
        self.assertEqual(result["open_graph"]["site_name"], "Example")
        self.assertEqual(result["headings"], ["Main heading", "Section heading"])
        self.assertIn("Useful page text.", result["content"])
        self.assertNotIn("Navigation clutter", result["content"])
        self.assertNotIn("script-only content", result["content"])
        self.assertIn("Mozilla/5.0", observed_headers["user-agent"])
        self.assertIn("en-US", observed_headers["accept-language"])

    async def test_uses_open_graph_as_metadata_fallback(self):
        def handler(request):
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text='<meta property="og:title" content="Public title">'
                '<meta property="og:description" content="Public description">',
            )

        result = await self.extract_with(handler)

        self.assertTrue(result["success"])
        self.assertEqual(result["title"], "Public title")
        self.assertEqual(result["meta_description"], "Public description")
        self.assertEqual(result["content"], "")

    async def test_http_errors_are_classified(self):
        cases = {
            401: "authentication_required",
            403: "access_restricted",
            404: "not_found",
            429: "rate_limited",
            500: "upstream_server_error",
        }
        for status, expected_code in cases.items():
            with self.subTest(status=status):
                result = await self.extract_with(
                    lambda request: httpx.Response(
                        status,
                        request=request,
                        headers={"content-type": "text/html"},
                    )
                )
                self.assertFalse(result["success"])
                self.assertEqual(result["error_code"], expected_code)

    async def test_detects_login_redirect_restriction_and_empty_content(self):
        def login_handler(request):
            if request.url.path == "/login":
                return httpx.Response(
                    200,
                    headers={"content-type": "text/html"},
                    text="<title>Sign in</title><p>Please sign in.</p>",
                    request=request,
                )
            return httpx.Response(
                302,
                headers={"location": "https://example.com/login"},
                request=request,
            )

        login_result = await self.extract_with(
            login_handler
        )
        blocked_result = await self.extract_with(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<title>Access Denied</title><p>Access denied</p>",
                request=request,
            )
        )
        empty_result = await self.extract_with(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<html><body><script>render()</script></body></html>",
                request=request,
            )
        )

        self.assertEqual(login_result["error_code"], "authentication_required")
        self.assertEqual(blocked_result["error_code"], "access_restricted")
        self.assertEqual(empty_result["error_code"], "no_extractable_content")

    async def test_detects_common_block_pages_and_metadata_only_shells(self):
        blocked_result = await self.extract_with(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<title>Your request has been blocked</title>",
                request=request,
            )
        )
        shell_result = await self.extract_with(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<title>Social Network</title><div id='root'></div>",
                request=request,
            )
        )

        self.assertEqual(blocked_result["error_code"], "access_restricted")
        self.assertEqual(shell_result["error_code"], "no_extractable_content")

    async def test_rejects_private_addresses_and_redirect_targets(self):
        private_result = await website_extractor.extract_website_content(
            "http://127.0.0.1"
        )
        redirect_result = await self.extract_with(
            lambda request: httpx.Response(
                302,
                headers={"location": "http://127.0.0.1/admin"},
                request=request,
            )
        )

        self.assertEqual(private_result["error_code"], "invalid_url")
        self.assertEqual(redirect_result["error_code"], "access_restricted")

    async def test_rejects_urls_containing_credentials(self):
        result = await website_extractor.extract_website_content(
            "https://user:password@example.com"
        )

        self.assertEqual(result["error_code"], "invalid_url")

    async def test_rejects_public_hostname_resolving_to_private_ip(self):
        result = await self.extract_with(
            lambda request: self.fail("Private DNS result must be rejected before requesting"),
            public_addresses=False,
        )

        self.assertEqual(result["error_code"], "invalid_url")


if __name__ == "__main__":
    unittest.main()
