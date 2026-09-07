"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { MissingInfo } from "@/components/MissingInfo";
import { ProveIt } from "@/components/ProveIt";
import { ScoreBar, ScoreChip } from "@/components/Score";
import { ACTION_LABELS, ACTION_TONE, CLEARANCE_LABELS, POLYGRAPH_LABELS, formatSalary, titleCase } from "@/lib/format";
import type { AnalyzeResponse, DraftTone } from "@/lib/types";

const EXAMPLE = `Hi Eric, I'm recruiting for a Forward Deployed Engineer supporting national security customers. The role requires TS/SCI and experience with Python, React, TypeScript, LLMs, and customer-facing technical delivery. Salary is $190k-$240k plus equity. Position is onsite in San Francisco with approximately 20% travel. We're looking for 3-5 years full-stack engineering experience.`;

export function AnalyzeForm() {
  const router = useRouter();
  const [rawText, setRawText] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [channel, setChannel] = useState("email");
  const [tone, setTone] = useState<DraftTone>("professional");
  const [save, setSave] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!rawText.trim()) return;
    setPending(true);
    setError(null);
    setResult(null);
    try {
      const response = await api.analyze({
        raw_text: rawText,
        source_url: sourceUrl.trim() || null,
        channel,
        tone,
        save,
        generate_draft: true,
      });
      setResult(response);
      if (save) router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Analysis failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="grid grid-2" style={{ alignItems: "start" }}>
      <form className="card" onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="raw_text">Recruiter message or job description</label>
          <textarea
            id="raw_text"
            value={rawText}
            onChange={(event) => setRawText(event.target.value)}
            placeholder="Paste the message here…"
            required
          />
          <div className="hint">
            <button
              type="button"
              className="btn"
              style={{ padding: "0.15rem 0.5rem", fontSize: "0.78rem", marginTop: "0.35rem" }}
              onClick={() => setRawText(EXAMPLE)}
            >
              Load the example from the README
            </button>
          </div>
        </div>

        <div className="field">
          <label htmlFor="source_url">Job URL (optional)</label>
          <input
            id="source_url"
            type="url"
            value={sourceUrl}
            onChange={(event) => setSourceUrl(event.target.value)}
            placeholder="https://…"
          />
        </div>

        <div className="row" style={{ gap: "1rem", alignItems: "flex-end" }}>
          <div className="field" style={{ flex: 1, marginBottom: 0 }}>
            <label htmlFor="channel">Channel</label>
            <select id="channel" value={channel} onChange={(e) => setChannel(e.target.value)}>
              <option value="email">Email</option>
              <option value="linkedin">LinkedIn</option>
              <option value="job_board">Job board</option>
              <option value="sms">SMS</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div className="field" style={{ flex: 1, marginBottom: 0 }}>
            <label htmlFor="tone">Reply tone</label>
            <select id="tone" value={tone} onChange={(e) => setTone(e.target.value as DraftTone)}>
              <option value="professional">Professional</option>
              <option value="warm">Warm</option>
              <option value="direct">Direct</option>
              <option value="humorous">Humorous</option>
            </select>
          </div>
        </div>

        <label
          style={{ display: "flex", gap: "0.45rem", alignItems: "center", margin: "0.9rem 0", fontWeight: 400 }}
        >
          <input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} style={{ width: "auto" }} />
          Save to the dashboard
        </label>

        <button type="submit" className="btn btn-primary" disabled={pending || !rawText.trim()}>
          {pending ? "Analyzing…" : "Analyze"}
        </button>

        {error && (
          <div className="banner banner-error" style={{ marginTop: "1rem", marginBottom: 0 }}>
            {error}
          </div>
        )}
      </form>

      <div>
        {!result && !pending && (
          <div className="card">
            <div className="empty">Results will appear here.</div>
          </div>
        )}
        {pending && (
          <div className="card">
            <div className="empty spinner-text">Extracting, scoring and drafting…</div>
          </div>
        )}
        {result && <AnalyzeResult result={result} />}
      </div>
    </div>
  );
}

function AnalyzeResult({ result }: { result: AnalyzeResponse }) {
  const { opportunity, score, draft, prove_it, missing_information, resume_match } = result;
  const weights = score.weights_used;

  return (
    <div className="stack" style={{ gap: "1rem" }}>
      <div className="card">
        <div className="card-header">
          <div>
            <h2>{opportunity.title ?? "Untitled opportunity"}</h2>
            <div className="muted">
              {opportunity.company ?? "Company not stated"} ·{" "}
              {formatSalary(opportunity.salary_min, opportunity.salary_max, opportunity.salary_currency)}
            </div>
          </div>
          <div className="row" style={{ gap: "0.5rem" }}>
            <ScoreChip value={score.overall_score} />
            <span className={`pill ${ACTION_TONE[score.recommended_action]}`}>
              {ACTION_LABELS[score.recommended_action]}
            </span>
          </div>
        </div>

        <ul className="reasons" style={{ marginBottom: "0.9rem" }}>
          {score.explanation.headline.map((line, index) => (
            <li key={index} className="reason-neutral">
              <span className="reason-marker">•</span>
              <span>{line}</span>
            </li>
          ))}
        </ul>

        <div className="stack" style={{ gap: "0.55rem" }}>
          <ScoreBar label="Current fit" value={score.fit_score} weight={weights.fit} />
          <ScoreBar label="Career capital" value={score.career_capital_score} weight={weights.career_capital} />
          <ScoreBar label="Proofability" value={score.proofability_score} weight={weights.proofability} />
          <ScoreBar label="Compensation" value={score.compensation_score} weight={weights.compensation} />
          <ScoreBar label="Lifestyle" value={score.lifestyle_score} weight={weights.lifestyle} />
          <ScoreBar label="Upside" value={score.upside_score} weight={weights.upside} />
          <ScoreBar label="Risk (shown separately)" value={score.risk_score} inverted />
        </div>

        <dl className="kv" style={{ marginTop: "1rem" }}>
          <dt>Clearance</dt>
          <dd>{CLEARANCE_LABELS[opportunity.security_clearance] ?? opportunity.security_clearance}</dd>
          <dt>Polygraph</dt>
          <dd>{POLYGRAPH_LABELS[opportunity.polygraph_requirement] ?? opportunity.polygraph_requirement}</dd>
          <dt>Location</dt>
          <dd>
            {opportunity.location ?? "Not stated"} · {titleCase(opportunity.remote_status)}
          </dd>
          <dt>Extraction</dt>
          <dd className="subtle">{opportunity.extraction_method}</dd>
        </dl>

        {result.saved && (
          <div style={{ marginTop: "1rem" }}>
            <Link href={`/opportunities/${opportunity.id}`} className="btn btn-primary" style={{ padding: "0.45rem 0.95rem" }}>
              Open full detail view →
            </Link>
          </div>
        )}
        {!result.saved && (
          <div className="banner banner-info" style={{ marginTop: "1rem", marginBottom: 0 }}>
            Preview only — this opportunity was not saved.
          </div>
        )}
      </div>

      <div className="card">
        <h2>Prove-it analysis</h2>
        <ProveIt analysis={prove_it} />
      </div>

      {draft && (
        <div className="card">
          <div className="card-header">
            <h2>Drafted reply</h2>
            <span className="tag">{titleCase(draft.intent)}</span>
          </div>
          <div className="banner banner-info">
            This draft is not sent. Review it, edit it, and send it yourself.
          </div>
          <pre className="jd" style={{ whiteSpace: "pre-wrap" }}>{draft.body}</pre>
        </div>
      )}

      <div className="card">
        <h2>Missing information</h2>
        <MissingInfo fields={missing_information} />
      </div>

      {resume_match?.best && (
        <div className="card">
          <h2>Recommended résumé</h2>
          <p>
            <strong>{resume_match.best.title}</strong> ({Math.round(resume_match.best.score)}/100)
          </p>
          <p className="muted">{resume_match.best.summary}</p>
          {resume_match.best.highlight.length > 0 && (
            <>
              <h3>Highlight</h3>
              <div className="row" style={{ gap: "0.3rem" }}>
                {resume_match.best.highlight.map((item) => (
                  <span key={item} className="tag tag-ok">{item}</span>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
