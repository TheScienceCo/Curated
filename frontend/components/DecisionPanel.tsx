"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatDate, titleCase } from "@/lib/format";
import type { DecisionType, UserDecisionRecord } from "@/lib/types";

const DECISIONS: { value: DecisionType; label: string }[] = [
  { value: "pursue", label: "Pursue" },
  { value: "maybe", label: "Maybe" },
  { value: "reject", label: "Reject" },
  { value: "ignore", label: "Ignore" },
  { value: "responded", label: "Responded" },
  { value: "interviewed", label: "Interviewed" },
  { value: "offer", label: "Received offer" },
  { value: "accepted_offer", label: "Accepted offer" },
  { value: "declined_offer", label: "Declined offer" },
];

/** §16 - every action becomes a labelled example for future ranking work. */
export function DecisionPanel({
  opportunityId,
  decisions,
}: {
  opportunityId: string;
  decisions: UserDecisionRecord[];
}) {
  const router = useRouter();
  const [decision, setDecision] = useState<DecisionType>("pursue");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await api.decide({
        opportunity_id: opportunityId,
        decision,
        reason: reason.trim() || null,
      });
      setReason("");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record the decision.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="card">
      <h2>Your decision</h2>
      <p className="subtle" style={{ marginTop: 0 }}>
        Recorded as feedback. v1 does not retrain anything — it accumulates honest labels first.
      </p>

      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="decision">Decision</label>
          <select
            id="decision"
            value={decision}
            onChange={(event) => setDecision(event.target.value as DecisionType)}
          >
            {DECISIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="reason">Why (optional)</label>
          <input
            id="reason"
            type="text"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="e.g. comp is fine but the commute isn't"
          />
        </div>
        <button className="btn btn-primary" type="submit" disabled={pending}>
          {pending ? "Saving…" : "Record decision"}
        </button>
      </form>

      {error && (
        <div className="banner banner-error" style={{ marginTop: "0.8rem", marginBottom: 0 }}>
          {error}
        </div>
      )}

      {decisions.length > 0 && (
        <details className="disclosure" open>
          <summary>History ({decisions.length})</summary>
          <ul className="stack" style={{ gap: "0.35rem", paddingLeft: "1.1rem", margin: 0 }}>
            {decisions.map((item) => (
              <li key={item.id} style={{ fontSize: "0.87rem" }}>
                <strong>{titleCase(item.decision)}</strong>{" "}
                <span className="subtle">{formatDate(item.timestamp)}</span>
                {item.reason && <div className="subtle">{item.reason}</div>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
