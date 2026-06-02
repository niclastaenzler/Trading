// Thin API client for the FastAPI backend. Stores the JWT in localStorage.

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export function setToken(token: string) {
  localStorage.setItem("token", token);
}

export function clearToken() {
  localStorage.removeItem("token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") window.location.href = "/login";
  }
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  async login(email: string, password: string) {
    // OAuth2 password form expects urlencoded username/password.
    const body = new URLSearchParams({ username: email, password });
    const res = await fetch(`${API_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    if (!res.ok) throw new Error("Invalid credentials");
    const data = await res.json();
    setToken(data.access_token);
    return data;
  },
  register: (email: string, password: string, inviteCode?: string) =>
    request("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, invite_code: inviteCode || null }),
    }),
  me: () => request<any>("/api/auth/me"),
  getConfig: () => request<any>("/api/config"),
  updateConfig: (config: any) =>
    request("/api/config", { method: "PUT", body: JSON.stringify({ config }) }),
  toggleAutomation: (enabled: boolean) =>
    request("/api/config/automation", {
      method: "POST",
      body: JSON.stringify({ auto_trading_enabled: enabled }),
    }),
  killSwitch: (activate: boolean) =>
    request(`/api/config/kill-switch?activate=${activate}`, { method: "POST" }),
  performance: () => request<any>("/api/trades/performance"),
  trades: () => request<any[]>("/api/trades"),
  pending: () => request<any>("/api/trading/pending"),
  confirm: (symbol: string, approve: boolean) =>
    request("/api/trading/confirm", {
      method: "POST",
      body: JSON.stringify({ symbol, approve }),
    }),
  runCycle: () => request<any>("/api/trading/run-cycle", { method: "POST" }),
  backtest: (symbol: string, bars: number) =>
    request<any>("/api/backtest", {
      method: "POST",
      body: JSON.stringify({ symbol, bars }),
    }),
  positions: () => request<any[]>("/api/trades/positions"),
  closePosition: (symbol: string) =>
    request<any>(`/api/trading/close/${encodeURIComponent(symbol)}`, { method: "POST" }),
  brokerStatus: () => request<any>("/api/trades/broker"),
  setBroker: (creds: any) =>
    request<any>("/api/trades/broker", { method: "POST", body: JSON.stringify(creds) }),
  testBroker: () => request<any>("/api/trades/broker/test", { method: "POST" }),
  account: () => request<any>("/api/trades/account"),
  candles: (symbol: string, timeframe: string, bars = 200) =>
    request<any>(
      `/api/market/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&bars=${bars}`
    ),
  scan: () => request<any>("/api/trading/scan"),
  universe: () => request<any>("/api/market/universe"),
};

export function wsUrl(): string {
  const token = getToken();
  const base = API_URL.replace(/^http/, "ws");
  return `${base}/ws?token=${token}`;
}
