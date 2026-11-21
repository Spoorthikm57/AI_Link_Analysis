# AI Website Link Analysis API

A FastAPI service that extracts public website content and creates structured business, competitor, SEO, audience, and SWOT analysis using Groq.

## Configure and run (Windows PowerShell)

From the project directory, create the virtual environment if needed, then install
the project dependencies into it:

```powershell
Set-Location "C:\Users\m6793\Downloads\MY PROJECTS\AI_Link_Analysis"
if (-not (Test-Path .\venv\Scripts\python.exe)) { py -3 -m venv .\venv }
.\venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

Set both keys in the local `.env` file; neither key is exposed to the browser. Do not commit `.env`; it is ignored by Git. The Groq model defaults to `openai/gpt-oss-120b`. Override it by setting `GROQ_MODEL` in `.env` if needed.

```dotenv
GROQ_API_KEY=your_groq_api_key
TAVILY_API_KEY=your_tavily_api_key
# Optional:
GROQ_MODEL=openai/gpt-oss-120b
```

Test the Groq connection, then start the API:

```powershell
.\venv\Scripts\python.exe .\test_groq.py
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Swagger UI is available at <http://127.0.0.1:8000/docs>. Submit a request to `POST /link-analysis` with:

```json
{
  "url": "https://example.com"
}
```

The extractor follows public redirects, checks resolved addresses to reject local and
private-network targets, and collects page title/description, Open Graph metadata,
headings, and readable server-rendered text. It removes common page boilerplate and
caps the downloaded HTML and extracted text.

The backend uses the Tavily Python SDK to improve competitor discovery. When direct
website extraction succeeds, it makes one focused discovery search; if extraction
fails or returns too little content, it runs six broader company searches instead.
After Groq identifies up to two potential competitors, Tavily makes two combined
research searches per competitor (official website/products/features, then strengths,
weaknesses, and comparison). This caps Tavily at five searches for a directly
extractable site or ten when extraction needs the broader fallback. Results are
deduplicated and bounded before being passed to Groq. Competitor and SWOT fields are
required by response validation; incomplete generations receive a correction attempt.
Verified source information is distinguished from analysis, which is labeled
`AI-generated inference`. Reports include the collected references in the response's
`sources` object and the dashboard. LinkedIn login, CAPTCHA, and other access
restrictions are not bypassed; only publicly indexed information is searched. A
directly extractable site can still be analyzed if optional Tavily discovery is
unavailable; when extraction fails, Tavily results are required to avoid generating
an unsupported report.

Run the focused backend tests with:

```powershell
.\venv\Scripts\python.exe -m unittest test_website_extractor test_search_service test_llm_service
```

## Run the React frontend (Windows PowerShell)

Open a second PowerShell terminal in the project directory and run:

```powershell
Set-Location "C:\Users\m6793\Downloads\MY PROJECTS\AI_Link_Analysis\frontend"
npm install
npm run dev
```

Open <http://localhost:5173>. Keep the FastAPI server running in the first terminal at <http://127.0.0.1:8000>; the frontend sends a JSON `POST` request to `/link-analysis` there. The optional `VITE_API_URL` environment variable can override the API base URL (for example, `http://127.0.0.1:8000`).

FastAPI allows cross-origin requests from `http://localhost:5173` and `http://127.0.0.1:5173` for local development. If you change Vite's port or deploy the frontend elsewhere, add its exact origin to `allow_origins` in `app/main.py` and restart FastAPI.

The dashboard uses the API response directly: website title and description come from `extracted_data`; provenance and search result references come from `sources`; the business overview, competitor analysis, search queries, SEO, products and services, audience, and SWOT sections come from `analysis`. Use the dashboard navigation to switch sections, or download/copy the complete response.

To try the Tavily fallback, open <http://127.0.0.1:8000/docs>, expand `POST /link-analysis`, choose **Try it out**, and submit:

```json
{
  "url": "https://www.linkedin.com/company/microsoft/"
}
```

Publicly indexed company results are used if LinkedIn blocks extraction. The returned
`sources.extraction_status` identifies the extraction outcome, while
`sources.search_results` contains the public result titles, URLs, snippets, and
queries. The report's provenance section distinguishes those results from content
directly extracted from a website. Do not expect private profile or login-only data.

Also test a normal website such as `https://www.python.org` for direct extraction,
and a malformed URL in `/docs` to verify request validation. Invalid/private URLs
are rejected before search or LLM calls.

Create a production build with:

```powershell
Set-Location "C:\Users\m6793\Downloads\MY PROJECTS\AI_Link_Analysis\frontend"
npm run build
```