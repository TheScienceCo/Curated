/**
 * Typed API client.
 *
 * Server components call the API directly over the internal Docker network;
 * client components go through the browser-visible URL. `apiBaseUrl()` picks
 * the right one, which is why there are two environment variables.
 */

import type {
  AnalyzeResponse,
  CandidateProfile,
  DashboardResponse,
  Draft,
  DraftTone,
  EquityAnalysis,
  JobDetail,
  RecruiterMessage,
  ResumeDocument,
  ResumeMatchResult,
} from "./types";

const BROWSER_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const SERVER_BASE = process.env.API_INTERNAL_URL ?? BROWSER_BASE;

export function apiBaseUrl(): string {
  return typeof window === "undefined" ? SERVER_BASE : BROWSER_BASE;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Server components render fresh data on every request by default. */
  revalidate?: number | false;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, revalidate, headers, ...rest } = options;
  const url = `${apiBaseUrl()}${path}`;

  let response: Response;
  try {
    response = await fetch(url, {
      ...rest,
      headers: {
        "Content-Type": "application/json",
        ...(headers ?? {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: revalidate === undefined ? "no-store" : undefined,
      next: revalidate === undefined ? undefined : { revalidate: revalidate || 0 },
    });
  } catch (cause) {
    throw new ApiError(
      `Could not reach the API at ${apiBaseUrl()}. Is the backend running?`,
      0,
      cause,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  const payload = text ? safeParse(text) : null;

  if (!response.ok) {
    const message =
      (payload as { error?: { message?: string } } | null)?.error?.message ??
      `Request to ${path} failed with ${response.status}`;
    throw new ApiError(message, response.status, payload);
  }

  return payload as T;
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

// --- Endpoints -------------------------------------------------------------

export const api = {
  health: () => apiFetch<{ status: string; llm_provider: string; extraction_mode: string }>("/health"),

  dashboard: (params: { sort?: string; order?: "asc" | "desc" } = {}) => {
    const query = new URLSearchParams();
    if (params.sort) query.set("sort", params.sort);
    if (params.order) query.set("order", params.order);
    const suffix = query.toString() ? `?${query}` : "";
    return apiFetch<DashboardResponse>(`/api/dashboard${suffix}`);
  },

  analyze: (body: {
    raw_text: string;
    source_url?: string | null;
    company?: string | null;
    title?: string | null;
    recruiter_name?: string | null;
    channel?: string;
    save?: boolean;
    generate_draft?: boolean;
    tone?: DraftTone;
    use_llm?: boolean;
  }) => apiFetch<AnalyzeResponse>("/api/jobs/analyze", { method: "POST", body }),

  job: (id: string) => apiFetch<JobDetail>(`/api/jobs/${id}`),

  updateJob: (id: string, body: Record<string, unknown>) =>
    apiFetch<unknown>(`/api/jobs/${id}`, { method: "PATCH", body }),

  deleteJob: (id: string) => apiFetch<void>(`/api/jobs/${id}`, { method: "DELETE" }),

  rescore: (id: string) => apiFetch<unknown>(`/api/jobs/${id}/score`, { method: "POST" }),

  draftResponse: (id: string, body: { tone: DraftTone; intent?: string; polish?: boolean }) =>
    apiFetch<Draft>(`/api/jobs/${id}/draft-response`, { method: "POST", body }),

  resumeMatch: (id: string) =>
    apiFetch<ResumeMatchResult>(`/api/jobs/${id}/resume-match`, { method: "POST" }),

  profile: () => apiFetch<CandidateProfile>("/api/profile"),

  updateProfile: (body: Record<string, unknown>) =>
    apiFetch<CandidateProfile>("/api/profile", { method: "PATCH", body }),

  resumes: () => apiFetch<ResumeDocument[]>("/api/resumes"),

  createResume: (body: { title: string; raw_text: string; target_families?: string[] }) =>
    apiFetch<ResumeDocument>("/api/resumes", { method: "POST", body }),

  deleteResume: (id: string) => apiFetch<void>(`/api/resumes/${id}`, { method: "DELETE" }),

  decide: (body: {
    opportunity_id: string;
    decision: string;
    reason?: string | null;
    edited_response?: string | null;
  }) => apiFetch<unknown>("/api/decisions", { method: "POST", body }),

  updateMessage: (id: string, body: { status: string; approved_response?: string | null }) =>
    apiFetch<RecruiterMessage>(`/api/messages/${id}`, { method: "PATCH", body }),

  equity: (body: {
    equity_percent: number;
    dilution_percent?: number;
    current_valuation?: number | null;
    strike_price?: number | null;
    shares?: number | null;
  }) => apiFetch<EquityAnalysis>("/api/equity/calculate", { method: "POST", body }),
};
