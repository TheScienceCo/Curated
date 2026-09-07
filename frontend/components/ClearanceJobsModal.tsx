"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import type { CandidateProfile } from "@/lib/types";

interface ClearanceJobsModalProps {
  isOpen: boolean;
  onClose: () => void;
  candidate: CandidateProfile | null;
}

export function ClearanceJobsModal({ isOpen, onClose, candidate }: ClearanceJobsModalProps) {
  const [keywords, setKeywords] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    saved: number;
    below_threshold: number;
    duplicates_skipped: number;
  } | null>(null);

  // Load keywords on open
  useEffect(() => {
    if (isOpen && !keywords) {
      loadKeywords();
    }
  }, [isOpen, keywords]);

  async function loadKeywords() {
    try {
      const response = await api.clearanceJobsKeywords();
      setKeywords(response.keywords);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load keywords");
    }
  }

  async function handleImport() {
    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const result = await api.importClearanceJobs({
        keyword_override: isEditing ? keywords : undefined,
      });
      setResult(result);
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
          <h2>Import ClearanceJobs</h2>
          <button className="modal-close" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          {result ? (
            <div className="success-message">
              <p>✓ Imported {result.saved} jobs</p>
              <ul style={{ marginTop: "0.5rem", fontSize: "0.9rem", color: "var(--weak)" }}>
                {result.below_threshold > 0 && (
                  <li>{result.below_threshold} below threshold</li>
                )}
                {result.duplicates_skipped > 0 && (
                  <li>{result.duplicates_skipped} duplicates skipped</li>
                )}
              </ul>
            </div>
          ) : (
            <>
              <div className="keyword-section">
                <div className="keyword-header">
                  <label>Search keywords:</label>
                  <button
                    className="btn-small"
                    onClick={() => {
                      setIsEditing(!isEditing);
                      if (isEditing) {
                        loadKeywords();
                      }
                    }}
                  >
                    {isEditing ? "Reset" : "Edit"}
                  </button>
                </div>

                {isEditing ? (
                  <textarea
                    value={keywords}
                    onChange={(e) => setKeywords(e.target.value)}
                    placeholder="Enter keywords separated by OR"
                    style={{
                      width: "100%",
                      minHeight: "60px",
                      padding: "0.5rem",
                      fontFamily: "monospace",
                      fontSize: "0.9rem",
                    }}
                  />
                ) : (
                  <div
                    style={{
                      padding: "0.75rem",
                      backgroundColor: "var(--neutral-bg)",
                      borderRadius: "4px",
                      fontFamily: "monospace",
                      fontSize: "0.9rem",
                    }}
                  >
                    {keywords || "(no keywords)"}
                  </div>
                )}
              </div>

              {candidate && (
                <div className="roles-section" style={{ marginTop: "1.5rem" }}>
                  <label>Target roles:</label>
                  <div style={{ marginTop: "0.5rem" }}>
                    {candidate.target_roles.slice(0, 6).map((role) => (
                      <div key={role} style={{ marginBottom: "0.3rem" }}>
                        <input type="checkbox" defaultChecked id={role} />
                        <label htmlFor={role} style={{ marginLeft: "0.3rem" }}>
                          {role}
                        </label>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="meta-section" style={{ marginTop: "1rem", fontSize: "0.85rem", color: "var(--weak)" }}>
                <div>Max results: <strong>50</strong></div>
                <div>Clearance filter: <strong>TS/SCI</strong></div>
              </div>

              {error && (
                <div className="error-banner" style={{ marginTop: "1rem" }}>
                  {error}
                </div>
              )}
            </>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          {!result && (
            <button
              className="btn btn-primary"
              onClick={handleImport}
              disabled={isLoading || !keywords}
            >
              {isLoading ? "Searching..." : "Run Import"}
            </button>
          )}
          {result && (
            <button className="btn btn-primary" onClick={onClose}>
              Done
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
