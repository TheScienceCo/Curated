import { EquityCalculator } from "@/components/EquityCalculator";

export const metadata = { title: "Equity | Job Intelligence Agent" };

export default function EquityPage() {
  return (
    <>
      <div className="page-header">
        <h1>Equity calculator</h1>
        <p>
          Dilution-adjusted scenarios for an offer&apos;s equity component. Every figure is a
          hypothetical illustration — the most common outcome for early-stage equity is zero.
        </p>
      </div>
      <EquityCalculator />
    </>
  );
}
