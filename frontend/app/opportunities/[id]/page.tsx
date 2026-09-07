import Link from "next/link";
import { notFound } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { OpportunityDetail } from "@/components/OpportunityDetail";
import type { JobDetail, ResumeMatchResult } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function OpportunityPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let detail: JobDetail;
  try {
    detail = await api.job(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    return (
      <>
        <div className="page-header">
          <h1>Opportunity</h1>
        </div>
        <div className="banner banner-error">
          {err instanceof ApiError ? err.message : "Failed to load this opportunity."}
        </div>
        <Link href="/">← Back to the dashboard</Link>
      </>
    );
  }

  // Résumé matching is a separate call so a missing-résumé setup degrades to
  // "no recommendation" rather than failing the whole page.
  let resumeMatch: ResumeMatchResult | null = null;
  try {
    resumeMatch = await api.resumeMatch(id);
  } catch {
    resumeMatch = null;
  }

  return <OpportunityDetail detail={detail} resumeMatch={resumeMatch} />;
}
