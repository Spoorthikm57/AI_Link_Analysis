import { useState } from "react";

function isValidWebsiteUrl(value) {
  try {
    const url = new URL(value.trim());
    return ["http:", "https:"].includes(url.protocol) && Boolean(url.hostname.includes("."));
  } catch {
    return false;
  }
}

export default function URLInput({ onAnalyze, disabled }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");

  function handleSubmit(event) {
    event.preventDefault();
    const trimmedUrl = url.trim();

    if (!trimmedUrl) {
      setError("Enter a website URL to get started.");
      return;
    }

    if (!isValidWebsiteUrl(trimmedUrl)) {
      setError("Enter a valid website address, including https://.");
      return;
    }

    setError("");
    onAnalyze(trimmedUrl);
  }

  function useExample() {
    setUrl("https://www.python.org");
    setError("");
  }

  return (
    <form className="url-form" onSubmit={handleSubmit} id="analyze" noValidate>
      <label className="input-label" htmlFor="website-url">Website URL</label>
      <div className={`url-input-wrap${error ? " has-error" : ""}`}>
        <span className="input-globe" aria-hidden="true">◎</span>
        <input
          id="website-url"
          type="url"
          value={url}
          onChange={(event) => {
            setUrl(event.target.value);
            if (error) setError("");
          }}
          placeholder="https://www.example.com"
          autoComplete="url"
          aria-invalid={Boolean(error)}
          aria-describedby={error ? "url-error" : "url-help"}
          disabled={disabled}
        />
        <button className="analyze-button" type="submit" disabled={disabled}>
          Analyze website <span aria-hidden="true">↗</span>
        </button>
      </div>
      {error ? (
        <p className="form-message form-error" id="url-error" role="alert">{error}</p>
      ) : (
        <p className="form-message" id="url-help">
          Try an example:{" "}
          <button className="text-button" type="button" onClick={useExample}>
            https://www.python.org
          </button>
        </p>
      )}
    </form>
  );
}
