import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ExternalLink, Info, Loader2, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { api } from "@/api/client";
import type { Source } from "@/api/types";
import { SettingsField, settingsInput } from "@/components/SettingsCard";
import { ErrorNote } from "@/components/Step";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn, hostname } from "@/lib/utils";

const n = (x: number | undefined) => (x ?? 0).toLocaleString("en-US");

export function SourcesPage() {
  const sources = useQuery({ queryKey: ["sources"], queryFn: api.sources });
  if (sources.isPending) return <p className="pt-10 text-sm text-muted-foreground">Loading …</p>;
  if (sources.isError) return <div className="pt-10"><ErrorNote error={sources.error} /></div>;
  // the key remounts the editor with fresh rows after saving
  return <SourcesEditor key={JSON.stringify(sources.data.sources)} initial={sources.data.sources} />;
}

function Stat({ value, label, info }: { value: ReactNode; label: string; info?: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 rounded-3xl bg-cream px-6 py-5">
      <span className="text-3xl leading-none font-bold text-secondary tabular-nums">{value}</span>
      <span className="flex items-center gap-1.5 text-sm text-muted-foreground">{label}{info}</span>
    </div>
  );
}

function SourcesEditor({ initial }: { initial: Source[] }) {
  const qc = useQueryClient();
  const [rows, setRows] = useState<Source[]>(initial);
  const [editing, setEditing] = useState<number | null>(null);
  const [filter, setFilter] = useState("");
  const [newUrl, setNewUrl] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const save = useMutation({
    mutationFn: () => api.saveSources(rows),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sources"] }),
  });
  const dirty = JSON.stringify(rows) !== JSON.stringify(initial);
  const update = (i: number, patch: Partial<Source>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const add = () => {
    if (!newUrl.trim()) return;
    setRows([{ name: "", desc: newDesc.trim(), url: newUrl.trim(), enabled: true }, ...rows]);
    setEditing(null);
    setNewUrl("");
    setNewDesc("");
  };
  const remove = (i: number) => {
    setRows(rows.filter((_, j) => j !== i));
    setEditing(null);
  };

  const active = rows.filter((r) => r.enabled).length;
  const indexed = rows.reduce((s, r) => s + (r.indexed ?? 0), 0);
  const crawled = rows.reduce((s, r) => s + (r.crawled ?? 0), 0);
  const q = filter.trim().toLowerCase();
  const visible = rows.map((r, i) => ({ r, i }))
    .filter(({ r }) => !q || `${r.desc} ${r.url} ${r.name}`.toLowerCase().includes(q));

  return (
    <div className="animate-fade mx-auto flex w-full max-w-4xl flex-col gap-8 pt-10 pb-28">
      <div className="flex flex-col gap-2">
        <h1 className="text-5xl leading-none font-bold tracking-[-0.02em]">Sources</h1>
        <p className="text-sm text-muted-foreground">
          The websites RAGlette searches. A start URL is all a website needs; changes take effect at the next crawl and
          index rebuild.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat value={<>{active}<span className="text-lg text-muted-foreground"> / {rows.length}</span></>} label="websites active" />
        <Stat value={n(indexed)} label="pages in the index" info={
          <Tooltip>
            <TooltipTrigger asChild>
              <button type="button" className="text-secondary/60 hover:text-primary" aria-label="What in the index means">
                <Info className="size-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs text-xs leading-relaxed">
              The pages the agent can search: what is left of the crawled pages after removing menus, duplicates (the
              same text under several addresses) and pages with almost no text. Pages crawled after the last index
              rebuild are not in it yet.
            </TooltipContent>
          </Tooltip>
        } />
        <Stat value={n(crawled)} label="pages crawled" />
      </div>

      <section className="flex flex-col gap-5 rounded-3xl bg-cream p-6 sm:p-8">
        <h2 className="text-2xl leading-none font-bold">Add a website</h2>
        <form className="grid items-end gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
              onSubmit={(e) => { e.preventDefault(); add(); }}>
          <SettingsField label="Start URL">
            <input value={newUrl} onChange={(e) => setNewUrl(e.target.value)} className={settingsInput}
                   placeholder="https://www.example.ch" />
          </SettingsField>
          <SettingsField label="Label (optional)">
            <input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} className={settingsInput}
                   placeholder="e.g. sitem-insel" />
          </SettingsField>
          <Button type="submit" disabled={!newUrl.trim()}><Plus /> Add</Button>
        </form>
      </section>

      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-2xl leading-none font-bold">Websites</h2>
          <div className="relative ml-auto w-full sm:w-72">
            <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter websites"
                   className={cn(settingsInput, "rounded-full pl-10")} aria-label="Filter websites" />
          </div>
        </div>

        <ul className="flex flex-col gap-2">
          {visible.map(({ r, i }) => (
            <li key={r.name || `new-${i}`}
                className={cn("animate-in-up rounded-2xl border transition-colors duration-200",
                              editing === i ? "border-secondary/20 bg-cream" : "border-secondary/10 hover:border-secondary/25")}>
              <div className="flex items-center gap-4 px-5 py-3.5">
                <Switch checked={r.enabled} onChange={(v) => update(i, { enabled: v })} label={`Use ${r.desc || r.url}`} />
                <div className={cn("min-w-0 flex-1 transition-opacity", !r.enabled && "opacity-50")}>
                  <p className="truncate font-semibold text-secondary">{r.desc || hostname(r.url)}</p>
                  <a href={r.url} target="_blank" rel="noreferrer"
                     className="flex items-center gap-1 truncate text-xs text-muted-foreground hover:text-primary">
                    {r.url.replace(/^https?:\/\//, "").replace(/\/$/, "")}
                    <ExternalLink className="size-3 shrink-0" />
                  </a>
                </div>
                <div className={cn("hidden text-right text-xs tabular-nums sm:block", !r.enabled && "opacity-50")}>
                  {r.crawled || r.indexed ? (
                    <>
                      <p className="font-semibold text-secondary">{n(r.indexed)} in index</p>
                      <p className="text-muted-foreground">{n(r.crawled)} crawled</p>
                    </>
                  ) : (
                    <span className="rounded-full bg-accent px-2.5 py-1 font-semibold text-secondary">not crawled yet</span>
                  )}
                </div>
                <div className="flex shrink-0 gap-1">
                  <button type="button" onClick={() => setEditing(editing === i ? null : i)}
                          className="rounded-full p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-secondary"
                          aria-label={editing === i ? "Done" : "Edit"} title={editing === i ? "Done" : "Edit"}>
                    {editing === i ? <Check className="size-4" /> : <Pencil className="size-4" />}
                  </button>
                  <button type="button" onClick={() => remove(i)}
                          className="rounded-full p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-primary"
                          aria-label="Remove website" title="Remove website">
                    <Trash2 className="size-4" />
                  </button>
                </div>
              </div>

              {editing === i && (
                <div className="animate-in-up grid gap-5 border-t border-secondary/10 px-5 py-5 sm:grid-cols-2">
                  <SettingsField label="Label">
                    <input value={r.desc} onChange={(e) => update(i, { desc: e.target.value })} className={settingsInput} />
                  </SettingsField>
                  <SettingsField label="Start URL">
                    <input value={r.url} onChange={(e) => update(i, { url: e.target.value })} className={settingsInput} />
                  </SettingsField>
                  <SettingsField label="Sitemap URLs" hint="Optional, comma-separated. Otherwise detected via robots.txt.">
                    <input value={(r.sitemaps ?? []).join(", ")} className={settingsInput} placeholder="auto-detected"
                           onChange={(e) => update(i, { sitemaps: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
                  </SettingsField>
                  <SettingsField label="Max. pages per crawl" hint="Safety cap for very large websites.">
                    <input type="number" min={1} value={r.max_pages ?? ""} placeholder="5000" className={settingsInput}
                           onChange={(e) => update(i, { max_pages: e.target.value ? Number(e.target.value) : undefined })} />
                  </SettingsField>
                  <p className="font-mono text-[11px] text-muted-foreground sm:col-span-2">id: {r.name || "assigned on save"}</p>
                </div>
              )}
            </li>
          ))}
          {visible.length === 0 && (
            <li className="rounded-2xl border border-dashed border-secondary/20 px-5 py-6 text-sm text-muted-foreground">
              No website matches "{filter}".
            </li>
          )}
        </ul>
      </section>

      {/* floating save bar while there are unsaved changes */}
      {(dirty || save.error) && (
        <div className="animate-in-up fixed inset-x-0 bottom-6 z-30 flex justify-center px-4">
          <div className="flex flex-wrap items-center gap-3 rounded-full border border-secondary/15 bg-background py-2 pr-2 pl-5 shadow-xl">
            <span className="text-sm font-semibold text-secondary">Unsaved changes</span>
            <ErrorNote error={save.error} />
            <Button variant="ghost" size="sm" onClick={() => { setRows(initial); setEditing(null); }}>Discard</Button>
            <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
              {save.isPending && <Loader2 className="animate-spin" />} Save changes
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
