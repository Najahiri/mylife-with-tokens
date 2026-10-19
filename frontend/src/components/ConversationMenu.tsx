import { useCallback, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronDown, Loader2, MessagesSquare, Plus } from "lucide-react";
import { api } from "@/api/client";
import { useDismiss } from "@/lib/useDismiss";
import { cn } from "@/lib/utils";

const ago = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

function relative(seconds: number) {
  const diff = seconds - Date.now() / 1000;
  for (const [unit, size] of [["day", 86400], ["hour", 3600], ["minute", 60]] as const) {
    if (Math.abs(diff) >= size) return ago.format(Math.round(diff / size), unit);
  }
  return "just now";
}

/** The current conversation's name; opens a menu to start a new one or go back to an earlier one. */
export function ConversationMenu({ current, title, disabled, onNew, onOpen }: {
  current: string | null;
  title: string;
  disabled: boolean;        // the agent is working: no switching
  onNew: () => void;
  onOpen: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useDismiss(open, box, useCallback(() => setOpen(false), []));
  const list = useQuery({ queryKey: ["sessions"], queryFn: api.sessions, enabled: open });
  const pick = (fn: () => void) => { setOpen(false); fn(); };

  return (
    <div ref={box} className="relative min-w-0">
      <button type="button" onClick={() => setOpen((o) => !o)} disabled={disabled} aria-haspopup="menu" aria-expanded={open}
              title={disabled ? "Wait until the agent has answered" : "Conversations"}
              className="flex max-w-full items-center gap-2 rounded-full px-3 py-1.5 text-sm font-semibold text-secondary transition-colors hover:bg-accent disabled:opacity-50 disabled:hover:bg-transparent">
        <MessagesSquare className="size-4 shrink-0 text-muted-foreground" />
        <span className="truncate">{title}</span>
        <ChevronDown className={cn("size-4 shrink-0 text-muted-foreground transition-transform duration-200", open && "rotate-180")} />
      </button>
      {open && (
        <div role="menu"
             className="animate-zoom absolute top-full left-0 z-20 mt-2 flex max-h-[min(28rem,70vh)] w-80 origin-top-left flex-col overflow-y-auto rounded-2xl border border-secondary/15 bg-background p-1.5 shadow-lg">
          <button type="button" role="menuitem" onClick={() => pick(onNew)}
                  className="flex items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-semibold text-primary hover:bg-accent focus-visible:bg-accent focus-visible:outline-none">
            <Plus className="size-4" /> New conversation
          </button>
          <span className="eyebrow mt-1 px-3 pt-2 pb-1 text-muted-foreground">Recent</span>
          {list.isLoading && <Loader2 className="mx-3 my-2 size-4 animate-spin text-muted-foreground" />}
          {list.data?.sessions.map((s) => (
            <button key={s.id} type="button" role="menuitem" onClick={() => pick(() => onOpen(s.id))}
                    className="flex items-start gap-2 rounded-xl px-3 py-2 text-left hover:bg-accent focus-visible:bg-accent focus-visible:outline-none">
              <span className="flex min-w-0 flex-1 flex-col">
                <span className={cn("truncate text-sm", s.id === current ? "font-semibold text-secondary" : "text-foreground")}>{s.title}</span>
                <span className="text-xs text-muted-foreground">
                  {s.items} {s.items === 1 ? "item" : "items"} · {relative(s.updated)}
                </span>
              </span>
              {s.id === current && <Check className="mt-0.5 size-4 shrink-0 text-secondary" />}
            </button>
          ))}
          {list.data && !list.data.sessions.length && (
            <span className="px-3 py-2 text-sm text-muted-foreground">No earlier conversations yet.</span>
          )}
        </div>
      )}
    </div>
  );
}
