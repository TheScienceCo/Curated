import { AnalyzeForm } from "@/components/AnalyzeForm";

export const metadata = { title: "Analyze | Job Intelligence Agent" };

export default function AnalyzePage() {
  return (
    <>
      <div className="page-header">
        <h1>Analyze an opportunity</h1>
        <p>
          Paste a recruiter message, email, LinkedIn note or full job description. The system
          extracts structured fields deterministically, scores the opportunity across seven
          dimensions, and drafts a reply <strong>for your approval</strong>. Nothing is sent.
        </p>
      </div>
      <AnalyzeForm />
    </>
  );
}
