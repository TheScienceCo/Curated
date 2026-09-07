"use client";

import { useEffect } from "react";

/**
 * Route-level error boundary.
 *
 * The overwhelmingly likely cause in this app is that the API is not running,
 * so the copy says that rather than "something went wrong".
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <>
      <div className="page-header">
        <h1>Something broke</h1>
      </div>
      <div className="card">
        <div className="banner banner-error">{error.message || "An unexpected error occurred."}</div>
        <p className="muted">
          The most common cause is the API not being reachable. Check that the backend is running
          on <code>http://localhost:8000</code> — <code>docker compose up</code>, or{" "}
          <code>uvicorn app.main:app --reload</code> from <code>backend/</code>.
        </p>
        <button className="btn btn-primary" onClick={reset}>
          Try again
        </button>
      </div>
    </>
  );
}
