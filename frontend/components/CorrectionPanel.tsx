"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { CLEARANCE_LABELS, POLYGRAPH_LABELS } from "@/lib/format";
import type { JobOpportunity } from "@/lib/types";

/**
 * Correct what the extractor got wrong.
 *
 * Extraction is best-effort, and the honest response to that is an edit form
 * rather than a disclaimer. Corrections are marked high-confidence server-side
 * (a human typed them), and re-scoring picks them up immediately — which is
 * the point: change the polygraph here and watch the verdict change.
 */
export function CorrectionPanel({ job }: { job: JobOpportunity }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const [form, setForm] = useState({
    title: job.title ?? "",
    company: job.company ?? "",
    location: job.location ?? "",
    remote_status: job.remote_status,
    salary_min: job.salary_min ?? "",
    salary_max: job.salary_max ?? "",
    security_clearance: job.security_clearance,
    polygraph_requirement: job.polygraph_requirement,
    hours: job.hours ?? "",
    travel: job.travel ?? "",
    equity: job.equity === null ? "" : String(job.equity),
    equity_percent_min: job.equity_percent_min ?? "",
    company_stage: job.company_stage ?? "",
    notes: job.notes ?? "",
  });

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  }

  /** Send only what actually changed, so PATCH stays a partial update. */
  function buildPayload(): Record<string, unknown> {
    const payload: Record<string, unknown> = {};
    const original: Record<string, unknown> = {
      title: job.title ?? "",
      company: job.company ?? "",
      location: job.location ?? "",
      remote_status: job.remote_status,
      salary_min: job.salary_min ?? "",
      salary_max: job.salary_max ?? "",
      security_clearance: job.security_clearance,
      polygraph_requirement: job.polygraph_requirement,
      hours: job.hours ?? "",
      travel: job.travel ?? "",
      equity: job.equity === null ? "" : String(job.equity),
      equity_percent_min: job.equity_percent_min ?? "",
      company_stage: job.company_stage ?? "",
      notes: job.notes ?? "",
    };

    for (const [key, value] of Object.entries(form)) {
      if (value === original[key]) continue;
      if (key === "equity") {
        payload[key] = value === "" ? null : value === "true";
      } else if (["salary_min", "salary_max", "hours", "travel", "equity_percent_min"].includes(key)) {
        payload[key] = value === "" ? null : Number(value);
      } else {
        payload[key] = value === "" ? null : value;
      }
    }
    return payload;
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const payload = buildPayload();
    if (Object.keys(payload).length === 0) {
      setError("Nothing changed.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      await api.updateJob(job.id, payload);
      // Re-score immediately: a corrected polygraph or salary should change
      // the verdict without the user having to ask twice.
      await api.rescore(job.id);
      setSaved(true);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the corrections.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <h2>Correct the extraction</h2>
        <button className="btn" onClick={() => setOpen((value) => !value)}>
          {open ? "Close" : "Edit fields"}
        </button>
      </div>

      {!open ? (
        <p className="subtle" style={{ margin: 0 }}>
          Extraction is best-effort. Anything it read wrong can be fixed here, and the
          opportunity is re-scored on save.
        </p>
      ) : (
        <form onSubmit={save}>
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: "0.7rem" }}>
            <Text label="Title" value={form.title} onChange={(v) => set("title", v)} />
            <Text label="Company" value={form.company} onChange={(v) => set("company", v)} />
            <Text label="Location" value={form.location} onChange={(v) => set("location", v)} />
            <Select
              label="Remote status"
              value={form.remote_status}
              onChange={(v) => set("remote_status", v as typeof form.remote_status)}
              options={["remote", "hybrid", "onsite", "unspecified"]}
            />
            <Num label="Salary min ($)" value={form.salary_min} onChange={(v) => set("salary_min", v)} />
            <Num label="Salary max ($)" value={form.salary_max} onChange={(v) => set("salary_max", v)} />
            <Select
              label="Clearance"
              value={form.security_clearance}
              onChange={(v) => set("security_clearance", v)}
              options={Object.keys(CLEARANCE_LABELS)}
              labels={CLEARANCE_LABELS}
            />
            <Select
              label="Polygraph"
              value={form.polygraph_requirement}
              onChange={(v) => set("polygraph_requirement", v)}
              options={Object.keys(POLYGRAPH_LABELS)}
              labels={POLYGRAPH_LABELS}
            />
            <Num label="Hours / week" value={form.hours} onChange={(v) => set("hours", v)} />
            <Num label="Travel (%)" value={form.travel} onChange={(v) => set("travel", v)} />
            <Select
              label="Equity offered"
              value={form.equity}
              onChange={(v) => set("equity", v)}
              options={["", "true", "false"]}
              labels={{ "": "Not stated", true: "Yes", false: "No" }}
            />
            <Num
              label="Equity (%)"
              value={form.equity_percent_min}
              onChange={(v) => set("equity_percent_min", v)}
              step={0.01}
            />
          </div>

          <div className="field" style={{ marginTop: "0.7rem" }}>
            <label htmlFor="company_stage">Company stage</label>
            <select
              id="company_stage"
              value={form.company_stage}
              onChange={(event) => set("company_stage", event.target.value)}
            >
              <option value="">Unknown</option>
              {[
                "pre_seed", "seed", "series_a", "series_b", "series_c", "growth",
                "late_stage", "public", "established_private", "government", "nonprofit",
              ].map((value) => (
                <option key={value} value={value}>
                  {value.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="job-notes">Your notes</label>
            <textarea
              id="job-notes"
              value={form.notes}
              onChange={(event) => set("notes", event.target.value)}
              placeholder="Context the message doesn't carry — who referred you, what you already know about them…"
              style={{ minHeight: 90 }}
            />
          </div>

          <button className="btn btn-primary" type="submit" disabled={pending}>
            {pending ? "Saving and re-scoring…" : "Save and re-score"}
          </button>

          {saved && (
            <div className="banner banner-info" style={{ marginTop: "0.8rem", marginBottom: 0 }}>
              Saved. Corrected fields are now marked high-confidence, and the scores above
              reflect them.
            </div>
          )}
          {error && (
            <div className="banner banner-error" style={{ marginTop: "0.8rem", marginBottom: 0 }}>
              {error}
            </div>
          )}
        </form>
      )}
    </div>
  );
}

type FieldValue = string | number;

function fieldId(label: string) {
  return `correct-${label.replace(/\W+/g, "-").toLowerCase()}`;
}

function Text({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const id = fieldId(label);
  return (
    <div className="field" style={{ marginBottom: 0 }}>
      <label htmlFor={id}>{label}</label>
      <input id={id} type="text" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function Num({
  label,
  value,
  onChange,
  step = 1,
}: {
  label: string;
  value: FieldValue;
  onChange: (value: string) => void;
  step?: number;
}) {
  const id = fieldId(label);
  return (
    <div className="field" style={{ marginBottom: 0 }}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="number"
        step={step}
        min={0}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  labels,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  labels?: Record<string, string>;
}) {
  const id = fieldId(label);
  return (
    <div className="field" style={{ marginBottom: 0 }}>
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {labels?.[option] ?? option.replace(/_/g, " ")}
          </option>
        ))}
      </select>
    </div>
  );
}
