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

  return (
    <nav className="nav">
      <span className="brand">⚙️ AI Trading</span>
      <Link href="/">Dashboard</Link>
      <Link href="/config">Configuration</Link>
      <Link href="/trades">Trades</Link>
      <Link href="/backtest">Backtest</Link>
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
