"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      if (isRegister) {
        await api.register(email, password);
      }
      await api.login(email, password);
      router.push("/");
    } catch (err: any) {
      setError(err.message || "Failed");
    }
  }

  return (
    <div className="auth">
      <h2>{isRegister ? "Create account" : "Sign in"}</h2>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>
        The first account created becomes the single <b>owner</b>.
      </p>
      {error && <div className="banner">{error}</div>}
      <form onSubmit={submit}>
        <label>Email</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
        <label>Password</label>
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          type="password"
          required
        />
        <button style={{ marginTop: 16, width: "100%" }} type="submit">
          {isRegister ? "Register" : "Login"}
        </button>
      </form>
      <p style={{ marginTop: 12 }}>
        <a onClick={() => setIsRegister(!isRegister)} style={{ cursor: "pointer" }}>
          {isRegister ? "Have an account? Sign in" : "Need an account? Register"}
        </a>
      </p>
    </div>
  );
}
