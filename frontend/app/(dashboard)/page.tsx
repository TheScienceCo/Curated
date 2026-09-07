import { api, ApiError } from "@/lib/api";
import { DashboardClient } from "@/components/DashboardClient";
import type { DashboardResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  let data: DashboardResponse | null = null;
  let error: string | null = null;

  try {
    data = await api.dashboard({ sort: "overall", order: "desc" });
  } catch (err) {
    error = err instanceof ApiError ? err.message : "Failed to load the dashboard.";
  }

  if (error) {
    return (
      <>
        <div className="page-header">
          <h1>Dashboard</h1>
        </div>
        <div className="banner banner-error">{error}</div>
        <p className="muted">
          Start the backend with <code>docker compose up</code>, or run{" "}
          <code>uvicorn app.main:app --reload</code> from the <code>backend/</code> directory.
        </p>
      </>
    );
  }

  const rows = data?.rows ?? [];
  const stats = data?.stats;

  return (
    <>
      <div className="page-header">
        <h1>Top opportunities</h1>
        <p>
          Ranked by overall score. Risk is shown alongside rather than folded in, so a
          high-variance opportunity is visible rather than silently discounted.
        </p>
      </div>

      <DashboardClient rows={rows} stats={stats ?? { count: 0, by_action: {}, average_overall: 0, hard_gated: 0, median_salary_max: null }} candidate={data?.candidate ?? null} />
    </>
  );
}
