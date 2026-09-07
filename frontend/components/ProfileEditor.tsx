"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { CLEARANCE_LABELS, POLYGRAPH_LABELS, titleCase } from "@/lib/format";
import type { CandidateProfile } from "@/lib/types";

const WEIGHT_KEYS = [
  ["fit", "Current fit"],
  ["career_capital", "Career capital"],
  ["proofability", "Proofability"],
  ["compensation", "Compensation"],
  ["lifestyle", "Lifestyle"],
  ["upside", "Upside"],
] as const;

const BAND_KEYS = [
  ["poor", "Poor (below this is a bad offer)"],
  ["acceptable", "Acceptable"],
  ["strong", "Strong"],
  ["excellent", "Excellent"],
] as const;

interface ScoringConfigShape {
  compensation_bands?: Record<string, number>;
  weights?: Record<string, number>;
  risk_penalty_weight?: number;
}

export function ProfileEditor({ profile }: { profile: CandidateProfile }) {
  const router = useRouter();
  const config = (profile.scoring_config ?? {}) as ScoringConfigShape;

  const [minimumSalary, setMinimumSalary] = useState(profile.minimum_salary ?? 0);
  const [targetSalary, setTargetSalary] = useState(profile.target_salary ?? 0);
  const [travel, setTravel] = useState(profile.willingness_to_travel);
  const [hours, setHours] = useState(profile.preferred_weekly_hours ?? 45);
  const [remote, setRemote] = useState(profile.remote_preference);
  const [risk, setRisk] = useState(profile.risk_tolerance);
  const [bands, setBands] = useState<Record<string, number>>({
    poor: config.compensation_bands?.poor ?? 120000,
    acceptable: config.compensation_bands?.acceptable ?? 150000,
    strong: config.compensation_bands?.strong ?? 200000,
    excellent: config.compensation_bands?.excellent ?? 250000,
  });
  const [weights, setWeights] = useState<Record<string, number>>({
    fit: config.weights?.fit ?? 0.2,
    career_capital: config.weights?.career_capital ?? 0.25,
    proofability: config.weights?.proofability ?? 0.15,
    compensation: config.weights?.compensation ?? 0.2,
    lifestyle: config.weights?.lifestyle ?? 0.1,
    upside: config.weights?.upside ?? 0.1,
  });
  const [riskPenalty, setRiskPenalty] = useState(config.risk_penalty_weight ?? 0);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const weightTotal = Object.values(weights).reduce((sum, value) => sum + value, 0);
  const bandsValid =
    bands.poor < bands.acceptable && bands.acceptable < bands.strong && bands.strong < bands.excellent;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!bandsValid) {
      setError("Compensation bands must increase: poor < acceptable < strong < excellent.");
      return;
    }
    setPending(true);
    setError(null);
    setSaved(false);
    try {
      await api.updateProfile({
        minimum_salary: minimumSalary || null,
        target_salary: targetSalary || null,
        willingness_to_travel: travel,
        preferred_weekly_hours: hours,
        remote_preference: remote,
        risk_tolerance: risk,
        scoring_config: {
          ...config,
          compensation_bands: bands,
          weights,
          risk_penalty_weight: riskPenalty,
        },
      });
      setSaved(true);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the profile.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={save} className="grid grid-2" style={{ alignItems: "start" }}>
      <div className="stack" style={{ gap: "1rem" }}>
        <div className="card">
          <h2>{profile.name}</h2>
          <p className="muted">{profile.summary}</p>
          <dl className="kv">
            <dt>Location</dt>
            <dd>{profile.current_location ?? "—"}</dd>
            <dt>Citizenship</dt>
            <dd>{profile.citizenship ?? "—"}</dd>
            <dt>Clearance</dt>
            <dd>{CLEARANCE_LABELS[profile.clearance_level] ?? profile.clearance_level}</dd>
            <dt>Polygraph</dt>
            <dd>{POLYGRAPH_LABELS[profile.polygraph_type] ?? profile.polygraph_type}</dd>
            <dt>Languages</dt>
            <dd>{profile.languages.join(", ") || "—"}</dd>
            <dt>Education</dt>
            <dd>{profile.education.join(", ") || "—"}</dd>
          </dl>
          {profile.notes && (
            <div className="banner banner-warn" style={{ marginTop: "0.9rem", marginBottom: 0 }}>
              {profile.notes}
            </div>
          )}
        </div>

        <div className="card">
          <h2>Preferences</h2>
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: "0.8rem" }}>
            <NumberField label="Minimum salary ($)" value={minimumSalary} onChange={setMinimumSalary} step={5000} />
            <NumberField label="Target salary ($)" value={targetSalary} onChange={setTargetSalary} step={5000} />
            <NumberField label="Max travel (%)" value={travel} onChange={setTravel} max={100} />
            <NumberField label="Preferred hours / week" value={hours} onChange={setHours} min={1} max={120} />
          </div>
          <div className="field" style={{ marginTop: "0.8rem" }}>
            <label htmlFor="remote">Remote preference</label>
            <select id="remote" value={remote} onChange={(e) => setRemote(e.target.value)}>
              {["remote_only", "remote_preferred", "hybrid_ok", "onsite_ok", "no_preference"].map((value) => (
                <option key={value} value={value}>{titleCase(value)}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="risk">Risk tolerance</label>
            <select id="risk" value={risk} onChange={(e) => setRisk(e.target.value)}>
              {["low", "medium", "high"].map((value) => (
                <option key={value} value={value}>{titleCase(value)}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="card">
          <h2>Skills</h2>
          <h3>Technical</h3>
          <div className="row" style={{ gap: "0.3rem", marginBottom: "0.7rem" }}>
            {profile.technical_skills.map((skill) => (
              <span key={skill} className="tag">{skill}</span>
            ))}
          </div>
          <h3>Domain</h3>
          <div className="row" style={{ gap: "0.3rem", marginBottom: "0.7rem" }}>
            {profile.domain_skills.map((skill) => (
              <span key={skill} className="tag">{skill}</span>
            ))}
          </div>
          <h3>Proofable (no formal experience, but demonstrable)</h3>
          <div className="row" style={{ gap: "0.3rem" }}>
            {profile.proofable_skills.map((skill) => (
              <span key={skill} className="tag tag-ok">{titleCase(skill)}</span>
            ))}
          </div>
        </div>
      </div>

      <div className="stack" style={{ gap: "1rem" }}>
        <div className="card">
          <h2>Compensation bands</h2>
          <p className="subtle" style={{ marginTop: 0 }}>
            The Compensation score is measured against these, not a market average.
          </p>
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: "0.8rem" }}>
            {BAND_KEYS.map(([key, label]) => (
              <NumberField
                key={key}
                label={label}
                value={bands[key]}
                onChange={(value) => setBands((prev) => ({ ...prev, [key]: value }))}
                step={5000}
              />
            ))}
          </div>
          {!bandsValid && (
            <div className="banner banner-error" style={{ marginTop: "0.8rem", marginBottom: 0 }}>
              Bands must increase from poor to excellent.
            </div>
          )}
        </div>

        <div className="card">
          <h2>Dimension weights</h2>
          <p className="subtle" style={{ marginTop: 0 }}>
            Weights are normalised, so they need not sum to exactly 1. Current total:{" "}
            <strong>{weightTotal.toFixed(2)}</strong>.
          </p>
          <div className="stack" style={{ gap: "0.7rem" }}>
            {WEIGHT_KEYS.map(([key, label]) => (
              <div key={key}>
                <label htmlFor={`weight-${key}`}>
                  {label} — {Math.round((weights[key] / weightTotal) * 100)}% effective
                </label>
                <input
                  id={`weight-${key}`}
                  type="range"
                  min={0}
                  max={0.5}
                  step={0.01}
                  value={weights[key]}
                  onChange={(event) =>
                    setWeights((prev) => ({ ...prev, [key]: Number(event.target.value) }))
                  }
                  style={{ width: "100%" }}
                />
              </div>
            ))}
            <div>
              <label htmlFor="risk-penalty">
                Subtract risk from the overall score — {Math.round(riskPenalty * 100)}%
              </label>
              <input
                id="risk-penalty"
                type="range"
                min={0}
                max={0.5}
                step={0.05}
                value={riskPenalty}
                onChange={(event) => setRiskPenalty(Number(event.target.value))}
                style={{ width: "100%" }}
              />
              <div className="hint">
                At 0% risk is reported but never subtracted, which is the default posture.
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <button className="btn btn-primary" type="submit" disabled={pending || !bandsValid}>
            {pending ? "Saving…" : "Save profile"}
          </button>
          {saved && (
            <div className="banner banner-info" style={{ marginTop: "0.8rem", marginBottom: 0 }}>
              Saved. Re-score an opportunity to apply the new weights.
            </div>
          )}
          {error && (
            <div className="banner banner-error" style={{ marginTop: "0.8rem", marginBottom: 0 }}>
              {error}
            </div>
          )}
        </div>
      </div>
    </form>
  );
}

function NumberField({
  label,
  value,
  onChange,
  step = 1,
  min = 0,
  max,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: number;
  min?: number;
  max?: number;
}) {
  const id = `field-${label.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <div className="field" style={{ marginBottom: 0 }}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="number"
        value={value}
        step={step}
        min={min}
        max={max}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </div>
  );
}
