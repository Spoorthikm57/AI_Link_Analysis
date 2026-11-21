function EmptyState({ children = "No information was returned for this section." }) {
  return <p className="empty-state">{children}</p>;
}

function Value({ label, value }) {
  return (
    <div className="detail-item">
      <p className="detail-label">{label}</p>
      <p className="detail-value">{typeof value === "string" && value.trim() ? value : "Not provided"}</p>
    </div>
  );
}

function ListItems({ items, emptyText }) {
  const values = Array.isArray(items) ? items.filter((item) => typeof item === "string" && item.trim()) : [];
  return values.length ? (
    <ul className="insight-list">{values.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
  ) : <EmptyState>{emptyText}</EmptyState>;
}

function KeywordTags({ items }) {
  const values = Array.isArray(items) ? items.filter((item) => typeof item === "string" && item.trim()) : [];
  return values.length ? (
    <div className="tag-list">{values.map((item, index) => <span className="keyword-tag" key={`${item}-${index}`}>{item}</span>)}</div>
  ) : <EmptyState>No keywords were returned.</EmptyState>;
}

export function Overview({ website, extracted, business, sources }) {
  const searchResults = Array.isArray(sources?.search_results) ? sources.search_results : [];
  return (
    <div className="section-stack">
      <section className="content-card">
        <div className="section-heading">
          <div><p className="eyebrow">At a glance</p><h2>Website overview</h2></div>
          <span className="success-pill"><span className="status-dot" /> Analysis complete</span>
        </div>
        <div className="website-summary">
          <span className="summary-icon" aria-hidden="true">⌘</span>
          <div className="summary-copy">
            <p className="detail-label">Analyzed website</p>
            <a href={website} target="_blank" rel="noreferrer">{website}</a>
          </div>
        </div>
        <div className="detail-grid">
          <Value label="Website title" value={extracted?.title} />
          <Value label="Meta description" value={extracted?.meta_description} />
        </div>
        {Array.isArray(extracted?.headings) && extracted.headings.some(Boolean) && (
          <div className="subsection-block">
            <p className="detail-label">Page headings</p>
            <div className="tag-list">{extracted.headings.filter(Boolean).map((heading, index) => <span className="soft-tag" key={`${heading}-${index}`}>{heading}</span>)}</div>
          </div>
        )}
      </section>

      <section className="content-card">
        <div className="section-heading"><div><p className="eyebrow">What this business does</p><h2>Business overview</h2></div></div>
        <div className="detail-grid">
          <Value label="Business name" value={business?.business_name} />
          <Value label="Business category" value={business?.business_category} />
          <Value label="Description" value={business?.business_description} />
          <Value label="Website purpose" value={business?.website_purpose} />
          <Value label="Brand positioning" value={business?.brand_positioning} />
        </div>
        <div className="subsection-block"><p className="detail-label">Brand advantages</p><ListItems items={business?.brand_advantages} emptyText="No evidence-backed brand advantages were identified." /></div>
      </section>

      <section className="content-card">
        <div className="section-heading"><div><p className="eyebrow">Evidence and provenance</p><h2>Sources used</h2></div></div>
        <p className="card-description">
          {sources?.direct_extraction_success
            ? "Analysis includes directly extracted public website content."
            : `Direct extraction was unavailable or insufficient (${sources?.extraction_status || "unknown"}). Search results below are third-party public sources, not content extracted directly from this website.`}
        </p>
        {sources?.extraction_error && <p className="muted-copy">{sources.extraction_error}</p>}
        {searchResults.length > 0 ? (
          <ul className="insight-list">
            {searchResults.map((item, index) => {
              let safeUrl = "";
              try {
                const parsed = new URL(item.url);
                if (["http:", "https:"].includes(parsed.protocol)) safeUrl = parsed.href;
              } catch { /* Leave malformed result URLs as plain text. */ }
              return (
                <li key={`${item.url}-${index}`}>
                  <strong>{item.title || "Public search result"}</strong>
                  {safeUrl && <> — <a href={safeUrl} target="_blank" rel="noreferrer">Source ↗</a></>}
                  <p>{item.content || "No snippet was provided."}</p>
                  <small>Found for: {item.query || "company research"}</small>
                </li>
              );
            })}
          </ul>
        ) : <EmptyState>No Tavily search results were needed or returned.</EmptyState>}
      </section>
    </div>
  );
}

export function Competitors({ competitors }) {
  const items = Array.isArray(competitors)
    ? competitors.filter((item) => item && typeof item === "object" && !Array.isArray(item))
    : [];
  return (
    <section className="content-card">
      <div className="section-heading"><div><p className="eyebrow">Market landscape</p><h2>Competitor analysis</h2><p className="section-description">A comparison of other businesses serving a similar space.</p></div><span className="count-pill">{items.length} found</span></div>
      {items.length ? <div className="card-grid">{items.map((item, index) => {
        let safeUrl = "";
        try {
          const parsed = new URL(item?.competitor_website);
          if (["http:", "https:"].includes(parsed.protocol)) safeUrl = parsed.href;
        } catch { /* Leave malformed model output as plain text. */ }
        return (
          <article className="competitor-card" key={`${item.competitor_name}-${index}`}>
            <span className="card-index">{String(index + 1).padStart(2, "0")}</span>
            <h3>{item?.competitor_name || "Unnamed competitor"}</h3>
            {safeUrl ? <a className="external-link" href={safeUrl} target="_blank" rel="noreferrer">{item?.competitor_website} <span aria-hidden="true">↗</span></a> : <p className="muted-copy">{item?.competitor_website || "Website not provided"}</p>}
            <p className="card-description">{item?.description || "Description was not provided."}</p>
            <div className="subsection-block"><p className="detail-label">Products and services</p><ListItems items={item?.products_and_services} emptyText="No products or services provided." /></div>
            <div className="subsection-block"><p className="detail-label">Strengths</p><ListItems items={item?.strengths} emptyText="No strengths provided." /></div>
            <div className="subsection-block"><p className="detail-label">Weaknesses</p><ListItems items={item?.weaknesses} emptyText="No weaknesses provided." /></div>
            <p className="card-description">{item?.comparison_with_analyzed_business || "Comparison details were not provided."}</p>
          </article>
        );
      })}</div> : <EmptyState>No competitors were returned in this analysis.</EmptyState>}
    </section>
  );
}

export function SearchQueries({ queries }) {
  const items = Array.isArray(queries) ? queries : [];
  return (
    <section className="content-card">
      <div className="section-heading"><div><p className="eyebrow">Explore search intent</p><h2>Search queries</h2></div><span className="count-pill">{items.length} ideas</span></div>
      {items.length ? <div className="table-scroll"><table><thead><tr><th>Query</th><th>Platform</th><th>Intent</th><th>Business relevance</th><th>Audience</th></tr></thead><tbody>
        {items.map((item, index) => <tr key={`${item.query}-${index}`}><td className="query-cell">{item.query || "Not provided"}</td><td>{item.platform || "Not provided"}</td><td><span className="soft-tag">{item.search_intent || "Not provided"}</span></td><td>{item.business_relevance || "Not provided"}</td><td>{item.target_audience || "Not provided"}</td></tr>)}
      </tbody></table></div> : <EmptyState>No search queries were returned.</EmptyState>}
    </section>
  );
}

export function SEOAnalysis({ seo }) {
  return (
    <div className="section-stack">
      <section className="content-card">
        <div className="section-heading"><div><p className="eyebrow">Be easier to discover</p><h2>SEO analysis</h2></div></div>
        <div className="seo-keywords">
          <div><p className="detail-label">Primary keywords</p><KeywordTags items={seo?.primary_keywords} /></div>
          <div><p className="detail-label">Secondary keywords</p><KeywordTags items={seo?.secondary_keywords} /></div>
          <div><p className="detail-label">Long-tail keywords</p><KeywordTags items={seo?.long_tail_keywords} /></div>
        </div>
        <div className="detail-grid seo-copy-grid"><Value label="Suggested SEO title" value={seo?.suggested_seo_title} /><Value label="Suggested meta description" value={seo?.suggested_meta_description} /></div>
      </section>
      <div className="two-column-grid">
        <section className="content-card"><p className="eyebrow">On-page opportunities</p><h2 className="subheading">Content improvements</h2><ListItems items={seo?.content_improvements} /></section>
        <section className="content-card"><p className="eyebrow">Plan ahead</p><h2 className="subheading">Content ideas</h2><ListItems items={seo?.content_ideas} /></section>
      </div>
    </div>
  );
}

export function ProductsServices({ products }) {
  const items = Array.isArray(products) ? products : [];
  return (
    <section className="content-card">
      <div className="section-heading"><div><p className="eyebrow">What they offer</p><h2>Products &amp; services</h2></div><span className="count-pill">{items.length} identified</span></div>
      {items.length ? <div className="card-grid">{items.map((item, index) => <article className="product-card" key={`${item.name}-${index}`}><span className="product-icon" aria-hidden="true">✧</span><h3>{item.name || "Unnamed offering"}</h3><p className="card-description">{item.description || "No description provided."}</p><Value label="Industry" value={item.industry} /><Value label="Target customer" value={item.target_customer} /><div className="subsection-block"><p className="detail-label">Benefits</p><ListItems items={item.benefits} emptyText="No benefits provided." /></div></article>)}</div> : <EmptyState>No products or services were returned.</EmptyState>}
    </section>
  );
}

export function TargetAudience({ audience }) {
  return (
    <div className="section-stack">
      <section className="content-card">
        <div className="section-heading"><div><p className="eyebrow">Who the site serves</p><h2>Target audience</h2></div></div>
        <div className="detail-grid"><Value label="Primary audience" value={audience?.primary_audience} /><Value label="Secondary audience" value={audience?.secondary_audience} /></div>
      </section>
      <div className="two-column-grid">
        <section className="content-card"><p className="detail-label">Industries</p><ListItems items={audience?.industries} /></section>
        <section className="content-card"><p className="detail-label">Business types</p><ListItems items={audience?.business_types} /></section>
        <section className="content-card"><p className="detail-label">Customer profiles</p><ListItems items={audience?.customer_profiles} /></section>
        <section className="content-card"><p className="detail-label">Locations supported by evidence</p><ListItems items={audience?.locations} /></section>
        <section className="content-card"><p className="detail-label">Customer needs</p><ListItems items={audience?.customer_needs} /></section>
        <section className="content-card"><p className="detail-label">Pain points</p><ListItems items={audience?.pain_points} /></section>
        <section className="content-card"><p className="detail-label">Interests</p><ListItems items={audience?.interests} /></section>
        <section className="content-card"><p className="detail-label">Audience segments</p><ListItems items={audience?.audience_segments} /></section>
      </div>
    </div>
  );
}

const swotCards = [
  { key: "strengths", title: "Strengths", label: "S", className: "swot-strength" },
  { key: "weaknesses", title: "Weaknesses", label: "W", className: "swot-weakness" },
  { key: "opportunities", title: "Opportunities", label: "O", className: "swot-opportunity" },
  { key: "threats", title: "Threats", label: "T", className: "swot-threat" },
];

export function SWOTAnalysis({ swot }) {
  return (
    <div className="section-stack">
      <div className="section-heading swot-title"><div><p className="eyebrow">Strategic snapshot</p><h2>SWOT analysis</h2><p className="section-description">A concise view of internal strengths and challenges, plus external possibilities and risks.</p></div></div>
      <div className="swot-grid">{swotCards.map((card) => <article className={`swot-card ${card.className}`} key={card.key}><div className="swot-card-heading"><span className="swot-letter">{card.label}</span><h3>{card.title}</h3></div><ListItems items={swot?.[card.key]} /></article>)}</div>
    </div>
  );
}
