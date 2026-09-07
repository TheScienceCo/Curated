import type { ProveItAnalysis } from "@/lib/types";

/**
 * §8 - the three-bucket view.
 *
 * The visual separation is the point: "you're missing 5 years of TypeScript"
 * and "you're missing a Full Scope Polygraph" must never look like the same
 * kind of problem.
 */
export function ProveIt({ analysis }: { analysis: ProveItAnalysis }) {
  return (
    <div className="stack" style={{ gap: "1.1rem" }}>
      <p className="muted" style={{ margin: 0 }}>
        {analysis.summary}
      </p>

      <section>
        <h3>Already demonstrated</h3>
        {analysis.already_demonstrated.length === 0 ? (
          <p className="subtle">Nothing in this job matches your current profile.</p>
        ) : (
          <div className="row" style={{ gap: "0.35rem" }}>
            {analysis.already_demonstrated.map((item) => (
              <span key={item.skill} className="tag tag-ok">
                {item.skill}
                {item.required ? "" : " (preferred)"}
              </span>
            ))}
          </div>
        )}
      </section>

      <section>
        <h3>Learnable / proofable</h3>
        {analysis.learnable.length === 0 ? (
          <p className="subtle">No demonstrable gaps.</p>
        ) : (
          <div className="stack" style={{ gap: "0.7rem" }}>
            {analysis.learnable.map((item) => (
              <div
                key={item.requirement}
                style={{
                  borderLeft: "2px solid var(--mixed)",
                  paddingLeft: "0.7rem",
                }}
              >
                <div className="row" style={{ gap: "0.45rem" }}>
                  <strong style={{ fontSize: "0.9rem" }}>{item.requirement}</strong>
                  {item.learning_difficulty && (
                    <span className="tag">{item.learning_difficulty} difficulty</span>
                  )}
                  {item.interview_readiness && (
                    <span className="tag">{item.interview_readiness}</span>
                  )}
                </div>
                <div className="subtle" style={{ marginTop: "0.15rem" }}>
                  How to demonstrate: {item.how_to_demonstrate}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h3>Hard gates</h3>
        {analysis.hard_gates.length === 0 ? (
          <p className="subtle">
            None. Nothing here requires a credential you cannot demonstrate.
          </p>
        ) : (
          <div className="stack" style={{ gap: "0.7rem" }}>
            {analysis.hard_gates.map((item) => (
              <div
                key={item.requirement}
                style={{ borderLeft: "2px solid var(--weak)", paddingLeft: "0.7rem" }}
              >
                <strong style={{ fontSize: "0.9rem", color: "var(--weak)" }}>
                  {item.requirement}
                </strong>
                <div style={{ fontSize: "0.87rem" }}>{item.detail}</div>
                <div className="subtle">{item.why_hard}</div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
