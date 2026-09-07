import type { ScoreReason } from "@/lib/types";

const MARKERS: Record<ScoreReason["kind"], string> = {
  positive: "+",
  negative: "−",
  missing: "?",
  neutral: "·",
};

/**
 * Renders the "why" behind a score. The signed impact is shown so a user can
 * see which reasons actually moved the number and which are commentary.
 */
export function ReasonList({ reasons }: { reasons: ScoreReason[] }) {
  if (reasons.length === 0) {
    return <p className="subtle">No reasons recorded.</p>;
  }
  return (
    <ul className="reasons">
      {reasons.map((reason, index) => (
        <li key={index} className={`reason-${reason.kind}`}>
          <span className="reason-marker" aria-hidden="true">
            {reason.impact ? Math.round(reason.impact) : MARKERS[reason.kind]}
          </span>
          <span>{reason.text}</span>
        </li>
      ))}
    </ul>
  );
}
