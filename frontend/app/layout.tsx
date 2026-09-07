import type { Metadata } from "next";
import "./globals.css";
import { NavBar } from "@/components/NavBar";
import { PipelineMode } from "@/components/PipelineMode";

export const metadata: Metadata = {
  title: "Job Intelligence Agent",
  description:
    "Extracts, scores and triages job opportunities against a configurable candidate profile, with transparent reasoning and human-in-the-loop drafting.",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <NavBar modeBadge={<PipelineMode />} />
        <main className="shell">{children}</main>
      </body>
    </html>
  );
}
