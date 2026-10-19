import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { api } from "@/api/client";
import type { LlmSettings } from "@/api/types";
import { ConfigGroupForm } from "@/components/ConfigGroupForm";
import { ErrorNote } from "@/components/Step";
import { Button } from "@/components/ui/button";

const field = "h-9 border border-input bg-background px-2 text-sm outline-none focus:border-secondary";

export function SettingsPage() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  if (settings.isPending || config.isPending) return <p className="pt-10 text-sm text-muted-foreground">Loading …</p>;
  if (settings.isError || config.isError)
    return <div className="pt-10"><ErrorNote error={settings.error || config.error} /></div>;

  return (
    // same width as the other pages, the form itself stays narrow
    <div className="mx-auto w-full max-w-6xl pt-10 pb-24">
      <div className="flex max-w-3xl flex-col gap-8">
        <div className="flex flex-col gap-1">
          <h1 className="text-5xl leading-none font-bold tracking-[-0.02em]">Settings</h1>
          <p className="text-sm text-muted-foreground">
            All parameters of the pipeline. Changed values apply to all requests until they are reset.
          </p>
        </div>
        <ApiAccess llm={settings.data.llm} />
        {config.data.groups.map((g) => (
          // the key remounts a group with fresh values after saving or resetting
          <ConfigGroupForm key={`${g.section}-${JSON.stringify(g.fields.map((f) => f.value))}`} group={g} />
        ))}
      </div>
    </div>
  );
}

function ApiAccess({ llm }: { llm: LlmSettings }) {
  const qc = useQueryClient();
  const [baseUrl, setBaseUrl] = useState(llm.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [modelQueries, setModelQueries] = useState(llm.model_queries ?? "");
  const [modelBrief, setModelBrief] = useState(llm.model_brief ?? "");
  const [modelAgent, setModelAgent] = useState(llm.model_agent ?? "");

  const models = useQuery({ queryKey: ["models"], queryFn: api.models, enabled: llm.key_set });
  const save = useMutation({
    mutationFn: () => api.saveSettings({ base_url: baseUrl, api_key: apiKey || undefined,
      model_queries: modelQueries, model_brief: modelBrief, model_agent: modelAgent }),
    onSuccess: () => {
      setApiKey("");
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["health"] });
      qc.invalidateQueries({ queryKey: ["models"] });
    },
  });
  const test = useMutation({ mutationFn: api.test });
  const options = models.data?.models ?? [];

  const modelField = (label: string, hint: string, value: string, set: (v: string) => void) => (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium">{label}</span>
      {options.length ? (
        <select value={value} onChange={(e) => set(e.target.value)} className={field}>
          {!options.includes(value) && <option value={value}>{value || "– choose –"}</option>}
          {options.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      ) : (
        <input value={value} onChange={(e) => set(e.target.value)} className={field} />
      )}
      <span className="text-[11px] text-muted-foreground">{hint}</span>
    </label>
  );

  return (
    <section className="flex flex-col gap-5 border-l-4 border-primary bg-cream p-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-2xl leading-none font-bold">Apertus access</h2>
        <p className="text-xs text-muted-foreground">
          OpenAI-compatible API. The key stays in the backend and is never sent back to the browser.
        </p>
      </div>
      <form className="flex flex-col gap-5" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium">API base URL</span>
          <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} className={field}
                 placeholder="https://gateway.keera.ch/api/v1" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium">API key</span>
          <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} className={field}
                 autoComplete="off"
                 placeholder={llm.key_set ? `set (…${llm.key_last4}), leave empty to keep it` : "Enter key"} />
        </label>
        <div className="grid gap-5 sm:grid-cols-2">
          {modelField("Model for search terms (B2)", "translates buzzwords into technical terms, e.g. 8B", modelQueries, setModelQueries)}
          {modelField("Model for pitch information (B4)", "reads the pages and backs the items with evidence, e.g. 70B", modelBrief, setModelBrief)}
          {modelField("Model for the agent (chat)", "orchestrates the chat: writes the searches, reads pages, composes the items, e.g. 70B", modelAgent, setModelAgent)}
        </div>
        <div className="flex gap-2">
          <Button type="submit" size="sm" disabled={save.isPending}>
            {save.isPending && <Loader2 className="animate-spin" />} Save
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => test.mutate()}
                  disabled={test.isPending || !llm.key_set}>
            {test.isPending && <Loader2 className="animate-spin" />} Test connection
          </Button>
        </div>
        {save.isSuccess && <p className="text-sm text-muted-foreground">Saved.</p>}
        <ErrorNote error={save.error || test.error || models.error} />
      </form>
      {test.data && (
        <ul className="flex flex-col gap-2 text-sm">
          {test.data.results.map((r) => (
            <li key={r.role} className="flex items-start gap-2">
              {r.ok ? <CheckCircle2 className="mt-0.5 size-4 text-emerald-600" /> : <XCircle className="mt-0.5 size-4 text-red-600" />}
              <span>
                <span className="font-medium">{{ queries: "Search terms", brief: "Pitch information", agent: "Agent" }[r.role] ?? r.role}</span>
                <span className="text-muted-foreground"> · {r.seconds} s · {r.ok ? "responds" : r.message}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
