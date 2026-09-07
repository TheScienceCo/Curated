"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { DecisionPanel } from "@/components/DecisionPanel";
import { DraftPanel } from "@/components/DraftPanel";
import { MissingInfo } from "@/components/MissingInfo";
import { ProveIt } from "@/components/ProveIt";
import { ReasonList } from "@/components/ReasonList";
import { ScoreBar, ScoreChip } from "@/components/Score";
import {
  ACTION_LABELS,
  ACTION_TONE,
  CLEARANCE_LABELS,
  POLYGRAPH_LABELS,
  formatDate,
  formatSalary,
  titleCase,
} from "@/lib/format";
import type { JobDetail, ResumeMatchResult } from "@/lib/types";

const DIMENSION_LABELS: Record<string, string> = {
  fit: "Current fit",
  career_capital: "Career capital",
  proofability: "Proofability",
  compensation: "Compensation",
  lifestyle: "Lifestyle",
  upside: "Upside",
  risk: "Risk",
};

export function OpportunityDetail({
  detail,
  resumeMatch,
}: {
  detail: JobDetail;
  resumeMatch: ResumeMatchResult | null;
}) {
  const router = useRouter();
  const { opportunity, score, messages, decisions, missing_information } = detail;
  const [rescoring, setRescoring] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRescore() {
    setRescoring(true);
    setError(null);
    try {
      await api.rescore(opportunity.id);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Re-scoring failed.");
    } finally {
      setRescoring(false);
    }
  }

  const latestMessage = messages[messages.length - 1] ?? null;

  return (
    <>
      <div className="page-header">
        <Link href="/" className="subtle">
          ← Dashboard
        </Link>
        <div
          className="row"
          style={{ justifyContent: "space-between", alignItems: "flex-start", marginTop: "0.5rem" }}
        >
          <div>
            <h1>{opportunity.title ?? "Untitled opportunity"}</h1>
            <p className="muted">
              {opportunity.company ?? "Company not stated"}
              {opportunity.job_family && ` · ${titleCase(opportunity.job_family)}`}
              {opportunity.location && ` · ${opportunity.location}`}
              {` · ${titleCase(opportunity.remote_status)}`}
            </p>
          </div>
          {score && (
            <div className="row" style={{ gap: "0.6rem" }}>
              <ScoreChip value={score.overall_score} />
              <span className={`pill ${ACTION_TONE[score.recommended_action]}`}>
                {ACTION_LABELS[score.recommended_action]}
              </span>
              <button className="btn" onClick={handleRescore} disabled={rescoring}>
                {rescoring ? "Re-scoring…" : "Re-score"}
              </button>
            </div>
          )}
        </div>
      </div>

      {error && <div className="banner banner-error">{error}</div>}

      {score?.explanation.overall_capped_by_hard_gate && (
        <div className="banner banner-warn">
          The overall score is capped because this role has a hard eligibility gate. Everything
          else about it may be excellent — but you cannot demonstrate your way past this one.
        </div>
      )}

      <div className="grid grid-2" style={{ alignItems: "start" }}>
        <div className="stack" style={{ gap: "1rem" }}>
          {score && (
            <div className="card">
              <div className="card-header">
                <h2>Why this score</h2>
                <span className="subtle">{formatDate(score.generated_at)}</span>
              </div>

              <ul className="reasons" style={{ marginBottom: "1rem" }}>
                {score.explanation.headline.map((line, index) => (
                  <li key={index} className="reason-neutral">
                    <span className="reason-marker">•</span>
                    <span>{line}</span>
                  </li>
                ))}
              </ul>

              <div className="stack" style={{ gap: "0.55rem" }}>
                {(
                  [
                    ["fit", score.fit_score],
                    ["career_capital", score.career_capital_score],
                    ["proofability", score.proofability_score],
                    ["compensation", score.compensation_score],
                    ["lifestyle", score.lifestyle_score],
                    ["upside", score.upside_score],
                  ] as const
                ).map(([key, value]) => (
                  <ScoreBar
                    key={key}
                    label={DIMENSION_LABELS[key]}
                    value={value}
                    weight={score.weights_used[key]}
                  />
                ))}
                <ScoreBar label="Risk (not subtracted by default)" value={score.risk_score} inverted />
              </div>

              {Object.entries(score.explanation.dimensions).map(([key, dimension]) => (
                <details key={key} className="disclosure">
                  <summary>
                    {DIMENSION_LABELS[key] ?? dimension.name} — {Math.round(dimension.score)}/100
                  </summary>
                  <ReasonList reasons={dimension.reasons} />
                </details>
              ))}
            </div>
          )}

          <div className="card">
            <h2>Prove-it analysis</h2>
            {score ? (
              <ProveIt analysis={score.explanation.prove_it} />
            ) : (
              <p className="subtle">Not scored yet.</p>
            )}
          </div>

          <div className="card">
            <h2>Extracted fields</h2>
            <dl className="kv">
              <dt>Salary</dt>
              <dd>
                {formatSalary(opportunity.salary_min, opportunity.salary_max, opportunity.salary_currency)}
              </dd>
              <dt>Equity</dt>
              <dd>
                {opportunity.equity === null
                  ? "Not mentioned"
                  : opportunity.equity
                    ? opportunity.equity_percent_min
                      ? `${opportunity.equity_percent_min}%${
                          opportunity.equity_percent_max &&
                          opportunity.equity_percent_max !== opportunity.equity_percent_min
                            ? `–${opportunity.equity_percent_max}%`
                            : ""
                        }`
                      : "Offered, percentage not stated"
                    : "Not offered"}
              </dd>
              <dt>Bonus / OTE</dt>
              <dd>
                {opportunity.commission_ote
                  ? `OTE $${opportunity.commission_ote.toLocaleString()}`
                  : opportunity.bonus ?? "Not stated"}
              </dd>
              <dt>Clearance</dt>
              <dd>{CLEARANCE_LABELS[opportunity.security_clearance] ?? opportunity.security_clearance}</dd>
              <dt>Polygraph</dt>
              <dd>
                {POLYGRAPH_LABELS[opportunity.polygraph_requirement] ?? opportunity.polygraph_requirement}
              </dd>
              <dt>Hours / week</dt>
              <dd>{opportunity.hours ?? "Not stated"}</dd>
              <dt>Travel</dt>
              <dd>{opportunity.travel === null ? "Not stated" : `${opportunity.travel}%`}</dd>
              <dt>Experience</dt>
              <dd>
                {opportunity.required_years_experience
                  ? `${opportunity.required_years_experience}${
                      opportunity.preferred_years_experience
                        ? `–${opportunity.preferred_years_experience}`
                        : "+"
                    } years`
                  : "Not stated"}
              </dd>
              <dt>Stage / size</dt>
              <dd>
                {titleCase(opportunity.company_stage) || "Unknown"}
                {opportunity.estimated_company_size && ` · ${opportunity.estimated_company_size}`}
              </dd>
              <dt>Extraction</dt>
              <dd className="subtle">{opportunity.extraction_method}</dd>
            </dl>

            {opportunity.required_skills.length > 0 && (
              <>
                <h3 style={{ marginTop: "1rem" }}>Required skills</h3>
                <div className="row" style={{ gap: "0.3rem" }}>
                  {opportunity.required_skills.map((skill) => (
                    <span key={skill} className="tag">
                      {opportunity.skill_labels[skill] ?? titleCase(skill)}
                    </span>
                  ))}
                </div>
              </>
            )}
            {opportunity.preferred_skills.length > 0 && (
              <>
                <h3 style={{ marginTop: "0.8rem" }}>Preferred skills</h3>
                <div className="row" style={{ gap: "0.3rem" }}>
                  {opportunity.preferred_skills.map((skill) => (
                    <span key={skill} className="tag">
                      {opportunity.skill_labels[skill] ?? titleCase(skill)}
                    </span>
                  ))}
                </div>
              </>
            )}

            <details className="disclosure">
              <summary>Original text</summary>
              <div className="jd">{opportunity.job_description ?? "No source text."}</div>
            </details>
          </div>
        </div>

        <div className="stack" style={{ gap: "1rem" }}>
          <DraftPanel opportunityId={opportunity.id} message={latestMessage} />

          <div className="card">
            <h2>Missing information</h2>
            <MissingInfo fields={missing_information} />
          </div>

          {resumeMatch?.best && (
            <div className="card">
              <div className="card-header">
                <h2>Recommended résumé</h2>
                {resumeMatch.semantic_enabled && <span className="tag">semantic</span>}
              </div>
              <p>
                <strong>{resumeMatch.best.title}</strong>{" "}
                <span className="subtle">({Math.round(resumeMatch.best.score)}/100)</span>
              </p>
              <p className="muted">{resumeMatch.best.summary}</p>

              {resumeMatch.best.highlight.length > 0 && (
                <>
                  <h3>Highlight</h3>
                  <div className="row" style={{ gap: "0.3rem", marginBottom: "0.7rem" }}>
                    {resumeMatch.best.highlight.map((item) => (
                      <span key={item} className="tag tag-ok">{item}</span>
                    ))}
                  </div>
                </>
              )}
              {resumeMatch.best.de_emphasize.length > 0 && (
                <>
                  <h3>De-emphasize</h3>
                  <div className="row" style={{ gap: "0.3rem", marginBottom: "0.7rem" }}>
                    {resumeMatch.best.de_emphasize.map((item) => (
                      <span key={item} className="tag">{item}</span>
                    ))}
                  </div>
                </>
              )}
              {resumeMatch.best.missing_keywords.length > 0 && (
                <>
                  <h3>Missing keywords</h3>
                  <p className="subtle">
                    Address these honestly rather than adding them to the résumé:{" "}
                    {resumeMatch.best.missing_keywords.join(", ")}.
                  </p>
                </>
              )}

              <details className="disclosure">
                <summary>All variants ({resumeMatch.ranked.length})</summary>
                <ul className="stack" style={{ gap: "0.3rem", paddingLeft: "1.1rem", margin: 0 }}>
                  {resumeMatch.ranked.map((entry) => (
                    <li key={entry.resume_id}>
                      {entry.title} — {Math.round(entry.score)}/100
                    </li>
                  ))}
                </ul>
              </details>
            </div>
          )}

          <DecisionPanel opportunityId={opportunity.id} decisions={decisions} />
        </div>
      </div>
    </>
  );
}
