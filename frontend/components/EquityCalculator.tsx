"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { EquityAnalysis } from "@/lib/types";

export function EquityCalculator() {
  const [equityPercent, setEquityPercent] = useState(0.25);
  const [dilution, setDilution] = useState(40);
  const [valuation, setValuation] = useState<number | "">("");
  const [strike, setStrike] = useState<number | "">("");
  const [shares, setShares] = useState<number | "">("");
  const [result, setResult] = useState<EquityAnalysis | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      setResult(
        await api.equity({
          equity_percent: equityPercent,
          dilution_percent: dilution,
          current_valuation: valuation === "" ? null : valuation,
          strike_price: strike === "" ? null : strike,
          shares: shares === "" ? null : shares,
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Calculation failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="grid grid-2" style={{ alignItems: "start" }}>
      <form className="card" onSubmit={submit}>
        <div className="field">
          <label htmlFor="equity-percent">Equity grant (%)</label>
          <input
            id="equity-percent"
            type="number"
            step={0.01}
            min={0}
            max={100}
            value={equityPercent}
            onChange={(event) => setEquityPercent(Number(event.target.value))}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="dilution">Expected future dilution (%) — {dilution}%</label>
          <input
            id="dilution"
            type="range"
            min={0}
            max={90}
            step={5}
            value={dilution}
            onChange={(event) => setDilution(Number(event.target.value))}
            style={{ width: "100%" }}
          />
          <div className="hint">
            Every future round dilutes you. 40–60% across a company&apos;s life is common.
          </div>
        </div>
        <div className="field">
          <label htmlFor="valuation">Current valuation ($, optional)</label>
          <input
            id="valuation"
            type="number"
            min={0}
            value={valuation}
            onChange={(event) => setValuation(event.target.value === "" ? "" : Number(event.target.value))}
            placeholder="e.g. 80000000"
          />
        </div>
        <div className="row" style={{ gap: "0.8rem" }}>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="strike">Strike price ($, optional)</label>
            <input
              id="strike"
              type="number"
              step={0.01}
              min={0}
              value={strike}
              onChange={(event) => setStrike(event.target.value === "" ? "" : Number(event.target.value))}
            />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="shares">Share count (optional)</label>
            <input
              id="shares"
              type="number"
              min={0}
              value={shares}
              onChange={(event) => setShares(event.target.value === "" ? "" : Number(event.target.value))}
            />
          </div>
        </div>
        <button className="btn btn-primary" type="submit" disabled={pending}>
          {pending ? "Calculating…" : "Calculate scenarios"}
        </button>
        {error && (
          <div className="banner banner-error" style={{ marginTop: "0.8rem", marginBottom: 0 }}>
            {error}
          </div>
        )}
      </form>

      <div className="card">
        {!result ? (
          <div className="empty">Enter a grant to see the scenario table.</div>
        ) : (
          <>
            <div className="card-header">
              <h2>Scenarios</h2>
              <span className="tag">hypothetical</span>
            </div>
            <dl className="kv" style={{ marginBottom: "1rem" }}>
              <dt>Current ownership</dt>
              <dd>{result.equity_percent}%</dd>
              <dt>After {result.dilution_percent}% dilution</dt>
              <dd>
                <strong>{result.post_dilution_percent.toFixed(4).replace(/0+$/, "")}%</strong>
              </dd>
              {result.current_paper_value !== null && (
                <>
                  <dt>Paper value today</dt>
                  <dd>{formatMoney(result.current_paper_value)}</dd>
                </>
              )}
            </dl>

            <div className="table-wrap">
              <table style={{ minWidth: "auto" }}>
                <thead>
                  <tr>
                    <th>Exit valuation</th>
                    <th className="num">Gross</th>
                    {result.strike_price !== null && <th className="num">Net of strike</th>}
                  </tr>
                </thead>
                <tbody>
                  {result.scenarios.map((scenario) => (
                    <tr key={scenario.exit_valuation}>
                      <td>{scenario.label}</td>
                      <td className="num">{formatMoney(scenario.gross_value)}</td>
                      {result.strike_price !== null && (
                        <td className="num">{formatMoney(scenario.net_value)}</td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="banner banner-warn" style={{ marginTop: "1rem", marginBottom: 0 }}>
              {result.disclaimer}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
