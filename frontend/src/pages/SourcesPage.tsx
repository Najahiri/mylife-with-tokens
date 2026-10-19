import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ExternalLink, Info, Loader2, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { api } from "@/api/client";
import type { Source } from "@/api/types";
import { ErrorNote } from "@/components/Step";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn, hostname } from "@/lib/utils";

const input = "h-10 w-full border border-input bg-background px-3 text-sm outline-none focus:border-secondary";
// one grid for header and rows, so every column lines up
const row = "grid grid-cols-[2.5rem_minmax(0,1fr)_9rem_8rem_4.5rem] items-center gap-x-4";

export function SourcesPage() {
  const sources = useQuery({ queryKey: ["sources"], queryFn: api.sources });
  if (sources.isPending) return <p className="pt-10 text-sm text-muted-foreground">Loading …</p>;
  if (sources.isError) return <div className="pt-10"><ErrorNote error={sources.error} /></div>;
  // the key remounts the editor with fresh rows after saving
  return <SourcesEditor key={JSON.stringify(sources.data.sources)} initial={sources.data.sources} />;
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold text-secondary">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
    </label>
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
  const indexed = rows.reduce((n, r) => n + (r.indexed ?? 0), 0);
  const q = filter.trim().toLowerCase();
  const visible = rows.map((r, i) => ({ r, i }))
    .filter(({ r }) => !q || `${r.desc} ${r.url} ${r.name}`.toLowerCase().includes(q));

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 pt-10 pb-24">
      <div className="flex flex-col gap-2">
        <h1 className="text-5xl leading-none font-bold tracking-[-0.02em]">Sources</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          The websites RAGlette searches. Each website only needs a start URL, there are no per-website rules.
          New or changed websites take effect at the next crawl and index rebuild.
        </p>
      </div>

      <section className="flex flex-col gap-4 border-l-4 border-primary bg-cream p-6">
        <span className="eyebrow text-secondary">Add website</span>
        <div className="grid items-end gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
          <Field label="Start URL">
            <input value={newUrl} onChange={(e) => setNewUrl(e.target.value)} className={input}
                   placeholder="https://www.example.ch" onKeyDown={(e) => e.key === "Enter" && add()} />
          </Field>
          <Field label="Label (optional)">
            <input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} className={input}
                   placeholder="e.g. sitem-insel" onKeyDown={(e) => e.key === "Enter" && add()} />
          </Field>
          <Button onClick={add} disabled={!newUrl.trim()}><Plus /> Add</Button>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <span className="text-sm text-muted-foreground tabular-nums">
            <span className="font-semibold text-secondary">{active}</span> of {rows.length} websites active ·{" "}
            <span className="font-semibold text-secondary">{indexed.toLocaleString("en-US")}</span> pages in the index
          </span>
          <Tooltip>
            <TooltipTrigger asChild>
              <button type="button" className="-ml-4 text-secondary/60 hover:text-primary" aria-label="What crawled and in index mean">
                <Info className="size-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs text-xs leading-relaxed">
              <b>Crawled</b>: pages downloaded from the website. <b>In index</b>: the pages the agent can search, what is
              left after removing menus, duplicates (the same text under several addresses) and pages with almost no
              text. Pages crawled after the last index rebuild are not in the index yet.
            </TooltipContent>
          </Tooltip>
          <div className="relative ml-auto w-full sm:w-72">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter websites"
                   className={cn(input, "pl-9")} aria-label="Filter websites" />
          </div>
        </div>

        <div className="overflow-x-auto">
          <div className="min-w-[720px]">
            <div className={cn(row, "eyebrow border-b-2 border-secondary pb-2 text-secondary")}>
              <span>On</span>
              <span>Website</span>
              <span>Settings</span>
              <span className="text-right">Status</span>
              <span />
            </div>

            <ul className="divide-y divide-secondary/10">
              {visible.map(({ r, i }) => (
                <li key={r.name || `new-${i}`} className={cn(editing === i && "bg-cream")}>
                  <div className={cn(row, "py-3", !r.enabled && "opacity-50")}>
                    <Checkbox checked={r.enabled} onCheckedChange={(v) => update(i, { enabled: v === true })}
                              aria-label={`Use ${r.desc || r.url}`} />
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-secondary">{r.desc || hostname(r.url)}</p>
                      <a href={r.url} target="_blank" rel="noreferrer"
                         className="flex items-center gap-1 truncate text-xs text-muted-foreground hover:text-primary">
                        {r.url.replace(/^https?:\/\//, "").replace(/\/$/, "")}
                        <ExternalLink className="size-3 shrink-0" />
                      </a>
                    </div>
                    <div className="flex flex-col text-xs text-muted-foreground">
                      <span>{r.sitemaps?.length ? "sitemap set" : "sitemap auto"}</span>
                      <span className="tabular-nums">max. {(r.max_pages ?? 5000).toLocaleString("en-US")} pages</span>
                    </div>
                    <div className="text-right text-xs tabular-nums">
                      {r.crawled || r.indexed ? (
                        <>
                          <p className="font-semibold text-secondary">{(r.indexed ?? 0).toLocaleString("en-US")} in index</p>
                          <p className="text-muted-foreground">{(r.crawled ?? 0).toLocaleString("en-US")} crawled</p>
                        </>
                      ) : (
                        <span className="rounded-full bg-accent px-2 py-0.5 font-semibold text-secondary">not crawled yet</span>
                      )}
                    </div>
                    <div className="flex justify-end gap-1">
                      <button type="button" onClick={() => setEditing(editing === i ? null : i)}
                              className="rounded-full p-1.5 text-muted-foreground hover:bg-accent hover:text-secondary"
                              aria-label={editing === i ? "Done" : "Edit"}>
                        {editing === i ? <Check className="size-4" /> : <Pencil className="size-4" />}
                      </button>
                      <button type="button" onClick={() => remove(i)}
                              className="rounded-full p-1.5 text-muted-foreground hover:bg-accent hover:text-primary"
                              aria-label="Remove website">
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </div>

                  {editing === i && (
                    <div className="grid gap-4 px-4 pb-5 pl-14 sm:grid-cols-2">
                      <Field label="Label">
                        <input value={r.desc} onChange={(e) => update(i, { desc: e.target.value })} className={input} />
                      </Field>
                      <Field label="Start URL">
                        <input value={r.url} onChange={(e) => update(i, { url: e.target.value })} className={input} />
                      </Field>
                      <Field label="Sitemap URLs" hint="Optional, comma-separated. Otherwise detected via robots.txt.">
                        <input value={(r.sitemaps ?? []).join(", ")} className={input} placeholder="auto-detected"
                               onChange={(e) => update(i, {
                                 sitemaps: e.target.value.split(",").map((x) => x.trim()).filter(Boolean),
                               })} />
                      </Field>
                      <Field label="Max. pages per crawl" hint="Safety cap for very large websites.">
                        <input type="number" min={1} value={r.max_pages ?? ""} placeholder="5000" className={input}
                               onChange={(e) => update(i, { max_pages: e.target.value ? Number(e.target.value) : undefined })} />
                      </Field>
                      <p className="font-mono text-[11px] text-muted-foreground sm:col-span-2">
                        id: {r.name || "assigned on save"}
                      </p>
                    </div>
                  )}
                </li>
              ))}
              {visible.length === 0 && (
                <li className="py-6 text-sm text-muted-foreground">No website matches "{filter}".</li>
              )}
            </ul>
          </div>
        </div>
      </section>

      {(dirty || save.error) && (
        <div className="sticky bottom-0 -mx-4 flex flex-wrap items-center gap-3 border-t-2 border-primary bg-background px-4 py-3 sm:-mx-6 sm:px-6">
          <span className="text-sm font-semibold text-secondary">Unsaved changes</span>
          <ErrorNote error={save.error} />
          <div className="ml-auto flex gap-2">
            <Button variant="ghost" onClick={() => { setRows(initial); setEditing(null); }}>Discard</Button>
            <Button onClick={() => save.mutate()} disabled={save.isPending}>
              {save.isPending && <Loader2 className="animate-spin" />} Save changes
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
