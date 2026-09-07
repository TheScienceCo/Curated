"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { EquityAnalysis, JobOpportunity } from "@/lib/types";

/**
 * Inline equity scenarios for an opportunity that offers equity.
 *
 * The number a recruiter quotes is pre-dilution and pre-exit; showing the
 * range of outcomes next to the offer is more useful than a separate page the
 * user has to remember to visit.
 */
export function EquityScenarios({ job }: { job: JobOpportunity }) {
  const grant = job.equity_percent_max ?? job.equity_percent_min;
  const [dilution, setDilution] = useState(40);
  const [analysis, setAnalysis] = useState<EquityAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!grant) return;
    let cancelled = false;
    api
      .equity({ equity_percent: grant, dilution_percent: dilution })
      .then((result) => {
        if (!cancelled) setAnalysis(result);
      })
      .catch(() => {
        if (!cancelled) setError("Could not calculate scenarios.");
      });
    return () => {
      cancelled = true;
    };
  }, [grant, dilution]);

  if (!job.equity) return null;

  if (!grant) {
    return (
      <div className="card">
        <h2>Equity</h2>
        <p className="muted" style={{ marginBottom: 0 }}>
          Equity is offered but the grant size is not stated, so it cannot be valued. That is
          the question to ask — a percentage and the current valuation.
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <h2>Equity scenarios</h2>
        <span className="tag">hypothetical</span>
      </div>

      <div className="field">
        <label htmlFor="detail-dilution">
          Assumed future dilution — {dilution}% (stake becomes{" "}
          {analysis ? analysis.post_dilution_percent.toFixed(3).replace(/0+$/, "") : "…"}%)
        </label>
        <input
          id="detail-dilution"
          type="range"
          min={0}
          max={80}
          step={5}
          value={dilution}
          onChange={(event) => setDilution(Number(event.target.value))}
          style={{ width: "100%" }}
        />
      </div>

      {error && <div className="banner banner-error">{error}</div>}

      {analysis && (
        <>
          <div className="table-wrap">
            <table style={{ minWidth: "auto" }}>
              <thead>
                <tr>
                  <th>Exit valuation</th>
                  <th className="num">Your stake</th>
                </tr>
              </thead>
              <tbody>
                {analysis.scenarios.map((scenario) => (
                  <tr key={scenario.exit_valuation}>
                    <td>{scenario.label}</td>
                    <td className="num">{formatMoney(scenario.gross_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="subtle" style={{ marginTop: "0.7rem", marginBottom: 0 }}>
            {analysis.disclaimer}
          </p>
        </>
      )}
    </div>
  );
}
