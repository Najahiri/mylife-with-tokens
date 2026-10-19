import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { api } from "@/api/client";
import type { LlmSettings } from "@/api/types";
import { ConfigGroupForm } from "@/components/ConfigGroupForm";
import { SettingsCard, SettingsField, settingsInput } from "@/components/SettingsCard";
import { ErrorNote } from "@/components/Step";
import { Button } from "@/components/ui/button";

export function SettingsPage() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  if (settings.isPending || config.isPending) return <p className="pt-10 text-sm text-muted-foreground">Loading …</p>;
  if (settings.isError || config.isError)
    return <div className="pt-10"><ErrorNote error={settings.error || config.error} /></div>;

  const sections = [{ id: "api", title: "Apertus access" }, ...config.data.groups.map((g) => ({ id: g.section, title: g.title }))];

  return (
    <div className="animate-fade mx-auto w-full max-w-6xl pt-10 pb-24">
      <div className="flex flex-col gap-2">
        <h1 className="text-5xl leading-none font-bold tracking-[-0.02em]">Settings</h1>
        <p className="text-sm text-muted-foreground">Changes apply to all conversations until they are reset.</p>
      </div>
      <div className="mt-10 grid gap-10 lg:grid-cols-[13rem_minmax(0,1fr)]">
        <nav aria-label="Settings sections" className="hidden lg:block">
          <ul className="sticky top-6 flex flex-col gap-0.5">
            {sections.map((s) => (
              <li key={s.id}>
                <a href={`#${s.id}`}
                   className="block rounded-full px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-secondary">
                  {s.title}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="flex min-w-0 flex-col gap-6">
          <ApiAccess llm={settings.data.llm} />
          {config.data.groups.map((g) => (
            // the key remounts a group with fresh values after saving or resetting
            <ConfigGroupForm key={`${g.section}-${JSON.stringify(g.fields.map((f) => f.value))}`} group={g} />
          ))}
        </div>
      </div>
    </div>
  );
}

function ApiAccess({ llm }: { llm: LlmSettings }) {
  const qc = useQueryClient();
  const [baseUrl, setBaseUrl] = useState(llm.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(llm.model_agent ?? "");

  const models = useQuery({ queryKey: ["models"], queryFn: api.models, enabled: llm.key_set });
  const save = useMutation({
    mutationFn: () => api.saveSettings({ base_url: baseUrl, api_key: apiKey || undefined, model_agent: model }),
    onSuccess: () => {
      setApiKey("");
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["health"] });
      qc.invalidateQueries({ queryKey: ["models"] });
    },
  });
  const test = useMutation({ mutationFn: api.test });
  const options = models.data?.models ?? [];
  const result = test.data?.results[0];

  return (
    <SettingsCard id="api" title="Apertus access"
                  intro="OpenAI-compatible API. The key stays in the backend and is never sent back to the browser.">
      <form className="flex flex-col gap-6" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="grid gap-x-8 gap-y-6 sm:grid-cols-2">
          <SettingsField label="API base URL">
            <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} className={settingsInput}
                   placeholder="https://gateway.keera.ch/api/v1" />
          </SettingsField>
          <SettingsField label="API key">
            <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} className={settingsInput}
                   autoComplete="off"
                   placeholder={llm.key_set ? `set (…${llm.key_last4}), leave empty to keep it` : "Enter key"} />
          </SettingsField>
          <SettingsField label="Model" hint="Runs the chat: writes the searches, reads the pages, composes and edits the slides. It needs tool calls, so not a thinking model.">
            {options.length ? (
              <select value={model} onChange={(e) => setModel(e.target.value)} className={settingsInput}>
                {!options.includes(model) && <option value={model}>{model || "– choose –"}</option>}
                {options.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            ) : (
              <input value={model} onChange={(e) => setModel(e.target.value)} className={settingsInput} />
            )}
          </SettingsField>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-secondary/10 pt-5">
          <Button type="submit" size="sm" disabled={save.isPending}>
            {save.isPending && <Loader2 className="animate-spin" />} Save
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => test.mutate()} disabled={test.isPending || !llm.key_set}>
            {test.isPending && <Loader2 className="animate-spin" />} Test connection
          </Button>
          {save.isSuccess && <span className="text-xs text-muted-foreground">Saved.</span>}
          {result && (
            <span className="animate-fade flex items-center gap-1.5 text-sm">
              {result.ok ? <CheckCircle2 className="size-4 text-emerald-600" /> : <XCircle className="size-4 text-red-600" />}
              <span className="text-muted-foreground">{result.ok ? `responds in ${result.seconds} s` : result.message}</span>
            </span>
          )}
        </div>
        <ErrorNote error={save.error || test.error || models.error} />
      </form>
    </SettingsCard>
  );
}
