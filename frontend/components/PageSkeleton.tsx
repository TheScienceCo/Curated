/** Shared loading frame. Mirrors the page header so the layout does not jump
 *  when the real content arrives. */
export function PageSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <>
      <div className="page-header">
        <div className="skeleton" style={{ height: "1.9rem", width: "16rem" }} />
        <div
          className="skeleton"
          style={{ height: "1rem", width: "min(34rem, 90%)", marginTop: "0.6rem" }}
        />
      </div>
      <div className="card">
        <div className="stack" style={{ gap: "0.7rem" }}>
          {Array.from({ length: rows }, (_, index) => (
            <div
              key={index}
              className="skeleton"
              style={{ height: "1.4rem", width: `${92 - index * 6}%` }}
            />
          ))}
        </div>
      </div>
    </>
  );
}
