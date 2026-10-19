/** Mirrors the FastAPI backend (api/main.py). */

export type Mode = "direct" | "apertus";

export interface Query {
  buzzword: string;
  terms: string[];
}

export interface SearchOptions {
  top_k: number;
  top_n: number;
  max_per_site: number;
  min_similarity: number;
  weak_similarity: number;
  variant_similarity: number;
}

export interface Source {
  name: string;          // stable id, derived from the host; empty for new rows
  desc: string;
  url: string;
  sitemaps?: string[];
  max_pages?: number;
  enabled: boolean;
  crawled?: number;      // pages fetched by the crawler
  indexed?: number;      // pages in the search index
}

export interface ConfigField {
  key: string;
  label: string;
  hint: string;
  type: "int" | "float" | "bool" | "select" | "str" | "list";
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
  option_labels?: Record<string, string>;
  value: unknown;
  default: unknown;
}

export interface ConfigGroup {
  section: string;
  title: string;
  intro?: string;
  applies: string;
  editable: boolean;
  fields: ConfigField[];
}

export interface Page {
  page_id: string;
  url: string;
  title: string;
  website: string;
  source: string;
  similarity: number;
  rrf: number;
  terms: Record<string, number>;
  snippet: string;
  variants: string[];
}

export interface Contact {
  name: string;
  role?: string;
  email?: string;
  phone?: string;
}

export interface Item {
  title: string;
  category: string;
  organisation?: string;
  summary: string;
  relevance?: string;
  facts?: string[];
  evidence: string;
  sources: { url: string; title: string; website: string }[];
  contacts: Contact[];
  contacts_removed: Contact[];
  flags: string[];
  edited?: string[];      // fields changed on the user's request
  unbacked?: string[];    // what the source pages do not back since those changes
}

export interface Dropped {
  item: { title?: string; summary?: string };
  reasons: string[];
}

export interface BriefResult {
  status: "ok" | "insufficient_evidence" | "no_results";
  items: Item[];
  dropped: Dropped[];
  took_s: number;
  trace: string;
}

export interface LlmSettings {
  base_url?: string;
  model_agent?: string;
  key_set: boolean;
  key_last4: string;
}

export interface Health {
  status: string;
  pages: number;
  websites: number;
  llm_configured: boolean;
}

export interface TestResult {
  role: "agent";
  ok: boolean;
  seconds: number;
  message: string;
}

/** Presentation settings of a conversation; the user edits them in the panel, the agent with update_presentation. */
export interface Deck {
  company: string;
  subtitle: string;
  kicker: string;
  author: string;
  organizer: string;
  overview: boolean;
  contacts_slide: boolean;
}

/** One step of an agent conversation, as streamed by POST /api/agent/{id}/messages. */
export type AgentEvent =
  | { type: "user"; text: string }
  | { type: "assistant"; text: string; final: boolean }
  | { type: "tool_call"; id: string; name: string; arguments: Record<string, unknown>; repeated?: boolean }
  | { type: "tool_result"; id: string; name: string; error: boolean; info: Record<string, unknown>; text: string }
  | { type: "items"; items: Item[]; dropped: Dropped[] }
  | { type: "done"; took_s: number; trace: string }
  | { type: "note"; text: string }
  | { type: "deck"; deck: Deck }
  | { type: "error"; message: string };

export interface SessionSummary {
  id: string;
  title: string;
  updated: number;   // seconds since 1970
  items: number;
}

export interface AgentSession {
  id: string;
  events: AgentEvent[];
  pages: { page_id: string; url: string; title: string; website: string; similarity: number }[];
  read: number[];
  items: Item[];
  dropped: Dropped[];
  deck: Deck;
}
