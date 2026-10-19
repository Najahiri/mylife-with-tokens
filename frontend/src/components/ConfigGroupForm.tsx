import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCcw } from "lucide-react";
import { api } from "@/api/client";
import type { ConfigField, ConfigGroup } from "@/api/types";
import { SettingsCard, SettingsField, settingsInput } from "@/components/SettingsCard";
import { ErrorNote } from "@/components/Step";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";

function show(v: unknown) {
  return Array.isArray(v) ? v.join(", ") : String(v);
}

/** One parameter group, rendered from the backend schema (rag_model/config.py). Save and reset appear only when
 *  there is something to save or reset. */
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
    if (f.type === "bool")
      return <div className="flex h-10 items-center"><Switch checked={Boolean(v)} onChange={set} label={v ? "On" : "Off"} showLabel /></div>;
    if (f.type === "select")
      return (
        <select value={String(v)} onChange={(e) => set(e.target.value)} className={settingsInput}>
          {f.options?.map((o) => <option key={o} value={o}>{f.option_labels?.[o] ?? o}</option>)}
        </select>
      );
    return (
      <input type="number" value={String(v)} min={f.min} max={f.max} step={f.step ?? 1} className={settingsInput}
             onChange={(e) => set(e.target.value === "" ? "" : Number(e.target.value))} />
    );
  };

  const footer = (dirty || changed || save.isSuccess || save.error || reset.error) ? (
    <div className="animate-fade flex flex-wrap items-center gap-2 border-t border-secondary/10 pt-5">
      {dirty && (
        <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending && <Loader2 className="animate-spin" />} Save changes
        </Button>
      )}
      {changed && !dirty && (
        <Button size="sm" variant="ghost" onClick={() => reset.mutate()} disabled={reset.isPending}>
          <RotateCcw /> Reset to defaults
        </Button>
      )}
      {save.isSuccess && !dirty && <span className="text-xs text-muted-foreground">Saved.</span>}
      <ErrorNote error={save.error || reset.error} />
    </div>
  ) : null;

  return (
    <SettingsCard id={group.section} title={group.title} intro={group.intro} applies={group.applies} footer={footer}>
      <div className="grid gap-x-8 gap-y-6 sm:grid-cols-2">
        {group.fields.map((f) => (
          <SettingsField key={f.key} label={f.label} hint={f.hint}
                         note={f.value !== f.default && !Array.isArray(f.value) && (
                           <span className="text-xs font-normal text-signal">
                             changed · default {f.option_labels?.[String(f.default)] ?? show(f.default)}
                           </span>
                         )}>
            {control(f)}
          </SettingsField>
        ))}
      </div>
    </SettingsCard>
  );
}
