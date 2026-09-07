"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/analyze", label: "Analyze" },
  { href: "/examples", label: "Examples" },
  { href: "/resumes", label: "Résumés" },
  { href: "/profile", label: "Profile" },
  { href: "/equity", label: "Equity" },
];

/** `modeBadge` is rendered on the server and passed in, so the nav itself can
 *  stay a client component without making the whole tree client-side. */
export function NavBar({ modeBadge }: { modeBadge?: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Link href="/" className="brand">
          Job Intelligence Agent
          <span>human-in-the-loop</span>
        </Link>
        {modeBadge}
        <nav className="nav">
          {LINKS.map((link) => {
            const active =
              link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            return (
              <Link key={link.href} href={link.href} className={active ? "active" : undefined}>
                {link.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
