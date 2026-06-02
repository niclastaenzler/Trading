"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";

export default function SettingsPage() {
  const router = useRouter();
  const [broker, setBroker] = useState("paper");
  const [apiKey, setApiKey] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [demo, setDemo] = useState(true);
  const [status, setStatus] = useState<any>(null);
  const [test, setTest] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api.brokerStatus().then((s) => {
      setStatus(s);
      setBroker(s.broker || "paper");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save() {
    setBusy(true); setErr(""); setMsg(""); setTest(null);
    try {
      const body: any = { broker, demo };
      if (broker === "capital_com") {
        body.api_key = apiKey;
        body.identifier = identifier;
        body.password = password;
      }
      await api.setBroker(body);
      setMsg("Broker saved.");
      setStatus(await api.brokerStatus());
    } catch (e: any) {
      setErr(e.message);
    }
    setBusy(false);
  }

  async function runTest() {
    setBusy(true); setErr(""); setMsg(""); setTest(null);
    try {
      setTest(await api.testBroker());
    } catch (e: any) {
      setErr(e.message);
    }
    setBusy(false);
  }

  return (
    <div>
      <h2>Einstellungen — Broker</h2>
      {msg && (
        <div className="banner" style={{ borderColor: "var(--green)", color: "var(--green)", background: "rgba(46,204,113,.1)" }}>{msg}</div>
      )}
      {err && <div className="banner">{err}</div>}

      <div className="card">
        <h3>Aktiver Broker</h3>
        <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>
          Aktuell: <b>{status?.broker || "…"}</b>{" "}
          {status?.configured ? "✓ konfiguriert" : "— nicht konfiguriert"}
        </p>

        <label>Broker</label>
        <select value={broker} onChange={(e) => setBroker(e.target.value)}>
          <option value="paper">Paper (simuliert, sicherer Standard)</option>
          <option value="capital_com">Capital.com (Live-/Demo-API)</option>
        </select>

        {broker === "capital_com" && (
          <fieldset className="fieldset" style={{ marginTop: 16 }}>
            <legend>Capital.com Zugangsdaten</legend>
            <p style={{ color: "var(--muted)", fontSize: 13 }}>
              API-Schlüssel in Capital.com unter <i>Settings → API integrations</i> erzeugen.
              Wird verschlüsselt gespeichert. <b>Demo</b> aktiviert lassen, bis alles getestet ist.
            </p>
            <label>API-Schlüssel</label>
            <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} type="password" />
            <label>Identifier (Login-E-Mail)</label>
            <input value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
            <label>Passwort (API-Passwort)</label>
            <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" />
            <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 14 }}>
              <input type="checkbox" style={{ width: "auto" }} checked={demo} onChange={(e) => setDemo(e.target.checked)} />
              Demo-Umgebung verwenden (empfohlen)
            </label>
          </fieldset>
        )}

        <div className="row" style={{ marginTop: 16 }}>
          <button onClick={save} disabled={busy}>Broker speichern</button>
          <button className="secondary" onClick={runTest} disabled={busy}>Verbindung testen</button>
        </div>

        {test && (
          <div className="banner" style={
            test.ok
              ? { borderColor: "var(--green)", color: "var(--green)", background: "rgba(46,204,113,.1)", marginTop: 16 }
              : { marginTop: 16 }
          }>
            {test.ok
              ? `✓ Verbunden mit ${test.broker} (${test.is_paper ? "Demo/Paper" : "LIVE"}) — Kontostand ${test.balance}`
              : `✗ Verbindung fehlgeschlagen: ${test.error}`}
          </div>
        )}
      </div>

      <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 16 }}>
        Hinweis: Einen Live-Broker zu verbinden startet noch keinen Handel. Du steuerst
        alles über den Auto-Handel-Schalter, die manuelle Bestätigung und den Not-Aus.
      </p>
    </div>
  );
}
