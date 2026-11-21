import { useState } from "react";
import {
  Competitors,
  Overview,
  ProductsServices,
  SearchQueries,
  SEOAnalysis,
  SWOTAnalysis,
  TargetAudience,
} from "./AnalysisSections.jsx";

const sections = [
  { id: "overview", label: "Overview", icon: "◫" },
  { id: "competitors", label: "Competitors", icon: "◎" },
  { id: "queries", label: "Search queries", icon: "⌕" },
  { id: "seo", label: "SEO analysis", icon: "↗" },
  { id: "products", label: "Products & services", icon: "◇" },
  { id: "audience", label: "Target audience", icon: "♧" },
  { id: "swot", label: "SWOT analysis", icon: "⊞" },
];

export default function Dashboard({ result, onAnalyzeAnother }) {
  const [activeSection, setActiveSection] = useState("overview");
  const [feedback, setFeedback] = useState("");
  const { analysis, extracted_data: extracted, website } = result;

  async function copyReport() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(result, null, 2));
      setFeedback("Report copied to clipboard.");
    } catch {
      setFeedback("Could not access the clipboard. Check your browser permissions.");
    }
  }

  function downloadReport() {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = `${new URL(website).hostname.replace(/[^a-z0-9.-]/gi, "-")}-analysis.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(downloadUrl);
    setFeedback("Your JSON report has been downloaded.");
  }

  let content;
  switch (activeSection) {
    case "competitors":
      content = (
        <Competitors
          competitors={analysis.competitor_analysis}
          status={result.competitor_analysis_status}
          message={result.competitor_analysis_message}
        />
      );
      break;
    case "queries":
      content = <SearchQueries queries={analysis.search_queries} />;
      break;
    case "seo":
      content = <SEOAnalysis seo={analysis.seo_analysis} />;
      break;
    case "products":
      content = <ProductsServices products={analysis.products_and_services} />;
      break;
    case "audience":
      content = <TargetAudience audience={analysis.target_audience} />;
      break;
    case "swot":
      content = <SWOTAnalysis swot={analysis.swot_analysis} />;
      break;
    default:
      content = <Overview website={website} extracted={extracted} business={analysis.business_overview} sources={result.sources} />;
  }

  return (
    <main className="dashboard-shell" id="results">
      <div className="dashboard-topline">
        <div>
          <p className="eyebrow">Your analysis report</p>
          <h1>Website insights</h1>
          <p className="dashboard-url">{website}</p>
        </div>
        <div className="report-actions">
          <button className="secondary-button" type="button" onClick={copyReport}><span aria-hidden="true">▣</span> Copy results</button>
          <button className="secondary-button" type="button" onClick={downloadReport}><span aria-hidden="true">↓</span> Download JSON</button>
          <button className="primary-button compact-button" type="button" onClick={onAnalyzeAnother}>New analysis <span aria-hidden="true">＋</span></button>
        </div>
      </div>
      <p className="analysis-status" role="status">
        {result.message || "Website analyzed successfully."}
      </p>
      {feedback && <p className="action-feedback" role="status">{feedback}</p>}
      <div className="dashboard-layout">
        <aside className="dashboard-sidebar" aria-label="Analysis sections">
          <p className="sidebar-label">REPORT SECTIONS</p>
          {sections.map((section) => <button
            type="button"
            className={`sidebar-link${activeSection === section.id ? " active" : ""}`}
            key={section.id}
            onClick={() => setActiveSection(section.id)}
            aria-current={activeSection === section.id ? "page" : undefined}
          ><span className="sidebar-icon" aria-hidden="true">{section.icon}</span>{section.label}<span className="sidebar-chevron" aria-hidden="true">›</span></button>)}
          <div className="sidebar-tip"><span aria-hidden="true">✦</span><p>AI-generated insights are based on the content available on the analyzed website.</p></div>
        </aside>
        <div className="dashboard-content">{content}</div>
      </div>
    </main>
  );
}
