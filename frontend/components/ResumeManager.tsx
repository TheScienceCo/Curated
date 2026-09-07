"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatDate, titleCase } from "@/lib/format";
import type { ResumeDocument } from "@/lib/types";

export function ResumeManager({ resumes }: { resumes: ResumeDocument[] }) {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [rawText, setRawText] = useState("");
  const [families, setFamilies] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      await api.createResume({
        title: title.trim(),
        raw_text: rawText,
        target_families: families
          .split(",")
          .map((value) => value.trim().toLowerCase().replace(/\s+/g, "_"))
          .filter(Boolean),
      });
      setTitle("");
      setRawText("");
      setFamilies("");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the résumé.");
    } finally {
      setPending(false);
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await api.deleteResume(id);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete the résumé.");
    }
  }

  return (
    <div className="grid grid-2" style={{ alignItems: "start" }}>
      <div className="stack" style={{ gap: "1rem" }}>
        {resumes.length === 0 && (
          <div className="card">
            <div className="empty">No résumé variants yet.</div>
          </div>
        )}
        {resumes.map((resume) => (
          <div key={resume.id} className="card">
            <div className="card-header">
              <h2>{resume.title}</h2>
              <div className="row" style={{ gap: "0.4rem" }}>
                {resume.active ? (
                  <span className="tag tag-ok">active</span>
                ) : (
                  <span className="tag">inactive</span>
                )}
                <button
                  className="btn"
                  style={{ padding: "0.2rem 0.55rem", fontSize: "0.78rem" }}
                  onClick={() => remove(resume.id)}
                >
                  Delete
                </button>
              </div>
            </div>
            <div className="subtle">Added {formatDate(resume.created_at)}</div>

            {resume.target_families.length > 0 && (
              <>
                <h3 style={{ marginTop: "0.7rem" }}>Targets</h3>
                <div className="row" style={{ gap: "0.3rem" }}>
                  {resume.target_families.map((family) => (
                    <span key={family} className="tag">{titleCase(family)}</span>
                  ))}
                </div>
              </>
            )}

            <h3 style={{ marginTop: "0.7rem" }}>Detected skills ({resume.skills.length})</h3>
            <div className="row" style={{ gap: "0.3rem" }}>
              {resume.skills.slice(0, 24).map((skill) => (
                <span key={skill} className="tag">{titleCase(skill)}</span>
              ))}
            </div>

            <details className="disclosure">
              <summary>Full text</summary>
              <div className="jd">{resume.raw_text}</div>
            </details>
          </div>
        ))}
      </div>

      <form className="card" onSubmit={submit}>
        <h2>Add a variant</h2>
        <div className="field">
          <label htmlFor="resume-title">Title</label>
          <input
            id="resume-title"
            type="text"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Forward Deployed AI Resume"
            required
          />
        </div>
        <div className="field">
          <label htmlFor="resume-families">Target job families (comma separated)</label>
          <input
            id="resume-families"
            type="text"
            value={families}
            onChange={(event) => setFamilies(event.target.value)}
            placeholder="forward_deployed_engineer, ai_engineer"
          />
          <div className="hint">Used to break ties when two variants cover the same skills.</div>
        </div>
        <div className="field">
          <label htmlFor="resume-text">Résumé text</label>
          <textarea
            id="resume-text"
            value={rawText}
            onChange={(event) => setRawText(event.target.value)}
            placeholder="Paste the plain text of this résumé variant…"
            required
            style={{ minHeight: 260 }}
          />
          <div className="hint">
            Skills are mined from this text, so paste the real content rather than a summary.
          </div>
        </div>
        <button className="btn btn-primary" type="submit" disabled={pending || !title || !rawText}>
          {pending ? "Saving…" : "Add résumé"}
        </button>
        {error && (
          <div className="banner banner-error" style={{ marginTop: "0.8rem", marginBottom: 0 }}>
            {error}
          </div>
        )}
      </form>
    </div>
  );
}
