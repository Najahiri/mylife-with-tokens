import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import {
  BookOpen, ChevronRight, ChevronsLeft, ListPlus, ListX, Loader2, Pencil, Presentation, Repeat, Search, Send, Sparkles, Square, Trash2, Undo2,
} from "lucide-react";
import { api } from "@/api/client";
import type { AgentEvent, Deck, Item } from "@/api/types";
import { ConversationMenu } from "@/components/ConversationMenu";
import { DeckPanel } from "@/components/DeckPanel";
import { SideDrawer } from "@/components/SideDrawer";
import { ErrorNote } from "@/components/Step";
import { Button } from "@/components/ui/button";
import { useElapsed } from "@/lib/useElapsed";
import { cn } from "@/lib/utils";

const STORE = "raglette-chat";
const DECK_STORE = "raglette-deck";   // speaker and organisation carry over to the next conversation
const NEW_DECK: Deck = { company: "", subtitle: "", kicker: "", author: "", organizer: "", overview: true, contacts_slide: true };

function draftDeck(): Deck {
  try {
    return { ...NEW_DECK, ...JSON.parse(localStorage.getItem(DECK_STORE) ?? "{}") };
  } catch {
    return NEW_DECK;
  }
}
type PageInfo = { n: number; title: string; website: string; url: string; similarity?: number };
type ToolCall = Extract<AgentEvent, { type: "tool_call" }>;
type ToolResult = Extract<AgentEvent, { type: "tool_result" }>;

function remember(id: string | null) {
  try {
    if (id) sessionStorage.setItem(STORE, id);
    else sessionStorage.removeItem(STORE);
  } catch { /* private mode: the conversation is just not restored */ }
}

/** Chat with the agent: Apertus searches, reads and composes; every step is shown and can be expanded. */
export function ChatPage() {
  const [sid, setSid] = useState<string | null>(() => {
    try { return sessionStorage.getItem(STORE); } catch { return null; }
  });
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [deck, setDeck] = useState<Deck>(draftDeck);
  // the presentation slides in by itself once the first items arrive; the slides button folds it away or back
  const [panelOpen, setPanelOpen] = useState(false);
  const hadItems = useRef(false);
  function showItems(next: Item[]) {
    setItems(next);
    if (next.length && !hadItems.current) setPanelOpen(true);
    hadItems.current = next.length > 0;
  }
  const saveTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [draft, setDraft] = useState("");
  const [running, setRunning] = useState(false);
  const [startedAt, setStartedAt] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const elapsed = useElapsed(running, startedAt);
  const restored = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);

  // restore the conversation after a reload or a visit to another page (saved in the backend)
  useEffect(() => {
    if (restored.current || !sid) return;
    restored.current = true;
    api.chat(sid)
      .then((s) => { setEvents(s.events); showItems(s.items); setDeck(s.deck); })
      .catch(() => { remember(null); setSid(null); });
  }, [sid]);

  useEffect(() => { bottom.current?.scrollIntoView({ block: "nearest" }); }, [events.length]);

  async function send() {
    const text = draft.trim();
    if (!text || running) return;
    setDraft("");
    setError(null);
    setRunning(true);
    setStartedAt(Date.now());
    try {
      let id = sid;
      if (!id) {
        id = (await api.newChat(deck)).id;
        restored.current = true;
        remember(id);
        setSid(id);
      }
      await api.sendMessage(id, text, (e) => {
        if (e.type === "items") showItems(e.items);
        else if (e.type === "deck") setDeck(e.deck);
        else setEvents((prev) => [...prev, e]);
        if (e.type === "error") setError(new Error(e.message));
      });
    } catch (e) {
      setError(e);
    } finally {
      setRunning(false);
    }
  }

  async function removeItem(title: string) {
    if (!sid) return;
    setError(null);
    try {
      const s = await api.removeItems(sid, [title]);
      showItems(s.items);
      setEvents(s.events);
    } catch (e) {
      setError(e);
    }
  }

  /** A change in the presentation panel: shown at once, saved with the conversation shortly after typing pauses. */
  function changeDeck(change: Partial<Deck>) {
    const next = { ...deck, ...change };
    setDeck(next);
    try {
      localStorage.setItem(DECK_STORE, JSON.stringify({ author: next.author, organizer: next.organizer }));
    } catch { /* not kept */ }
    clearTimeout(saveTimer.current);
    if (sid) saveTimer.current = setTimeout(() => { api.saveDeck(sid, next).catch(setError); }, 400);
  }

  function stop() {
    if (sid) api.stopChat(sid).catch(setError);
  }

  /** Switch to a saved conversation: its steps, slides and settings; the presentation is open if it has slides. */
  async function openConversation(id: string) {
    if (running || id === sid) return;
    setError(null);
    try {
      const s = await api.chat(id);
      remember(id);
      restored.current = true;
      setSid(id);
      setEvents(s.events);
      hadItems.current = false;
      setPanelOpen(false);
      showItems(s.items);
      setDeck(s.deck);
    } catch (e) {
      setError(e);
    }
  }

  function reset() {
    remember(null);
    setSid(null);
    setEvents([]);
    showItems([]);
    setPanelOpen(false);
    setDeck(draftDeck());
    setError(null);
  }

  // title, overview, one per item, contacts: the same rule as rag_model/presentation.py slide_map
  const slideCount = items.length
    ? 1 + (deck.overview ? 1 : 0) + items.length + (deck.contacts_slide && items.some((it) => it.contacts.length) ? 1 : 0)
    : 0;
  const results = new Map(events.filter((e): e is ToolResult => e.type === "tool_result").map((e) => [e.id, e]));

  return (
    <div className="flex flex-col gap-6 py-5 lg:h-[calc(100vh-5rem)] lg:flex-row lg:gap-0">
      {/* conversation */}
      <section className="flex min-h-[32rem] min-w-0 flex-1 flex-col gap-4 lg:min-h-0 lg:pr-4">
        <h1 className="sr-only">Chat with the agent</h1>
        <div className="flex h-12 shrink-0 items-end gap-2 border-b border-secondary/15 pb-2">
          <ConversationMenu current={sid} disabled={running} onNew={reset} onOpen={openConversation}
                            onDeleted={(id) => { if (id === sid) reset(); }}
                            title={deck.company || events.find((e) => e.type === "user")?.text || "New conversation"} />
          {/* arrows point where the slides would move: left to slide in, right to slide away */}
          <Button variant="outline" size="icon-sm" className="ml-auto shrink-0" onClick={() => setPanelOpen(!panelOpen)} aria-expanded={panelOpen}
                  title={panelOpen ? "Slide the presentation away" : `Show the presentation${slideCount ? ` (${slideCount} slides)` : ""}`}
                  aria-label={panelOpen ? "Slide the presentation away" : "Show the presentation"}>
            <ChevronsLeft className={cn("transition-transform duration-300", panelOpen && "rotate-180")} />
          </Button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
          {!events.length && (
            // welcome: centred in the empty chat, gone with the first message
            <div className="animate-in-up m-auto flex max-w-xl flex-col gap-5 px-2 py-10 text-center">
              <h2 className="text-[clamp(2rem,3.4vw,2.9rem)] leading-[1.05] font-bold tracking-[-0.02em] text-balance text-secondary">
                Which company are you pitching to?
              </h2>
              <p className="text-base leading-relaxed text-pretty text-foreground/80">
                Describe what it does, in a few words or with lines from its own pitch. RAGlette reads the websites of
                Bern's research institutions and builds a slide for every partner that fits, each one backed by a quote
                from its source.
              </p>
              <p className="text-sm leading-relaxed text-balance text-muted-foreground">
                Then shape the deck right here: <em>“focus on research groups”</em>,{" "}
                <em>“find more on rehabilitation”</em>, <em>“shorten the texts”</em>.
              </p>
            </div>
          )}
          {events.map((e, i) => {
            if (e.type === "user") return <UserBubble key={i} text={e.text} />;
            if (e.type === "assistant")
              return e.final ? <AssistantText key={i} text={e.text} />
                : <StepRow key={i} icon={<Sparkles />} label="Plan" details={<p className="whitespace-pre-wrap">{e.text}</p>} />;
            if (e.type === "tool_call") return <ToolStep key={i} call={e} result={results.get(e.id)} />;
            if (e.type === "done") return <p key={i} className="text-[11px] text-muted-foreground">answered in {Math.round(e.took_s)} s</p>;
            if (e.type === "error") return <ErrorNote key={i} error={new Error(e.message)} />;
            if (e.type === "note") return <StepRow key={i} icon={<Trash2 />} label={e.text} />;
            if (e.type === "stopped") return <StepRow key={i} icon={<Square />} label="Stopped" meta="what was added so far stays" />;
            return null;
          })}
          {running && (
            <p className="animate-fade flex items-center gap-2 text-sm text-muted-foreground tabular-nums">
              <Loader2 className="size-4 animate-spin" /> Apertus is working … {elapsed}
            </p>
          )}
          <div ref={bottom} />
        </div>

        <ErrorNote error={error} />
        <Composer value={draft} onChange={setDraft} onSend={send} onStop={stop} running={running}
                  placeholder={events.length ? "Ask for changes or more partners …" : "Describe the company, e.g. wearable glucose sensors for diabetes care"} />
      </section>

      <SideDrawer open={panelOpen}>
        <DeckPanel items={items} deck={deck} onDeck={changeDeck} onRemove={removeItem} locked={running} />
      </SideDrawer>
    </div>
  );
}

/** One line by default, grows with the text up to a few lines; Enter sends, Shift+Enter makes a new line. */
function Composer({ value, onChange, onSend, onStop, running, placeholder }: {
  value: string; onChange: (v: string) => void; onSend: () => void; onStop: () => void; running: boolean; placeholder: string;
}) {
  const field = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const el = field.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);
  return (
    <form className="flex items-end gap-2 rounded-[1.6rem] border border-secondary/15 bg-cream p-1.5 pl-5 transition-colors duration-200 focus-within:border-secondary/40"
          onSubmit={(e) => { e.preventDefault(); onSend(); }}>
      <textarea ref={field} value={value} onChange={(e) => onChange(e.target.value)} rows={1}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } }}
                placeholder={placeholder} aria-label="Message to the agent"
                className="max-h-[200px] min-w-0 flex-1 resize-none self-center bg-transparent py-2 text-sm leading-6 outline-none" />
      {/* while the agent works the button stops it */}
      {running ? (
        <Button type="button" size="icon" onClick={onStop} aria-label="Stop" title="Stop the agent">
          <Square className="fill-current" />
        </Button>
      ) : (
        <Button type="submit" size="icon" disabled={!value.trim()} aria-label="Send" title="Send (Enter)">
          <Send />
        </Button>
      )}
    </form>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <p className="animate-in-up max-w-[min(85%,48rem)] self-end rounded-3xl rounded-br-lg bg-primary px-5 py-3 text-sm leading-relaxed whitespace-pre-wrap text-primary-foreground">
      {text}
    </p>
  );
}

function AssistantText({ text }: { text: string }) {
  if (!text) return null;
  return <div className="animate-in-up max-w-[min(92%,56rem)] rounded-3xl rounded-tl-lg bg-cream px-5 py-3.5"><Rich text={text} /></div>;
}

/** A collapsed agent step; the details open on click. */
function StepRow({ icon, label, meta, details, pending }: {
  icon: ReactNode; label: string; meta?: ReactNode; details?: ReactNode; pending?: boolean;
}) {
  const head = (
    <span className="flex items-center gap-2 text-[13px] text-secondary [&_svg]:size-3.5">
      {pending ? <Loader2 className="animate-spin" /> : icon}
      <span className="font-semibold">{label}</span>
      {meta && <span className="text-muted-foreground">{meta}</span>}
    </span>
  );
  if (!details) return <div className="animate-in-up py-0.5">{head}</div>;
  return (
    <details className="group animate-in-up py-0.5">
      <summary className="flex cursor-pointer list-none items-center gap-1 [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-3.5 text-muted-foreground transition-transform duration-200 group-open:rotate-90" />
        {head}
      </summary>
      <div className="mt-2 ml-5 border-l border-secondary/20 pl-3 text-xs leading-relaxed text-muted-foreground">{details}</div>
    </details>
  );
}

function PageLinks({ pages }: { pages: PageInfo[] }) {
  return (
    <ul className="flex flex-col gap-1">
      {pages.map((p) => (
        <li key={p.n} className="truncate">
          <span className="font-mono">[{p.n}]</span>{" "}
          <a href={p.url} target="_blank" rel="noreferrer" className="hover:text-primary">{p.title || p.url}</a>
          <span> · {p.website}</span>
        </li>
      ))}
    </ul>
  );
}

function ToolStep({ call, result }: { call: ToolCall; result?: ToolResult }) {
  const args = call.arguments;
  const info = result?.info ?? {};
  const pages = (info.pages as PageInfo[] | undefined) ?? [];
  if (call.repeated) return <StepRow icon={<Repeat />} label="Repeated call skipped" meta={call.name} />;
  if (result?.error) return <StepRow icon={<Repeat />} label={`${call.name} failed`} details={<p>{result.text}</p>} />;

  if (call.name === "search") {
    const passages = (args.passages as string[] | undefined) ?? [];
    return (
      <StepRow icon={<Search />} label="Searched" pending={!result}
               meta={`${passages.length} passages${result ? ` → ${pages.length} pages` : ""}`}
               details={<div className="flex flex-col gap-3">
                 <ul className="flex flex-col gap-1.5">{passages.map((p, i) => <li key={i} className="italic">“{p}”</li>)}</ul>
                 {result && <PageLinks pages={pages} />}
               </div>} />
    );
  }
  if (call.name === "read_pages") {
    const asked = (args.pages as number[] | undefined) ?? [];
    return <StepRow icon={<BookOpen />} label="Read pages" pending={!result}
                    meta={result ? `${pages.length} full pages` : `${asked.length} pages`}
                    details={result && pages.length ? <PageLinks pages={pages} /> : undefined} />;
  }
  if (call.name === "add_items") {
    const added = Number(info.added ?? 0), rejected = Number(info.rejected ?? 0);
    return <StepRow icon={<ListPlus />} label="Added items" pending={!result}
                    meta={result ? `${added} added${rejected ? ` · ${rejected} rejected by the check` : ""}` : `${args.items} items to check`}
                    details={result ? <p className="whitespace-pre-wrap">{result.text}</p> : undefined} />;
  }
  if (call.name === "restore_items") {
    return <StepRow icon={<Undo2 />} label="Restored slides" pending={!result}
                    meta={((args.titles as string[] | undefined) ?? []).join(", ")}
                    details={result ? <p className="whitespace-pre-wrap">{result.text}</p> : undefined} />;
  }
  if (call.name === "edit_item") {
    return <StepRow icon={<Pencil />} label="Edited a slide" pending={!result} meta={String(args.title ?? "")}
                    details={result ? <p className="whitespace-pre-wrap">{result.text}</p> : undefined} />;
  }
  if (call.name === "update_presentation") {
    return <StepRow icon={<Presentation />} label="Changed the presentation" pending={!result}
                    details={result ? <p className="whitespace-pre-wrap">{result.text}</p> : undefined} />;
  }
  if (call.name === "remove_items") {
    return <StepRow icon={<ListX />} label="Removed items" pending={!result}
                    meta={result ? `${info.removed ?? 0} removed` : undefined}
                    details={result ? <p className="whitespace-pre-wrap">{result.text}</p> : undefined} />;
  }
  return <StepRow icon={<Sparkles />} label={call.name} pending={!result} />;
}

/** The little Markdown Apertus writes: headings, bullet and numbered lines, **bold**. */
function Rich({ text }: { text: string }) {
  const inline = (s: string) =>
    s.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
      part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong>
        : part.replace(/(^|\s)\*([^*\s][^*]*)\*/g, "$1$2"));
  return (
    <div className="flex flex-col gap-1.5 text-sm leading-relaxed">
      {text.split("\n").map((line, i) => {
        const t = line.trim();
        if (!t) return null;
        const heading = t.match(/^#{1,6}\s+(.*)/);
        if (heading) return <p key={i} className="pt-1 font-semibold text-secondary">{inline(heading[1])}</p>;
        const bullet = t.match(/^([-*•]|\d+\.)\s+(.*)/);
        if (bullet) {
          const marker = /\d/.test(bullet[1]) ? bullet[1] : "•";
          return <p key={i} className="flex gap-2 pl-1"><span className="text-primary">{marker}</span><span>{inline(bullet[2])}</span></p>;
        }
        return <p key={i}>{inline(t)}</p>;
      })}
    </div>
  );
}
