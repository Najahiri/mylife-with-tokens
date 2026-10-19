import { useCallback, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Loader2, MessagesSquare, Plus, Trash2 } from "lucide-react";
import { api } from "@/api/client";
import { relative } from "@/lib/time";
import { useDismiss } from "@/lib/useDismiss";
import { cn } from "@/lib/utils";

/** The current conversation's name; opens a menu to start a new one or go back to an earlier one. */
export function ConversationMenu({ current, title, disabled, onNew, onOpen, onDeleted }: {
  current: string | null;
  title: string;
  disabled: boolean;        // the agent is working: no switching
  onNew: () => void;
  onOpen: (id: string) => void;
  onDeleted: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);   // deleting is for good: a second click confirms
  const box = useRef<HTMLDivElement>(null);
  useDismiss(open, box, useCallback(() => { setOpen(false); setConfirming(null); }, []));
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["sessions"], queryFn: api.sessions, enabled: open });
  const remove = useMutation({
    mutationFn: api.deleteChat,
    onSuccess: (_, id) => { setConfirming(null); qc.invalidateQueries({ queryKey: ["sessions"] }); onDeleted(id); },
  });
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
            <div key={s.id} className="group flex items-center gap-1 rounded-xl transition-colors hover:bg-accent">
              <button type="button" role="menuitem" onClick={() => pick(() => onOpen(s.id))}
                      className="flex min-w-0 flex-1 items-center gap-2 rounded-xl px-3 py-2 text-left focus-visible:bg-accent focus-visible:outline-none">
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className={cn("truncate text-sm", s.id === current ? "font-semibold text-secondary" : "text-foreground")}>{s.title}</span>
                  <span className="text-xs text-muted-foreground">
                    {s.items} {s.items === 1 ? "item" : "items"} · {relative(s.updated)}
                  </span>
                </span>
              </button>
              {/* check and trash share the right edge, centred on the row */}
              {s.id === current && <Check className="size-4 shrink-0 text-secondary" aria-label="current conversation" />}
              {confirming === s.id ? (
                <button type="button" onClick={() => remove.mutate(s.id)} disabled={remove.isPending}
                        className="animate-zoom mr-1.5 flex shrink-0 items-center gap-1 rounded-full bg-primary px-2.5 py-1 text-xs font-semibold text-primary-foreground hover:brightness-110">
                  {remove.isPending ? <Loader2 className="size-3 animate-spin" /> : <Trash2 className="size-3" />} Delete?
                </button>
              ) : (
                <button type="button" onClick={() => setConfirming(s.id)} title="Delete this conversation" aria-label={`Delete conversation: ${s.title}`}
                        className="mr-1.5 shrink-0 rounded-full p-1.5 text-muted-foreground opacity-0 transition-all group-hover:opacity-100 hover:bg-background hover:text-primary focus-visible:opacity-100">
                  <Trash2 className="size-3.5" />
                </button>
              )}
            </div>
          ))}
          {remove.error && <span className="px-3 py-1 text-xs text-primary">{remove.error.message}</span>}
          {list.data && !list.data.sessions.length && (
            <span className="px-3 py-2 text-sm text-muted-foreground">No earlier conversations yet.</span>
          )}
        </div>
      )}
    </div>
  );
}
