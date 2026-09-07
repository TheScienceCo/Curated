import { api, ApiError } from "@/lib/api";
import { ExampleGallery } from "@/components/ExampleGallery";
import type { ExampleCase } from "@/lib/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "Example cases | Job Intelligence Agent" };

export default async function ExamplesPage() {
  let examples: ExampleCase[] = [];
  let note = "";
  let error: string | null = null;

  try {
    const body = await api.examples();
    examples = body.examples;
    note = body.note;
  } catch (err) {
    error = err instanceof ApiError ? err.message : "Could not load the example cases.";
  }

  return (
    <>
      <div className="page-header">
        <h1>Example cases</h1>
        <p>
          Seven scenarios chosen to produce different verdicts. Run any of them to see what the
          system concludes and why — the interesting ones are where the obvious answer is wrong.
        </p>
      </div>
      {error && <div className="banner banner-error">{error}</div>}
      {note && <div className="banner banner-info">{note}</div>}
      <ExampleGallery examples={examples} />
    </>
  );
}
