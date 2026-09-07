import type { Metadata } from "next";
import "./globals.css";
import { NavBar } from "@/components/NavBar";

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
        <NavBar />
        <main className="shell">{children}</main>
      </body>
    </html>
  );
}
