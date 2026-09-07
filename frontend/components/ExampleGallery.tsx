"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { MissingInfo } from "@/components/MissingInfo";
import { ProveIt } from "@/components/ProveIt";
import { ScoreBar, ScoreChip } from "@/components/Score";
import {
  ACTION_LABELS,
  ACTION_TONE,
  CLEARANCE_LABELS,
  POLYGRAPH_LABELS,
  formatSalary,
  titleCase,
} from "@/lib/format";
import type { AnalyzeResponse, ExampleCase } from "@/lib/types";

/**
 * The curated demo scenarios.
 *
 * Each runs through the real pipeline in preview mode, so the outcome shown is
 * genuinely computed rather than a recorded fixture — and nothing lands on the
 * dashboard unless the user asks for it.
 */
export function ExampleGallery({ examples }: { examples: ExampleCase[] }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, AnalyzeResponse>>({});
  const [pending, setPending] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function run(example: ExampleCase) {
    setOpenId(example.id);
    if (results[example.id]) return;

    setPending(example.id);
    setErrors((prev) => ({ ...prev, [example.id]: "" }));
    try {
      const result = await api.analyze({
        raw_text: example.raw_text,
        channel: example.channel,
        save: false,
        generate_draft: true,
      });
      setResults((prev) => ({ ...prev, [example.id]: result }));
    } catch (err) {
      setErrors((prev) => ({
        ...prev,
        [example.id]: err instanceof ApiError ? err.message : "Analysis failed.",
      }));
    } finally {
      setPending(null);
    }
  }

  if (examples.length === 0) {
    return (
      <div className="card">
        <div className="empty">No example cases available.</div>
      </div>
    );
  }

  return (
    <div className="stack" style={{ gap: "1rem" }}>
      {examples.map((example) => {
        const result = results[example.id];
        const open = openId === example.id;
        return (
          <div key={example.id} className="card">
            <div className="card-header">
              <div>
                <h2>{example.title}</h2>
                <span className="tag">{titleCase(example.channel)}</span>
              </div>
              <div className="row" style={{ gap: "0.5rem" }}>
                {result && (
                  <>
                    <ScoreChip value={result.score.overall_score} />
                    <span className={`pill ${ACTION_TONE[result.score.recommended_action]}`}>
                      {ACTION_LABELS[result.score.recommended_action]}
                    </span>
                  </>
                )}
                <button
                  className={result ? "btn" : "btn btn-primary"}
                  onClick={() => (open && result ? setOpenId(null) : run(example))}
                  disabled={pending === example.id}
                >
                  {pending === example.id
                    ? "Running…"
                    : result
                      ? open
                        ? "Hide"
                        : "Show result"
                      : "Run this case"}
                </button>
              </div>
            </div>

            <p style={{ marginBottom: "0.4rem" }}>{example.demonstrates}</p>
            <p className="subtle" style={{ marginBottom: "0.8rem" }}>
              <strong>Expected:</strong> {example.expect}
            </p>

            <details className="disclosure">
              <summary>The message</summary>
              <div className="jd">{example.raw_text}</div>
            </details>

            {errors[example.id] && (
              <div className="banner banner-error" style={{ marginTop: "0.8rem", marginBottom: 0 }}>
                {errors[example.id]}
              </div>
            )}

            {open && result && <ExampleResult result={result} />}
          </div>
        );
      })}
    </div>
  );
}

function ExampleResult({ result }: { result: AnalyzeResponse }) {
  const { opportunity, score, draft, prove_it, missing_information } = result;
  const weights = score.weights_used;

  return (
    <div style={{ marginTop: "1rem", borderTop: "1px solid var(--border)", paddingTop: "1rem" }}>
      <div className="grid grid-2" style={{ alignItems: "start" }}>
        <div>
          <h3>What it extracted</h3>
          <dl className="kv" style={{ marginBottom: "1rem" }}>
            <dt>Title</dt>
            <dd>{opportunity.title ?? <span className="subtle">not stated</span>}</dd>
            <dt>Company</dt>
            <dd>{opportunity.company ?? <span className="subtle">not stated</span>}</dd>
            <dt>Salary</dt>
            <dd>
              {formatSalary(opportunity.salary_min, opportunity.salary_max, opportunity.salary_currency)}
            </dd>
            <dt>Clearance</dt>
            <dd>{CLEARANCE_LABELS[opportunity.security_clearance] ?? opportunity.security_clearance}</dd>
            <dt>Polygraph</dt>
            <dd>
              {POLYGRAPH_LABELS[opportunity.polygraph_requirement] ??
                opportunity.polygraph_requirement}
            </dd>
          </dl>

          <h3>Scores</h3>
          <div className="stack" style={{ gap: "0.5rem" }}>
            <ScoreBar label="Current fit" value={score.fit_score} weight={weights.fit} />
            <ScoreBar
              label="Career capital"
              value={score.career_capital_score}
              weight={weights.career_capital}
            />
            <ScoreBar
              label="Proofability"
              value={score.proofability_score}
              weight={weights.proofability}
            />
            <ScoreBar
              label="Compensation"
              value={score.compensation_score}
              weight={weights.compensation}
            />
            <ScoreBar label="Lifestyle" value={score.lifestyle_score} weight={weights.lifestyle} />
            <ScoreBar label="Upside" value={score.upside_score} weight={weights.upside} />
            <ScoreBar label="Risk (separate)" value={score.risk_score} inverted />
          </div>

          <h3 style={{ marginTop: "1rem" }}>Why</h3>
          <ul className="reasons">
            {score.explanation.headline.map((line, index) => (
              <li key={index} className="reason-neutral">
                <span className="reason-marker">•</span>
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3>Prove-it analysis</h3>
          <ProveIt analysis={prove_it} />

          <h3 style={{ marginTop: "1rem" }}>Missing information</h3>
          <MissingInfo fields={missing_information.slice(0, 5)} />

          {draft && (
            <>
              <h3 style={{ marginTop: "1rem" }}>
                Drafted reply <span className="tag">{titleCase(draft.intent)}</span>
              </h3>
              <div className="jd" style={{ maxHeight: 260 }}>
                {draft.body}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
