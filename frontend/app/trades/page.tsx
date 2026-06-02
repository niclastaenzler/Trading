"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";

export default function TradesPage() {
  const router = useRouter();
  const [trades, setTrades] = useState<any[]>([]);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api.trades().then(setTrades);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <h2>Handelshistorie</h2>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Symbol</th><th>Seite</th><th>Menge</th><th>Einstieg</th><th>Ausstieg</th>
              <th>PnL</th><th>Konf.</th><th>Modus</th><th>Status</th><th>Eröffnet</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 && (
              <tr><td colSpan={10} style={{ color: "var(--muted)" }}>Noch keine Trades.</td></tr>
            )}
            {trades.map((t) => (
              <tr key={t.id}>
                <td>{t.symbol}</td>
                <td>{t.side}</td>
                <td>{t.quantity}</td>
                <td>{t.entry_price}</td>
                <td>{t.exit_price ?? "—"}</td>
                <td className={t.pnl >= 0 ? "pos" : "neg"}>{t.pnl?.toFixed?.(2) ?? "—"}</td>
                <td>{t.confidence ? (t.confidence * 100).toFixed(0) + "%" : "—"}</td>
                <td>{t.mode}</td>
                <td><span className={`pill ${t.status === "OPEN" ? "on" : "off"}`}>{t.status === "OPEN" ? "OFFEN" : "GESCHLOSSEN"}</span></td>
                <td>{new Date(t.opened_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
