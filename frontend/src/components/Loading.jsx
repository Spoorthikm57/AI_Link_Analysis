import { useEffect, useState } from "react";

const steps = [
  "Extracting website content...",
  "Analyzing business information...",
  "Generating AI insights...",
];

export default function Loading({ url }) {
  const [step, setStep] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setStep((current) => (current + 1) % steps.length);
    }, 2200);

    return () => window.clearInterval(timer);
  }, []);

  return (
    <section className="loading-panel" aria-live="polite">
      <div className="loading-orbit"><span /></div>
      <p className="eyebrow">AI analysis in progress</p>
      <h2>Analyzing website<span className="loading-dots">...</span></h2>
      <p className="loading-step">{steps[step]}</p>
      <p className="loading-url">{url}</p>
      <div className="loading-progress"><span /></div>
      <p className="loading-note">This can take a little while as we build your report.</p>
    </section>
  );
}
