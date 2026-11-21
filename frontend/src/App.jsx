import { useEffect, useState } from "react";
import Dashboard from "./components/Dashboard.jsx";
import Footer from "./components/Footer.jsx";
import Header from "./components/Header.jsx";
import Loading from "./components/Loading.jsx";
import URLInput from "./components/URLInput.jsx";

const API_BASE_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const API_URL = `${API_BASE_URL}/link-analysis`;

function getApiError(payload, status) {
  if (typeof payload?.detail === "string" && payload.detail.trim()) return payload.detail;
  if (Array.isArray(payload?.detail)) {
    const messages = payload.detail.map((item) => item?.msg).filter(Boolean);
    if (messages.length) return messages.join(" ");
  }
  if (typeof payload?.message === "string" && payload.message.trim()) return payload.message;
  if (status === 400) return "Enter a valid website URL and try again.";
  if (status === 401) return "This website requires authentication to view its content.";
  if (status === 403) return "This website restricts automated access, so complete extraction may not be possible.";
  if (status === 404) return "The requested website page could not be found.";
  if (status === 422) return "Website content could not be extracted or was insufficient for analysis.";
  if (status === 429) return "The website or analysis service is limiting requests. Please try again later.";
  if (status === 502) return "The website could not provide content right now.";
  if (status === 503) return "The website is temporarily unavailable or could not be reached.";
  if (status === 504) return "The request timed out. Please try again.";
  if (status === 405) return "The analysis endpoint does not accept this request method.";
  if (status >= 500) return "An internal analysis error occurred. Please try again later.";
  return "The analysis request could not be completed. Please try again.";
}

function isAnalysisResponse(payload) {
  return payload
    && payload.success === true
    && typeof payload.website === "string"
    && payload.extracted_data
    && typeof payload.extracted_data === "object"
    && payload.analysis
    && typeof payload.analysis === "object";
}

export default function App() {
  const [result, setResult] = useState(null);
  const [loadingUrl, setLoadingUrl] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    document.title = result ? "Website Insights | Insightly" : "AI Website Analyzer | Insightly";
  }, [result]);

  async function analyzeWebsite(url) {
    setError("");
    setResult(null);
    setLoadingUrl(url);

    try {
      let response;
      try {
        response = await fetch(API_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url }),
        });
      } catch {
        throw new Error(
          "Could not connect to the analysis service. Please try again in a moment."
        );
      }

      const responseText = await response.text();
      let payload;
      try {
        payload = responseText ? JSON.parse(responseText) : null;
      } catch {
        if (!response.ok) throw new Error(getApiError(null, response.status));
        throw new Error("The backend returned an unreadable response. Check that it returned valid JSON.");
      }

      if (!response.ok) throw new Error(getApiError(payload, response.status));
      if (payload === null) throw new Error("The backend returned an empty response. Check the API response.");
      if (!isAnalysisResponse(payload)) {
        throw new Error(payload?.success === false
          ? getApiError(payload, response.status)
          : "The backend response is missing required analysis data. Please check the API response.");
      }
      setResult(payload);
    } catch (requestError) {
      setError(requestError.message || "Something went wrong while analyzing this website. Please try again.");
    } finally {
      setLoadingUrl("");
    }
  }

  function resetAnalysis() {
    setResult(null);
    setError("");
    setLoadingUrl("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <>
      <Header onHome={resetAnalysis} />
      {loadingUrl ? (
        <main className="page-main"><Loading url={loadingUrl} /></main>
      ) : result ? (
        <Dashboard result={result} onAnalyzeAnother={resetAnalysis} />
      ) : (
        <main className="page-main" id="home">
          <section className="hero-section">
            <div className="hero-content">
              <div className="hero-pill"><span className="sparkle" aria-hidden="true">✦</span> YOUR WEBSITE, UNDERSTOOD</div>
              <h1>Analyze any website<br />with <span>AI-powered clarity.</span></h1>
              <p className="hero-description">Uncover business insights, competitors, SEO opportunities, and the people behind every click — all in one thoughtful report.</p>
              <URLInput onAnalyze={analyzeWebsite} />
              {error && <div className="error-banner" role="alert"><span className="error-icon" aria-hidden="true">!</span><p>{error}</p><button type="button" onClick={() => analyzeWebsite(document.getElementById("website-url")?.value.trim())}>Try again</button></div>}
              <div className="trust-row"><span className="trust-icon" aria-hidden="true">⌁</span><span>Public website content only</span><span className="trust-divider" /><span>No API key required in your browser</span></div>
            </div>
            <div className="hero-visual" aria-hidden="true">
              <div className="visual-glow" />
              <div className="orbit orbit-one" /><div className="orbit orbit-two" />
              <div className="visual-card visual-main-card">
                <div className="visual-window"><span /><span /><span /><div>website.com</div><b>✦</b></div>
                <div className="visual-card-content"><div className="visual-label"><span className="mini-star">✦</span> AI WEBSITE REPORT</div><div className="visual-heading-line" /><div className="visual-line long" /><div className="visual-line medium" /><div className="visual-chart"><span /><span /><span /><span /><span /><span /><span /></div><div className="visual-tags"><i /><i /><i /></div></div>
              </div>
              <div className="float-chip chip-business"><span>◈</span><div><b>Business insights</b><small>Clear, actionable overview</small></div></div>
              <div className="float-chip chip-seo"><span>↗</span><div><b>SEO opportunities</b><small>Find room to grow</small></div></div>
              <div className="visual-spark spark-a">✦</div><div className="visual-spark spark-b">✧</div>
            </div>
          </section>
          <section className="feature-section" id="features">
            <div className="feature-heading"><p className="eyebrow">Everything in one view</p><h2>From first impression to<br /><span>deeper opportunity.</span></h2><p>Get a structured view of the signals that matter, without digging through pages of data.</p></div>
            <div className="feature-grid">
              <article className="feature-card"><span className="feature-icon purple">◫</span><h3>Business overview</h3><p>Understand what a website offers and the purpose it serves.</p></article>
              <article className="feature-card"><span className="feature-icon blue">◎</span><h3>Competitive landscape</h3><p>See potential competitors and how their positioning compares.</p></article>
              <article className="feature-card"><span className="feature-icon violet">⌕</span><h3>SEO opportunities</h3><p>Explore keywords, content ideas, and on-page improvements.</p></article>
              <article className="feature-card"><span className="feature-icon indigo">⊞</span><h3>Audience &amp; SWOT</h3><p>Review potential audiences, their needs, and strategic signals.</p></article>
            </div>
          </section>
        </main>
      )}
      <Footer />
    </>
  );
}
