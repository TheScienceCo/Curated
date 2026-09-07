import { invertedScoreTone, scoreTone } from "@/lib/format";

interface ScoreChipProps {
  value: number;
  /** Risk is scored the other way round: high is bad. */
  inverted?: boolean;
}

export function ScoreChip({ value, inverted = false }: ScoreChipProps) {
  const tone = inverted ? invertedScoreTone(value) : scoreTone(value);
  return <span className={`score score-${tone}`}>{Math.round(value)}</span>;
}

interface ScoreBarProps {
  label: string;
  value: number;
  weight?: number;
  inverted?: boolean;
  description?: string;
}

export function ScoreBar({ label, value, weight, inverted = false, description }: ScoreBarProps) {
  const tone = inverted ? invertedScoreTone(value) : scoreTone(value);
  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", gap: "0.5rem" }}>
        <span style={{ fontSize: "0.85rem", fontWeight: 560 }}>{label}</span>
        <span className="row" style={{ gap: "0.4rem" }}>
          {weight !== undefined && (
            <span className="subtle">{Math.round(weight * 100)}%</span>
          )}
          <ScoreChip value={value} inverted={inverted} />
        </span>
      </div>
      <div className={`bar bar-${tone}`}>
        <div style={{ width: `${Math.max(2, Math.min(100, value))}%` }} />
      </div>
      {description && <div className="hint">{description}</div>}
    </div>
  );
}
