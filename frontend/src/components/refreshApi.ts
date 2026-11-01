export class RequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

const endpoint = (import.meta.env.VITE_REFRESH_URL ?? "").replace(/\/$/, "");

export async function request<T>(path: string, token?: string, body?: object): Promise<T> {
  const response = await fetch(`${endpoint}${path}`, {
    method: body ? "POST" : "GET",
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
    signal: AbortSignal.timeout(20000),
  });
  const data = await response.json();
  if (!response.ok) throw new RequestError(data.error ?? "Falha ao acessar a atualização.", response.status);
  return data as T;
}

export type Run = { id: number; title?: string; status: string; conclusion: string | null; url: string; created_at: string };
