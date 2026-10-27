import type {
  Draft,
  SessionState,
  CollectionRun,
  Health,
  Participant,
  ScanResponse,
  TallyResponse,
  UploadResponse,
} from "./types";

/**
 * Where the API is.
 *
 * Default: same host as this page, port 8000. That is what makes opening
 * http://192.168.0.14:5173 on the phone work without configuring anything --
 * the API is on the same laptop, and the phone already knows its address
 * because it just typed it. `VITE_API_URL` overrides for anything unusual.
 */
export const API_BASE: string =
  import.meta.env.VITE_API_URL ?? `${window.location.protocol}//${window.location.hostname}:8000`;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api${path}`, init);
  } catch {
    throw new ApiError(
      `A API não respondeu em ${API_BASE}. ` +
        "Ela está rodando? (uv run python -m gymrats.serve)",
      0,
    );
  }

  if (!response.ok) {
    // FastAPI puts the readable part in `detail`; anything else is a bug and
    // the status is the most useful thing left to show.
    const body = await response.text();
    let detail = body;
    try {
      detail = (JSON.parse(body) as { detail?: string }).detail ?? body;
    } catch {
      /* not JSON; keep the raw body */
    }
    throw new ApiError(detail || `Erro ${response.status}`, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export const api = {
  session: () => request<SessionState>("/gymrats/session"),
  requestCode: (email: string) => request<{ code_pending: boolean }>("/gymrats/session/code", json({ email })),
  verifyCode: (code: string) => request<SessionState>("/gymrats/session/verify", json({ code })),
  disconnect: () => request<SessionState>("/gymrats/session", { method: "DELETE" }),
  runs: () => request<{ runs: CollectionRun[] }>("/gymrats/runs").then(body => body.runs),
  collect: (month: string, provisional = false) => request<CollectionRun>("/gymrats/runs", json({ month, provisional })),
  loadRun: (id: string) => request<CollectionRun>(`/gymrats/runs/${id}`),
  loadCollection: (id: string) => request<Draft>(`/gymrats/runs/${id}/draft`),
  bonus: (name: string, calorie_bonus: boolean) =>
    request<{ participants: Participant[] }>(`/participants/${encodeURIComponent(name)}`, {
      ...json({ calorie_bonus }), method: "PATCH",
    }).then(body => body.participants),
  health: () => request<Health>("/health"),

  participants: () =>
    request<{ participants: Participant[] }>("/participants").then(
      (body) => body.participants,
    ),

  createParticipant: (person: Partial<Participant> & { name: string }) =>
    request<{ participants: Participant[] }>("/participants", json(person)).then(
      (body) => body.participants,
    ),

  addAlias: (name: string, aliases: string[]) =>
    request<{ participants: Participant[] }>(`/participants/${encodeURIComponent(name)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ aliases }),
    }).then((body) => body.participants),

  upload: (files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    return request<UploadResponse>("/ingest/upload", { method: "POST", body: form });
  },

  scan: () => request<ScanResponse>("/ingest/scan", { method: "POST" }),

  imageUrl: (batch: string, item: string) =>
    `${API_BASE}/api/ingest/${encodeURIComponent(batch)}/items/${encodeURIComponent(item)}/image`,

  read: (batch: string, month: string) =>
    request<Draft>(
      `/ocr/${encodeURIComponent(batch)}?month=${encodeURIComponent(month)}`,
      { method: "POST" },
    ),

  loadDraft: (batch: string) => request<Draft>(`/ocr/${encodeURIComponent(batch)}/draft`),

  saveDraft: (batch: string, draft: Draft) =>
    request<Draft>(draft.run ? `/gymrats/runs/${draft.run}/draft` : `/ocr/${encodeURIComponent(batch)}/draft`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
    }),

  preview: (month: string, draft: Draft) =>
    request<TallyResponse>(draft.run ? `/gymrats/runs/${draft.run}/preview` : "/tally/preview",
      json(draft.run ? { revision: draft.revision } : { month, draft })),

  commit: (month: string, draft: Draft, batch: string | null, preview?: TallyResponse, replace = false) =>
    request<TallyResponse>(draft.run ? `/gymrats/runs/${draft.run}/commit` : "/tally/commit",
      json(draft.run ? { revision: preview?.revision, preview_token: preview?.preview_token, replace } : { month, draft, batch })),

  csvUrl: (month: string) => `${API_BASE}/api/export/${month}.csv`,
};
