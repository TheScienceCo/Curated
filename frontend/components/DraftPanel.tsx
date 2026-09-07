"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { titleCase } from "@/lib/format";
import type { DraftTone, RecruiterMessage } from "@/lib/types";

const TONES: DraftTone[] = ["professional", "warm", "direct", "humorous"];

/**
 * The human-in-the-loop gate.
 *
 * The system never sends anything. Approving here records that the user is
 * happy with the wording — sending remains a manual act in their own mail
 * client, which is the whole safety model in v1.
 */
export function DraftPanel({
  opportunityId,
  message,
}: {
  opportunityId: string;
  message: RecruiterMessage | null;
}) {
  const router = useRouter();
  const [body, setBody] = useState(message?.approved_response ?? message?.response_draft ?? "");
  const [tone, setTone] = useState<DraftTone>("professional");
  const [status, setStatus] = useState(message?.status ?? "new");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const messageId = message?.id ?? null;
  const edited = body !== (message?.response_draft ?? "");

  async function regenerate() {
    setPending("regenerate");
    setError(null);
    setNotice(null);
    try {
      const draft = await api.draftResponse(opportunityId, { tone });
      setBody(draft.body);
      setStatus("draft_generated");
      setNotice(
        draft.generated_by === "llm-polished"
          ? "Regenerated and polished by the configured model."
          : "Regenerated from the deterministic template.",
      );
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate a draft.");
    } finally {
      setPending(null);
    }
  }

  async function updateStatus(next: string) {
    if (!messageId) {
      setError("Generate a draft first.");
      return;
    }
    setPending(next);
    setError(null);
    setNotice(null);
    try {
      const updated = await api.updateMessage(messageId, {
        status: next,
        approved_response: next === "approved" || next === "edited" ? body : null,
      });
      setStatus(updated.status);
      setNotice(
        next === "approved" || next === "edited"
          ? "Saved. Copy the text and send it yourself — the system never sends anything."
          : `Marked ${titleCase(next)}.`,
      );
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update the draft.");
    } finally {
      setPending(null);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(body);
      setNotice("Copied to the clipboard.");
    } catch {
      setError("Clipboard access was blocked; select the text and copy it manually.");
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <h2>Recruiter reply</h2>
        <span className="tag">{titleCase(status)}</span>
      </div>

      <div className="banner banner-info">
        Drafts are never sent automatically. Approve to record your sign-off, then send it
        yourself.
      </div>

      <div className="field">
        <textarea
          value={body}
          onChange={(event) => setBody(event.target.value)}
          placeholder="No draft yet — generate one below."
          style={{ minHeight: 220 }}
        />
        {edited && body && <div className="hint">Edited from the generated draft.</div>}
      </div>

      <div className="row" style={{ gap: "0.5rem", marginBottom: "0.7rem" }}>
        <select
          value={tone}
          onChange={(event) => setTone(event.target.value as DraftTone)}
          style={{ width: "auto" }}
          aria-label="Draft tone"
        >
          {TONES.map((value) => (
            <option key={value} value={value}>
              {titleCase(value)}
            </option>
          ))}
        </select>
        <button className="btn" onClick={regenerate} disabled={pending !== null}>
          {pending === "regenerate" ? "Generating…" : "Regenerate"}
        </button>
        <button className="btn" onClick={copy} disabled={!body}>
          Copy
        </button>
      </div>

      <div className="row" style={{ gap: "0.5rem" }}>
        <button
          className="btn btn-primary"
          onClick={() => updateStatus(edited ? "edited" : "approved")}
          disabled={pending !== null || !body}
        >
          {pending === "approved" || pending === "edited" ? "Saving…" : "Approve"}
        </button>
        <button
          className="btn"
          onClick={() => updateStatus("rejected")}
          disabled={pending !== null || !messageId}
        >
          Reject draft
        </button>
        <button
          className="btn"
          onClick={() => updateStatus("ignored")}
          disabled={pending !== null || !messageId}
        >
          Ignore
        </button>
      </div>

      {notice && (
        <div className="banner banner-info" style={{ marginTop: "0.8rem", marginBottom: 0 }}>
          {notice}
        </div>
      )}
      {error && (
        <div className="banner banner-error" style={{ marginTop: "0.8rem", marginBottom: 0 }}>
          {error}
        </div>
      )}
    </div>
  );
}
