"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      if (isRegister) {
        await api.register(email, password, inviteCode);
      }
      await api.login(email, password);
      router.push("/");
    } catch (err: any) {
      setError(err.message || "Failed");
    }
  }

  return (
    <div className="auth">
      <h2>{isRegister ? "Konto erstellen" : "Anmelden"}</h2>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>
        Das erste erstellte Konto wird zum alleinigen <b>Owner</b>.
      </p>
      {error && <div className="banner">{error}</div>}
      <form onSubmit={submit}>
        <label>E-Mail</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
        <label>Passwort</label>
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          type="password"
          required
        />
        {isRegister && (
          <>
            <label>Einladungscode</label>
            <input
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              type="text"
              placeholder="nur nötig, wenn die Instanz geschützt ist"
            />
          </>
        )}
        <button style={{ marginTop: 16, width: "100%" }} type="submit">
          {isRegister ? "Registrieren" : "Anmelden"}
        </button>
      </form>
      <p style={{ marginTop: 12 }}>
        <a onClick={() => setIsRegister(!isRegister)} style={{ cursor: "pointer" }}>
          {isRegister ? "Schon ein Konto? Anmelden" : "Noch kein Konto? Registrieren"}
        </a>
      </p>
    </div>
  );
}
