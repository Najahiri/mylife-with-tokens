import type {
  AgentEvent, AgentSession, ConfigGroup, Deck, SessionSummary, Health, Item, LlmSettings, SearchOptions, Source, TestResult,
} from "./types";

export class ApiError extends Error {}

async function call<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method: init?.method ?? (init?.body ? "POST" : "GET"),
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
      body: init?.body ? JSON.stringify(init.body) : undefined,
    });
  } catch {
    throw new ApiError("Backend not reachable. Is `uvicorn api.main:app` running?");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    throw new ApiError(typeof detail === "string" ? detail : `Error ${res.status}`);
  }
  return data as T;
}

/** POST a chat message and call onEvent for every server-sent event until the agent has answered. */
async function streamMessage(id: string, text: string, onEvent: (e: AgentEvent) => void, signal?: AbortSignal) {
  let res: Response;
  try {
    res = await fetch(`/api/agent/${id}/messages`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }), signal,
    });
  } catch {
    throw new ApiError("Backend not reachable. Is `uvicorn api.main:app` running?");
  }
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => null);
    throw new ApiError(typeof data?.detail === "string" ? data.detail : `Error ${res.status}`);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const b of blocks) if (b.startsWith("data: ")) onEvent(JSON.parse(b.slice(6)) as AgentEvent);
  }
}

export type DeckFields = Deck;
export type SlideInfo = { kind: "title" | "overview" | "contacts" } | { kind: "item"; title: string };

/** Download the deck as a file: "pdf", or "pptx" (every slide as a picture, its text in the notes). */
async function exportDeck(body: DeckFields & { items: Item[]; format: "pdf" | "pptx" }) {
  const res = await fetch("/api/presentation/export", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }).catch(() => { throw new ApiError("Backend not reachable. Is `uvicorn api.main:app` running?"); });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new ApiError(typeof data?.detail === "string" ? data.detail : `Error ${res.status}`);
  }
  const name = res.headers.get("Content-Disposition")?.match(/filename="(.+)"/)?.[1] ?? `business-case.${body.format}`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await res.blob());
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

export const api = {
  health: () => call<Health>("/health"),
  settings: () => call<{ llm: LlmSettings; search: SearchOptions }>("/settings"),
  saveSettings: (body: Partial<LlmSettings> & { api_key?: string }) =>
    call<{ llm: LlmSettings }>("/settings", { method: "PUT", body }),
  models: () => call<{ models: string[] }>("/settings/models"),
  test: () => call<{ results: TestResult[] }>("/settings/test", { method: "POST" }),
  sources: () => call<{ sources: Source[] }>("/sources"),
  saveSources: (sources: Source[]) => call<{ sources: Source[] }>("/sources", { method: "PUT", body: { sources } }),
  config: () => call<{ groups: ConfigGroup[] }>("/config"),
  saveConfig: (changes: Record<string, Record<string, unknown>>) =>
    call<{ groups: ConfigGroup[] }>("/config", { method: "PUT", body: changes }),
  resetConfig: (section: string) =>
    call<{ groups: ConfigGroup[] }>(`/config/reset?section=${encodeURIComponent(section)}`, { method: "POST" }),

  sessions: () => call<{ sessions: SessionSummary[] }>("/agent"),
  newChat: (deck: Deck) => call<AgentSession>("/agent", { body: deck }),
  saveDeck: (id: string, deck: Deck) => call<{ deck: Deck }>(`/agent/${id}/deck`, { method: "PUT", body: deck }),
  chat: (id: string) => call<AgentSession>(`/agent/${id}`),
  sendMessage: streamMessage,
  slides: (body: DeckFields & { items: Item[]; ppi?: number }) =>
    call<{ slides: string[]; map: SlideInfo[] }>("/presentation/preview", { body }),
  deckDefaults: () => call<{ subtitle: string; kicker: string }>("/presentation/defaults"),
  removeItems: (id: string, titles: string[]) => call<AgentSession>(`/agent/${id}/remove`, { body: { titles } }),
  exportDeck,
};
