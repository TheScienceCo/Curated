/** Display helpers shared across pages. */

import type { RecommendedAction } from "./types";

export function formatSalary(
  min: number | null,
  max: number | null,
  currency = "USD",
): string {
  const symbol = currency === "USD" ? "$" : currency === "GBP" ? "£" : currency === "EUR" ? "€" : "";
  const short = (value: number) =>
    value >= 1000 ? `${symbol}${Math.round(value / 1000)}k` : `${symbol}${value}`;
  if (min && max) return `${short(min)}–${short(max)}`;
  if (max) return `up to ${short(max)}`;
  if (min) return `${short(min)}+`;
  return "Not stated";
}

export function formatMoney(value: number): string {
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

/** Colour band for a 0–100 score. Risk uses `invertedScoreTone` instead. */
export function scoreTone(score: number): "strong" | "good" | "mixed" | "weak" {
  if (score >= 80) return "strong";
  if (score >= 65) return "good";
  if (score >= 45) return "mixed";
  return "weak";
}

/** For risk, where a high number is bad. */
export function invertedScoreTone(score: number): "strong" | "good" | "mixed" | "weak" {
  return scoreTone(100 - score);
}

export const ACTION_LABELS: Record<RecommendedAction, string> = {
  STRONGLY_PURSUE: "Strongly pursue",
  PURSUE: "Pursue",
  WORTH_A_CALL: "Worth a call",
  MAYBE: "Maybe",
  LOW_PRIORITY: "Low priority",
  REJECT: "Reject",
};

export const ACTION_TONE: Record<RecommendedAction, string> = {
  STRONGLY_PURSUE: "action-strong",
  PURSUE: "action-good",
  WORTH_A_CALL: "action-mixed",
  MAYBE: "action-mixed",
  LOW_PRIORITY: "action-weak",
  REJECT: "action-weak",
};

/** Words that must keep their canonical casing when a slug is humanised. */
const ACRONYMS: Record<string, string> = {
  ai: "AI",
  ml: "ML",
  gtm: "GTM",
  seta: "SETA",
  ci: "CI",
  fsp: "FSP",
  ts: "TS",
  sci: "SCI",
  ote: "OTE",
  and: "and",
  of: "of",
  a: "a",
};

export function titleCase(value: string | null | undefined): string {
  if (!value) return "";
  return value
    .replace(/_/g, " ")
    .split(" ")
    .map((word, index) => {
      const lower = word.toLowerCase();
      if (ACRONYMS[lower] && (index > 0 || !/^(and|of|a)$/.test(lower))) {
        return ACRONYMS[lower];
      }
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(" ");
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export const CLEARANCE_LABELS: Record<string, string> = {
  none: "None required",
  public_trust: "Public Trust",
  confidential: "Confidential",
  secret: "Secret",
  top_secret: "Top Secret",
  ts_sci: "TS/SCI",
  unspecified: "Not specified",
};

export const POLYGRAPH_LABELS: Record<string, string> = {
  none: "No polygraph",
  ci: "CI polygraph",
  full_scope: "Full Scope / ESP",
  unspecified_polygraph: "Polygraph (scope unstated)",
  unknown: "Not specified",
};
