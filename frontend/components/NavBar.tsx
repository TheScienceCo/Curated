"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/analyze", label: "Analyze" },
  { href: "/resumes", label: "Résumés" },
  { href: "/profile", label: "Profile" },
  { href: "/equity", label: "Equity" },
];

export function NavBar() {
  const pathname = usePathname();

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Link href="/" className="brand">
          Job Intelligence Agent
          <span>human-in-the-loop</span>
        </Link>
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
