import type { MissingField } from "@/lib/types";

/** §5 - what the recruiter did not tell you, in priority order. */
export function MissingInfo({ fields }: { fields: MissingField[] }) {
  if (fields.length === 0) {
    return <p className="subtle">Nothing important is missing.</p>;
  }
  return (
    <ol className="stack" style={{ gap: "0.5rem", margin: 0, paddingLeft: "1.1rem" }}>
      {fields.map((field) => (
        <li key={field.field}>
          <strong style={{ fontSize: "0.89rem" }}>{field.label}</strong>
          {field.priority <= 5 && (
            <span className="tag tag-warn" style={{ marginLeft: "0.4rem" }}>
              blocking
            </span>
          )}
          <div className="subtle">{field.rationale}</div>
        </li>
      ))}
    </ol>
  );
}
