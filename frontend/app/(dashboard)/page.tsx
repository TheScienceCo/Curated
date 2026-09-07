import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { DashboardTable } from "@/components/DashboardTable";
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

      {stats && stats.count > 0 && (
        <div className="grid grid-3" style={{ marginBottom: "1rem" }}>
          <StatCard label="Opportunities" value={String(stats.count)} />
          <StatCard label="Average overall" value={stats.average_overall.toFixed(1)} />
          <StatCard
            label="Median top-of-range"
            value={
              stats.median_salary_max
                ? `$${Math.round(stats.median_salary_max / 1000)}k`
                : "—"
            }
          />
          <StatCard
            label="Blocked by a hard gate"
            value={String(stats.hard_gated)}
            tone={stats.hard_gated > 0 ? "warn" : undefined}
          />
        </div>
      )}

      {rows.length === 0 ? (
        <div className="card">
          <div className="empty">
            <p>No opportunities yet.</p>
            <Link href="/analyze" className="btn btn-primary" style={{ padding: "0.45rem 0.95rem" }}>
              Analyze your first recruiter message →
            </Link>
          </div>
        </div>
      ) : (
        <DashboardTable rows={rows} />
      )}
    </>
  );
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "warn";
}) {
  return (
    <div className="card" style={{ padding: "0.8rem 1rem" }}>
      <div className="subtle">{label}</div>
      <div
        style={{
          fontSize: "1.5rem",
          fontWeight: 640,
          fontVariantNumeric: "tabular-nums",
          color: tone === "warn" ? "var(--weak)" : undefined,
        }}
      >
        {value}
      </div>
    </div>
  );
}
