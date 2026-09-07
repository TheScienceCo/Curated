import { api, ApiError } from "@/lib/api";
import { ResumeManager } from "@/components/ResumeManager";
import type { ResumeDocument } from "@/lib/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "Résumés | Job Intelligence Agent" };

export default async function ResumesPage() {
  let resumes: ResumeDocument[] = [];
  let error: string | null = null;

  try {
    resumes = await api.resumes();
  } catch (err) {
    error = err instanceof ApiError ? err.message : "Could not load résumés.";
  }

  return (
    <>
      <div className="page-header">
        <h1>Résumé variants</h1>
        <p>
          Keep one variant per audience. For each job the system recommends which to send, what to
          lead with, and what to shorten — always from what the résumé already says.
        </p>
      </div>
      {error && <div className="banner banner-error">{error}</div>}
      <ResumeManager resumes={resumes} />
    </>
  );
}
