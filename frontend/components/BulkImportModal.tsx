"use client";

import { useState } from "react";
import { api } from "@/lib/api";

interface BulkImportModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function BulkImportModal({ isOpen, onClose }: BulkImportModalProps) {
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    saved: number;
    below_threshold: number;
    duplicates_skipped: number;
    failed: number;
    total_processed: number;
  } | null>(null);

  async function handleImport() {
    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      // Split input by common delimiters (blank lines or separators)
      const jobs = input
        .split(/\n\s*\n+/)
        .map((job) => job.trim())
        .filter((job) => job.length > 0);

      if (jobs.length === 0) {
        setError("Please paste at least one job description");
        setIsLoading(false);
        return;
      }

      const result = await api.bulkImport(jobs);
      setResult(result);
      setInput(""); // Clear input on success
    } catch (err) {
      const message = err instanceof Error ? err.message : "Import failed";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  if (!isOpen) {
    return null;
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Bulk Import Jobs</h2>
          <button className="modal-close" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          {result ? (
            <div className="success-message">
              <p>✓ Processed {result.total_processed} job(s)</p>
              <ul style={{ marginTop: "0.5rem", fontSize: "0.9rem", color: "var(--weak)" }}>
                <li>{result.saved} saved</li>
                {result.below_threshold > 0 && (
                  <li>{result.below_threshold} below threshold</li>
                )}
                {result.duplicates_skipped > 0 && (
                  <li>{result.duplicates_skipped} duplicates</li>
                )}
                {result.failed > 0 && <li>{result.failed} failed to parse</li>}
              </ul>
            </div>
          ) : (
            <>
              <div className="field">
                <label htmlFor="jobs-textarea">Paste job descriptions below:</label>
                <div className="hint">
                  Separate multiple jobs with blank lines. Each job description is processed
                  through the extraction pipeline and scored.
                </div>
                <textarea
                  id="jobs-textarea"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={
                    "Paste job posting, email, or ad here.\n\n" +
                    "For multiple jobs, separate with blank lines:\n\n" +
                    "[Job 1 full text]\n\n" +
                    "[Job 2 full text]\n\n" +
                    "[Job 3 full text]"
                  }
                  style={{
                    minHeight: "300px",
                    fontFamily: "monospace",
                    fontSize: "0.85rem",
                  }}
                />
              </div>

              {error && (
                <div className="error-banner" style={{ marginBottom: "1rem" }}>
                  {error}
                </div>
              )}

              <div className="hint" style={{ marginTop: "1rem" }}>
                Jobs scoring below 40 will be skipped. Duplicates (same company + title +
                location) are ignored.
              </div>
            </>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            {result ? "Done" : "Cancel"}
          </button>
          {!result && (
            <button
              className="btn btn-primary"
              onClick={handleImport}
              disabled={isLoading || !input.trim()}
            >
              {isLoading ? "Importing..." : "Import"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
