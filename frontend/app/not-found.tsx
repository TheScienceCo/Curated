import Link from "next/link";

export default function NotFound() {
  return (
    <>
      <div className="page-header">
        <h1>Not found</h1>
        <p>
          That opportunity does not exist, or it was deleted. It may have been removed from the
          dashboard after a decision.
        </p>
      </div>
      <div className="card">
        <Link href="/" className="btn btn-primary" style={{ padding: "0.45rem 0.95rem" }}>
          ← Back to the dashboard
        </Link>
      </div>
    </>
  );
}
