"use client";

import Link from "next/link";
import { useState } from "react";
import { DashboardTable } from "@/components/DashboardTable";
import { ClearanceJobsModal } from "@/components/ClearanceJobsModal";
import { BulkImportModal } from "@/components/BulkImportModal";
import type { DashboardRow, CandidateProfile } from "@/lib/types";

interface DashboardClientProps {
  rows: DashboardRow[];
  stats: {
    count: number;
    by_action: Record<string, number>;
    average_overall: number;
    hard_gated: number;
    median_salary_max: number | null;
  };
  candidate: CandidateProfile | null;
}

export function DashboardClient({ rows, stats, candidate }: DashboardClientProps) {
  const [isClearanceJobsOpen, setIsClearanceJobsOpen] = useState(false);
  const [isBulkImportOpen, setIsBulkImportOpen] = useState(false);

  return (
    <>
      {stats.count > 0 && (
        <div className="grid grid-3" style={{ marginBottom: "1rem" }}>
          <StatCard label="Opportunities" value={String(stats.count)} />
          <StatCard label="Average overall" value={stats.average_overall.toFixed(1)} />
          <StatCard
            label="Median top-of-range"
            value={
              stats.median_salary_max ? `$${Math.round(stats.median_salary_max / 1000)}k` : "—"
            }
          />
          <StatCard
            label="Blocked by a hard gate"
            value={String(stats.hard_gated)}
            tone={stats.hard_gated > 0 ? "warn" : undefined}
          />
        </div>
      )}

      <div style={{ marginBottom: "1.5rem", display: "flex", gap: "0.5rem" }}>
        {stats.count > 0 && (
          <>
            <button
              className="btn btn-secondary"
              onClick={() => setIsBulkImportOpen(true)}
              style={{ padding: "0.45rem 0.95rem" }}
            >
              + Bulk import
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => setIsClearanceJobsOpen(true)}
              style={{ padding: "0.45rem 0.95rem" }}
            >
              + ClearanceJobs
            </button>
          </>
        )}
        {stats.count === 0 && (
          <div className="card">
            <div className="empty">
              <p>No opportunities yet.</p>
              <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", flexWrap: "wrap" }}>
                <Link
                  href="/analyze"
                  className="btn btn-primary"
                  style={{ padding: "0.45rem 0.95rem" }}
                >
                  Analyze message →
                </Link>
                <button
                  className="btn btn-secondary"
                  onClick={() => setIsBulkImportOpen(true)}
                  style={{ padding: "0.45rem 0.95rem" }}
                >
                  + Bulk import
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={() => setIsClearanceJobsOpen(true)}
                  style={{ padding: "0.45rem 0.95rem" }}
                >
                  + ClearanceJobs
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {rows.length > 0 && <DashboardTable rows={rows} />}

      <ClearanceJobsModal isOpen={isClearanceJobsOpen} onClose={() => setIsClearanceJobsOpen(false)} candidate={candidate} />
      <BulkImportModal isOpen={isBulkImportOpen} onClose={() => setIsBulkImportOpen(false)} />
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
