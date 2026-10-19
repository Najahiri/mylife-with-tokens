import { useState } from "react";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Eye, EyeOff, Loader2, Pencil, Trash2 } from "lucide-react";
import { api } from "@/api/client";
import type { Deck, Item } from "@/api/types";
import { ExportMenu, type ExportFormat } from "@/components/ExportMenu";
import { ItemCard } from "@/components/ItemCard";
import { SlideViewer } from "@/components/SlideViewer";
import { ErrorNote } from "@/components/Step";
import { TitleSlideEditor } from "@/components/TitleSlideEditor";
import { useDebounced } from "@/lib/useDebounced";
import { cn } from "@/lib/utils";

/** A small button on a slide preview: hidden until the slide is hovered, unless `visible`. */
function SlideAction({ onClick, disabled, title, visible, primary, children }: {
  onClick: () => void; disabled?: boolean; title: string; visible?: boolean; primary?: boolean; children: ReactNode;
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} title={title} aria-label={title}
            className={cn("flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold text-white transition-all duration-200",
                          primary ? "bg-primary hover:brightness-110" : "bg-black/70 hover:bg-primary disabled:hover:bg-black/70",
                          visible ? "opacity-100" : "opacity-0 group-hover:opacity-100 focus-visible:opacity-100")}>
      {children}
    </button>
  );
}

/** Where a hidden extra slide would be: a thin line to bring it back. */
function HiddenSlide({ label, onShow }: { label: string; onShow: () => void }) {
  return (
    <button type="button" onClick={onShow}
            className="animate-fade flex items-center justify-center gap-1.5 rounded-xl border border-dashed border-secondary/25 py-2 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary">
      <Eye className="size-3.5" /> {label} hidden · show
    </button>
  );
}

/** The presentation built from the checked items: live slide preview, big view, PDF, and the evidence behind it.
 *  Every item has its own slide; deleting the slide takes the item out of the presentation. */
export function DeckPanel({ items, deck: fields, onDeck, onRemove, locked }: {
  items: Item[];
  deck: Deck;                              // presentation settings, shared with the agent
  onDeck: (change: Partial<Deck>) => void;
  onRemove: (title: string) => void;
  locked: boolean;          // the agent is working: the list must not change under it
}) {
  const [tab, setTab] = useState<"slides" | "evidence">("slides");
  const [viewing, setViewing] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);

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
    <aside className="flex h-full flex-col gap-4 lg:min-h-0">
      <h2 className="sr-only">Presentation</h2>
      <div className="flex items-end gap-4">
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

      {/* key: the tab's content fades in when switching */}
      <div key={tab} className="animate-fade flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
        {tab === "slides" && (
          <>
            {!items.length && (
              <p className="text-sm text-muted-foreground">
                Slides appear here as the agent adds checked items: a title slide, an overview, one slide per item and
                the contacts.
              </p>
            )}
            {items.length > 0 && (
              <div className={cn("flex flex-col gap-3 transition-opacity duration-300", preview.isFetching && "opacity-60")}>
                {slides.map((src, i) => {
                  const info = map[i];
                  return (
                    // keyed by what the slide shows: a new item's slide fades in, the others stay in place
                    <div key={info?.kind === "item" ? `item:${info.title}` : (info?.kind ?? i)} className="animate-in-up flex flex-col gap-3">
                      <div className="group relative">
                        <button type="button" onClick={() => setViewing(i)} aria-label={`Show slide ${i + 1} large`}
                                className="block w-full cursor-zoom-in">
                          <img src={src} alt={`Slide ${i + 1}`} className="w-full border border-secondary/15 shadow-sm transition-shadow duration-200 group-hover:shadow-md" />
                        </button>
                        <div className="absolute top-2 right-2 flex gap-1.5">
                          {info?.kind === "title" && (
                            <SlideAction onClick={() => setEditing(!editing)} visible={!fields.company || editing} primary={!fields.company}
                                         title={fields.company ? "Edit the title slide" : "Add the company name"}>
                              <Pencil className="size-3.5" /> {fields.company ? "Edit" : "Add company name"}
                            </SlideAction>
                          )}
                          {info?.kind === "item" && (
                            <SlideAction onClick={() => onRemove(info.title)} disabled={locked}
                                         title={locked ? "Wait until the agent has answered" : `Delete this slide: ${info.title}`}>
                              <Trash2 className="size-3.5" /> Delete
                            </SlideAction>
                          )}
                          {(info?.kind === "overview" || info?.kind === "contacts") && (
                            <SlideAction onClick={() => onDeck(info.kind === "overview" ? { overview: false } : { contacts_slide: false })}
                                         title="Hide this slide">
                              <EyeOff className="size-3.5" /> Hide
                            </SlideAction>
                          )}
                        </div>
                      </div>
                      {info?.kind === "title" && editing && (
                        <TitleSlideEditor deck={fields} defaults={defaults.data} onDeck={onDeck} onDone={() => setEditing(false)} />
                      )}
                      {info?.kind === "title" && !fields.overview && (
                        <HiddenSlide label="Overview slide" onShow={() => onDeck({ overview: true })} />
                      )}
                    </div>
                  );
                })}
                {preview.data && !fields.contacts_slide && items.some((it) => it.contacts.length > 0) && (
                  <HiddenSlide label="Contacts slide" onShow={() => onDeck({ contacts_slide: true })} />
                )}
                {!preview.data && <Loader2 className="size-5 animate-spin text-muted-foreground" />}
              </div>
            )}
          </>
        )}
        {tab === "evidence" && (
          <>
            {!items.length && <p className="text-sm text-muted-foreground">Checked items with their quotes and sources.</p>}
            {items.map((it) => (
              <div key={it.title} className="animate-in-up"><ItemCard item={it} hitOf={() => undefined} /></div>
            ))}
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
