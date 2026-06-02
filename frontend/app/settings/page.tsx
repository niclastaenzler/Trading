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
      <h2>Settings — Broker</h2>
      {msg && (
        <div className="banner" style={{ borderColor: "var(--green)", color: "var(--green)", background: "rgba(46,204,113,.1)" }}>{msg}</div>
      )}
      {err && <div className="banner">{err}</div>}

      <div className="card">
        <h3>Active broker</h3>
        <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>
          Current: <b>{status?.broker || "…"}</b>{" "}
          {status?.configured ? "✓ configured" : "— not configured"}
        </p>

        <label>Broker</label>
        <select value={broker} onChange={(e) => setBroker(e.target.value)}>
          <option value="paper">Paper (simulated, safe default)</option>
          <option value="capital_com">Capital.com (live/demo API)</option>
        </select>

        {broker === "capital_com" && (
          <fieldset className="fieldset" style={{ marginTop: 16 }}>
            <legend>Capital.com credentials</legend>
            <p style={{ color: "var(--muted)", fontSize: 13 }}>
              Generate an API key in Capital.com → <i>Settings → API integrations</i>.
              Stored encrypted. Keep <b>Demo</b> on until you have validated behaviour.
            </p>
            <label>API key</label>
            <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} type="password" />
            <label>Identifier (login email)</label>
            <input value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
            <label>Password (API password)</label>
            <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" />
            <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 14 }}>
              <input type="checkbox" style={{ width: "auto" }} checked={demo} onChange={(e) => setDemo(e.target.checked)} />
              Use Demo environment (recommended)
            </label>
          </fieldset>
        )}

        <div className="row" style={{ marginTop: 16 }}>
          <button onClick={save} disabled={busy}>Save broker</button>
          <button className="secondary" onClick={runTest} disabled={busy}>Test connection</button>
        </div>

        {test && (
          <div className="banner" style={
            test.ok
              ? { borderColor: "var(--green)", color: "var(--green)", background: "rgba(46,204,113,.1)", marginTop: 16 }
              : { marginTop: 16 }
          }>
            {test.ok
              ? `✓ Connected to ${test.broker} (${test.is_paper ? "demo/paper" : "LIVE"}) — balance ${test.balance}`
              : `✗ Connection failed: ${test.error}`}
          </div>
        )}
      </div>

      <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 16 }}>
        Note: connecting a live broker does not start trading. You still control
        everything via auto-trading toggle, manual confirmation and the kill switch.
      </p>
    </div>
  );
}
