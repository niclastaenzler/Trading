"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken, getToken } from "@/lib/api";
import { useEffect, useState } from "react";

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    setAuthed(!!getToken());
  }, [pathname]);

  if (pathname === "/login") return null;

  const links = [
    { href: "/", label: "Dashboard" },
    { href: "/config", label: "Configuration" },
    { href: "/trades", label: "Trades" },
    { href: "/backtest", label: "Backtest" },
  ];

  return (
    <nav className="nav">
      <Link href="/" className="brand">
        <span className="brand-mark">◆</span> AI&nbsp;Trading
      </Link>
      <div className="nav-links">
        {links.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={`nav-link ${pathname === l.href ? "active" : ""}`}
          >
            {l.label}
          </Link>
        ))}
      </div>
      {authed && (
        <button
          className="secondary"
          onClick={() => {
            clearToken();
            router.push("/login");
          }}
        >
          Logout
        </button>
      )}
    </nav>
  );
}
