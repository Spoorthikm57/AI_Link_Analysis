export default function Header({ onHome }) {
  return (
    <header className="site-header">
      <a className="brand" href="#home" onClick={onHome} aria-label="AI Website Analyzer home">
        <span className="brand-mark" aria-hidden="true">✦</span>
        <span>insight<span className="brand-accent">ly</span></span>
      </a>
      <nav className="header-nav" aria-label="Main navigation">
        <a href="#home" onClick={onHome}>Home</a>
        <a href="#features">Features</a>
        <a href="#about">About</a>
      </nav>
      <a className="header-cta" href="#analyze" onClick={onHome}>
        <span className="status-dot" /> AI Website Analyzer
      </a>
    </header>
  );
}
