import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCcw } from "lucide-react";
import { api } from "@/api/client";
import type { ConfigField, ConfigGroup } from "@/api/types";
import { ErrorNote } from "@/components/Step";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const input = "h-9 w-full border border-input bg-background px-2 text-sm tabular-nums outline-none focus:border-secondary";

function show(v: unknown) {
  return Array.isArray(v) ? v.join(", ") : String(v);
}

/** One parameter group of the pipeline, rendered from the backend schema (rag_model/config.py). */
export function ConfigGroupForm({ group }: { group: ConfigGroup }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Record<string, unknown>>(
    () => Object.fromEntries(group.fields.map((f) => [f.key, f.value])),
  );
  const done = () => {
    qc.invalidateQueries({ queryKey: ["config"] });
    qc.invalidateQueries({ queryKey: ["settings"] });
  };
  const save = useMutation({ mutationFn: () => api.saveConfig({ [group.section]: draft }), onSuccess: done });
  const reset = useMutation({ mutationFn: () => api.resetConfig(group.section), onSuccess: done });
  const dirty = group.fields.some((f) => draft[f.key] !== f.value);
  const changed = group.fields.some((f) => f.value !== f.default && !Array.isArray(f.value));

  const control = (f: ConfigField) => {
    const v = draft[f.key];
    const set = (x: unknown) => setDraft({ ...draft, [f.key]: x });
    if (!group.editable) return <p className="h-9 py-2 text-sm">{show(v)}</p>;
    if (f.type === "bool")
      return (
        <label className="flex h-9 items-center gap-2 text-sm">
          <input type="checkbox" checked={Boolean(v)} onChange={(e) => set(e.target.checked)} /> {v ? "on" : "off"}
        </label>
      );
    if (f.type === "select")
      return (
        <select value={String(v)} onChange={(e) => set(e.target.value)} className={input}>
          {f.options?.map((o) => <option key={o} value={o}>{f.option_labels?.[o] ?? o}</option>)}
        </select>
      );
    return (
      <input type="number" value={String(v)} min={f.min} max={f.max} step={f.step ?? 1} className={input}
             onChange={(e) => set(e.target.value === "" ? "" : Number(e.target.value))} />
    );
  };

  return (
    <section className="flex flex-col gap-4 bg-cream p-6">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-2xl leading-none font-bold">{group.title}</h2>
        <span className="text-xs text-muted-foreground">applies {group.applies}</span>
        {!group.editable && <span className="text-xs text-muted-foreground">· read only</span>}
      </div>
      <div className="grid gap-x-6 gap-y-5 sm:grid-cols-2">
        {group.fields.map((f) => {
          const isChanged = group.editable && f.value !== f.default && !Array.isArray(f.value);
          return (
            <div key={f.key} className="flex flex-col gap-1">
              <span className="flex items-baseline gap-2 text-xs font-medium">
                {f.label}
                {isChanged && (
                  <span className="font-normal text-signal">
                    changed · default {f.option_labels?.[String(f.default)] ?? show(f.default)}
                  </span>
                )}
              </span>
              {control(f)}
              <span className="text-[11px] leading-snug text-muted-foreground">{f.hint}</span>
            </div>
          );
        })}
      </div>
      {group.editable && (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
            {save.isPending && <Loader2 className="animate-spin" />} Save
          </Button>
          <Button size="sm" variant="ghost" onClick={() => reset.mutate()} disabled={!changed || reset.isPending}
                  className={cn(!changed && "invisible")}>
            <RotateCcw /> Reset to defaults
          </Button>
          {save.isSuccess && !dirty && <span className="text-xs text-muted-foreground">Saved.</span>}
        </div>
      )}
      <ErrorNote error={save.error || reset.error} />
    </section>
  );
}
