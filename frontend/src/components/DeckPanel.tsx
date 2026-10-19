import { useState } from "react";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Loader2, PanelRightClose, Trash2 } from "lucide-react";
import { api, type DeckFields } from "@/api/client";
import type { Deck, Item } from "@/api/types";
import { ExportMenu, type ExportFormat } from "@/components/ExportMenu";
import { ItemCard } from "@/components/ItemCard";
import { Button } from "@/components/ui/button";
import { SlideViewer } from "@/components/SlideViewer";
import { ErrorNote } from "@/components/Step";
import { Checkbox } from "@/components/ui/checkbox";
import { useDebounced } from "@/lib/useDebounced";
import { cn } from "@/lib/utils";

type TextField = Exclude<keyof DeckFields, "overview" | "contacts_slide">;
const FIELDS: { key: TextField; label: string; placeholder?: string; wide?: boolean }[] = [
  { key: "company", label: "Company", placeholder: "Company name", wide: true },
  { key: "subtitle", label: "Subtitle", wide: true },
  { key: "kicker", label: "Label above the title" },
  { key: "author", label: "Speaker", placeholder: "Name" },
  { key: "organizer", label: "Organisation", placeholder: "Unit, shown below the speaker" },
];

/** The presentation built from the checked items: live slide preview, big view, PDF, and the evidence behind it.
 *  Every item has its own slide; deleting the slide takes the item out of the presentation. */
export function DeckPanel({ items, deck: fields, onDeck, onRemove, locked, onHide }: {
  items: Item[];
  deck: Deck;                              // presentation settings, shared with the agent
  onDeck: (change: Partial<Deck>) => void;
  onRemove: (title: string) => void;
  locked: boolean;          // the agent is working: the list must not change under it
  onHide: () => void;       // fold the panel away, the chat takes the full width
}) {
  const [tab, setTab] = useState<"slides" | "evidence">("slides");
  const [viewing, setViewing] = useState<number | null>(null);

  const defaults = useQuery({ queryKey: ["deck-defaults"], queryFn: api.deckDefaults });
  // re-render the slides when the items or the fields change, once typing has paused
  const request = useDebounced(JSON.stringify({ ...fields, items }), 500);
  const preview = useQuery({
    queryKey: ["slides", request], queryFn: () => api.slides(JSON.parse(request)),
    enabled: items.length > 0, placeholderData: keepPreviousData,
  });
  const exporting = useMutation({ mutationFn: (format: ExportFormat) => api.exportDeck({ ...fields, items, format }) });
  const slides = items.length ? preview.data?.slides ?? [] : [];
  const map = preview.data?.map ?? [];
  const itemOf = (i: number) => (map[i]?.kind === "item" ? map[i].title : undefined);

  const tabClass = (t: typeof tab) => cn("eyebrow border-b-2 pb-1 transition-colors",
    tab === t ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-primary");

  return (
    <aside className="flex flex-col gap-4 lg:min-h-0">
      <h2 className="sr-only">Presentation</h2>
      <div className="flex items-end gap-4">
        <Button variant="outline" size="sm" onClick={onHide} title="Fold the presentation away, the chat takes the full width">
          <PanelRightClose /> Hide
        </Button>
        <div className="ml-auto">
          <ExportMenu disabled={!items.length} pending={exporting.isPending} onExport={(f) => exporting.mutate(f)} />
        </div>
      </div>

      <div className="flex gap-5 border-b border-secondary/15">
        <button type="button" className={tabClass("slides")} onClick={() => setTab("slides")}>
          Slides {slides.length > 0 && `· ${slides.length}`}
        </button>
        <button type="button" className={tabClass("evidence")} onClick={() => setTab("evidence")}>
          Evidence {items.length > 0 && `· ${items.length}`}
        </button>
      </div>
      <ErrorNote error={preview.error || exporting.error} />

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
        {tab === "slides" && (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-6">
              {FIELDS.map((f) => (
                <label key={f.key} className={cn("flex flex-col gap-1", f.wide ? "col-span-2 sm:col-span-3" : "sm:col-span-2")}>
                  <span className="text-xs font-medium">{f.label}</span>
                  <input value={fields[f.key]} placeholder={f.placeholder ?? defaults.data?.[f.key as "subtitle" | "kicker"]}
                         onChange={(e) => onDeck({ [f.key]: e.target.value })}
                         className="min-w-0 border border-input bg-background px-2.5 py-1.5 text-sm outline-none focus:border-secondary" />
                </label>
              ))}
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
              {([["overview", "Overview slide (at a glance)"], ["contacts_slide", "Contacts slide"]] as const).map(([key, label]) => (
                <label key={key} className="flex items-center gap-2">
                  <Checkbox checked={fields[key]} onCheckedChange={(v) => onDeck({ [key]: v === true })} />
                  {label}
                </label>
              ))}
            </div>
            {!items.length && (
              <p className="text-sm text-muted-foreground">
                Slides appear here as the agent adds checked items: a title slide, an overview, one slide per item and
                the contacts.
              </p>
            )}
            {items.length > 0 && (
              <div className={cn("flex flex-col gap-3 transition-opacity", preview.isFetching && "opacity-60")}>
                {slides.map((src, i) => (
                  <div key={i} className="group relative">
                    <button type="button" onClick={() => setViewing(i)} aria-label={`Show slide ${i + 1} large`}
                            className="block w-full cursor-zoom-in">
                      <img src={src} alt={`Slide ${i + 1}`} className="w-full border border-secondary/15 shadow-sm" />
                    </button>
                    {itemOf(i) && (
                      <button type="button" onClick={() => onRemove(itemOf(i)!)} disabled={locked}
                              title={locked ? "Wait until the agent has answered" : "Delete this slide"}
                              aria-label={`Delete slide ${i + 1}: ${itemOf(i)}`}
                              className="absolute top-2 right-2 flex items-center gap-1 rounded-full bg-black/70 px-2.5 py-1 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 hover:bg-primary disabled:hover:bg-black/70">
                        <Trash2 className="size-3.5" /> Delete
                      </button>
                    )}
                  </div>
                ))}
                {!preview.data && <Loader2 className="size-5 animate-spin text-muted-foreground" />}
              </div>
            )}
          </>
        )}
        {tab === "evidence" && (
          <>
            {!items.length && <p className="text-sm text-muted-foreground">Checked items with their quotes and sources.</p>}
            {items.map((it) => <ItemCard key={it.title} item={it} hitOf={() => undefined} />)}
          </>
        )}
      </div>
      {viewing !== null && slides.length > 0 && (
        <SlideViewer request={request} preview={slides} index={Math.min(viewing, slides.length - 1)}
                     itemOf={itemOf} locked={locked} onRemove={onRemove}
                     onIndex={setViewing} onClose={() => setViewing(null)} />
      )}
    </aside>
  );
}
