"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ScoreChip } from "@/components/Score";
import { ACTION_LABELS, ACTION_TONE, formatSalary, titleCase } from "@/lib/format";
import type { DashboardRow } from "@/lib/types";

type SortKey =
  | "overall_score"
  | "fit_score"
  | "career_capital_score"
  | "proofability_score"
  | "compensation_score"
  | "upside_score"
  | "risk_score"
  | "salary"
  | "company"
  | "title";

const COLUMNS: { key: SortKey; label: string; numeric: boolean; inverted?: boolean }[] = [
  { key: "company", label: "Company", numeric: false },
  { key: "title", label: "Title", numeric: false },
  { key: "salary", label: "Salary", numeric: true },
  { key: "overall_score", label: "Overall", numeric: true },
  { key: "fit_score", label: "Fit", numeric: true },
  { key: "career_capital_score", label: "Capital", numeric: true },
  { key: "proofability_score", label: "Proof", numeric: true },
  { key: "compensation_score", label: "Comp", numeric: true },
  { key: "upside_score", label: "Upside", numeric: true },
  { key: "risk_score", label: "Risk", numeric: true, inverted: true },
];

export function DashboardTable({ rows }: { rows: DashboardRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("overall_score");
  const [descending, setDescending] = useState(true);

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      const left = sortValue(a, sortKey);
      const right = sortValue(b, sortKey);
      if (typeof left === "string" || typeof right === "string") {
        return String(left).localeCompare(String(right));
      }
      return left - right;
    });
    return descending ? copy.reverse() : copy;
  }, [rows, sortKey, descending]);

  function toggle(key: SortKey) {
    if (key === sortKey) {
      setDescending((value) => !value);
    } else {
      setSortKey(key);
      setDescending(true);
    }
  }

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {COLUMNS.map((column) => (
                <th key={column.key} className={column.numeric ? "num" : undefined}>
                  <button type="button" onClick={() => toggle(column.key)}>
                    {column.label}
                    {sortKey === column.key && <span aria-hidden="true">{descending ? "▾" : "▴"}</span>}
                  </button>
                </th>
              ))}
              <th>Location</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr key={row.opportunity_id}>
                <td>{row.company ?? <span className="subtle">Unknown</span>}</td>
                <td className="wrap">
                  <Link
                    href={`/opportunities/${row.opportunity_id}`}
                    style={{ fontWeight: 560, color: "var(--accent)" }}
                  >
                    {row.title ?? "Untitled opportunity"}
                  </Link>
                  {row.hard_gate_count > 0 && (
                    <span className="tag tag-warn" style={{ marginLeft: "0.4rem" }}>
                      hard gate
                    </span>
                  )}
                  {row.job_family && (
                    <div className="subtle">{titleCase(row.job_family)}</div>
                  )}
                </td>
                <td className="num">
                  {formatSalary(row.salary_min, row.salary_max, row.salary_currency)}
                </td>
                <td className="num">
                  <ScoreChip value={row.overall_score} />
                </td>
                <td className="num"><ScoreChip value={row.fit_score} /></td>
                <td className="num"><ScoreChip value={row.career_capital_score} /></td>
                <td className="num"><ScoreChip value={row.proofability_score} /></td>
                <td className="num"><ScoreChip value={row.compensation_score} /></td>
                <td className="num"><ScoreChip value={row.upside_score} /></td>
                <td className="num"><ScoreChip value={row.risk_score} inverted /></td>
                <td>
                  {row.location ?? "—"}
                  <div className="subtle">{titleCase(row.remote_status)}</div>
                </td>
                <td>
                  <span className={`pill ${ACTION_TONE[row.recommended_action]}`}>
                    {ACTION_LABELS[row.recommended_action]}
                  </span>
                  {row.decision && <div className="subtle">You: {titleCase(row.decision)}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function sortValue(row: DashboardRow, key: SortKey): number | string {
  switch (key) {
    case "salary":
      return row.salary_max ?? row.salary_min ?? 0;
    case "company":
      return row.company ?? "zzz";
    case "title":
      return row.title ?? "zzz";
    default:
      return row[key];
  }
}
