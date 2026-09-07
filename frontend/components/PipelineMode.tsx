import { api } from "@/lib/api";

/**
 * Says which pipeline is actually running.
 *
 * Whether the LLM layer is active changes what the app can extract, so it
 * belongs in the chrome rather than buried in an env file. Rendered on the
 * server; a failure here must never take the nav down.
 */
export async function PipelineMode() {
  try {
    const health = await api.health();
    const llm = health.llm_provider !== "mock" && health.extraction_mode.startsWith("llm");
    return (
      <span
        className={`mode-badge ${llm ? "mode-badge-llm" : ""}`}
        title={
          llm
            ? `Deterministic extraction, enriched by ${health.llm_provider}.`
            : "Deterministic extraction only. Set LLM_PROVIDER and an API key to add the language layer."
        }
      >
        {llm ? `rules + ${health.llm_provider}` : "rules only"}
      </span>
    );
  } catch {
    return <span className="mode-badge">API offline</span>;
  }
}
