import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CircleDashed, Loader2, RefreshCw, X } from "lucide-react";
import { api } from "@/api/client";
import type { IndexJob } from "@/api/types";
import { SettingsCard } from "@/components/SettingsCard";
import { ErrorNote } from "@/components/Step";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { relative } from "@/lib/time";
import { useElapsed } from "@/lib/useElapsed";
import { cn } from "@/lib/utils";

const n = (x: number | undefined) => (x ?? 0).toLocaleString("en-US");

/** Search index: what is live, and a manual update (crawl, prepare, embed, load, switch) with its progress. */
export function IndexUpdateCard() {
  const qc = useQueryClient();
  const [refetch, setRefetch] = useState(false);
  const status = useQuery({
    queryKey: ["index"], queryFn: api.indexStatus,
    refetchInterval: (q) => (q.state.data?.job?.state === "running" ? 1000 : false),
  });
  const start = useMutation({ mutationFn: () => api.startUpdate(refetch), onSuccess: (d) => qc.setQueryData(["index"], d) });
  const cancel = useMutation({ mutationFn: api.cancelUpdate, onSuccess: (d) => qc.setQueryData(["index"], d) });
  const job = status.data?.job;
  const running = job?.state === "running";

  // when an update finishes, the page counts elsewhere are out of date
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && !running) {
      qc.invalidateQueries({ queryKey: ["health"] });
      qc.invalidateQueries({ queryKey: ["sources"] });
    }
    wasRunning.current = running;
  }, [running, qc]);

  return (
    <SettingsCard id="index" title="Search index"
                  intro="The pages the agent searches. Update it after adding websites or to pick up new pages.">
      {status.data && (
        <p className="text-sm text-muted-foreground tabular-nums">
          <span className="font-semibold text-secondary">{n(status.data.pages)}</span> pages ·{" "}
          <span className="font-semibold text-secondary">{n(status.data.chunks)}</span> chunks
          {status.data.built && <> · built {relative(status.data.built)}</>}
        </p>
      )}
      {running && job ? (
        <Progress job={job} onCancel={() => cancel.mutate()} cancelling={cancel.isPending} />
      ) : (
        <div className="flex flex-col gap-5">
          {job && <Outcome job={job} />}
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-secondary/10 pt-5">
            <Button size="sm" onClick={() => start.mutate()} disabled={start.isPending}>
              {start.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />} Update index
            </Button>
            <Switch checked={refetch} onChange={setRefetch} label="Re-fetch all pages" showLabel />
            <span className="text-xs text-muted-foreground">
              {refetch ? "Every page is fetched again: picks up changed pages, takes hours."
                       : "Only new pages are fetched; unchanged chunks keep their vectors."}
            </span>
          </div>
        </div>
      )}
      <ErrorNote error={status.error || start.error || cancel.error} />
    </SettingsCard>
  );
}

function Progress({ job, onCancel, cancelling }: { job: IndexJob; onCancel: () => void; cancelling: boolean }) {
  const elapsed = useElapsed(true, job.started * 1000);
  const index = job.stages.findIndex((s) => s.key === job.stage);
  const overall = Math.round(((index + job.share) / job.stages.length) * 100);
  return (
    <div className="animate-fade flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between gap-4">
          <span className="text-sm font-semibold text-secondary">{job.stages[index]?.label} …</span>
          <span className="text-sm text-muted-foreground tabular-nums">{overall} % · {elapsed}</span>
        </div>
        <div className="h-2.5 overflow-hidden rounded-full bg-background" role="progressbar" aria-valuenow={overall}
             aria-valuemin={0} aria-valuemax={100} aria-label="Index update">
          <div className="h-full rounded-full bg-primary transition-[width] duration-700 ease-out" style={{ width: `${overall}%` }} />
        </div>
        <span className="text-xs text-muted-foreground">{job.detail}</span>
      </div>
      <ol className="grid gap-2 sm:grid-cols-5">
        {job.stages.map((s) => (
          <li key={s.key} className={cn("flex items-start gap-2 rounded-2xl bg-background px-3 py-2.5 text-xs transition-opacity",
                                        s.status === "pending" && "opacity-50")}>
            {s.status === "done" ? <Check className="mt-px size-3.5 shrink-0 text-emerald-600" />
              : s.status === "running" ? <Loader2 className="mt-px size-3.5 shrink-0 animate-spin text-primary" />
              : <CircleDashed className="mt-px size-3.5 shrink-0 text-muted-foreground" />}
            <span className={cn(s.status === "running" ? "font-semibold text-secondary" : "text-muted-foreground")}>{s.label}</span>
          </li>
        ))}
      </ol>
      <div className="flex items-center gap-3 border-t border-secondary/10 pt-5">
        <Button size="sm" variant="outline" onClick={onCancel} disabled={cancelling || job.stage === "switch"}>
          <X /> Cancel
        </Button>
        <span className="text-xs text-muted-foreground">
          The chat keeps working on the current index meanwhile; it switches over at the end.
        </span>
      </div>
    </div>
  );
}

function Outcome({ job }: { job: IndexJob }) {
  if (job.state === "error") return <ErrorNote error={new Error(`The last update failed: ${job.error}`)} />;
  const done = job.state === "done";
  return (
    <p className="animate-fade flex items-start gap-2 text-sm">
      {done ? <Check className="mt-0.5 size-4 shrink-0 text-emerald-600" /> : <X className="mt-0.5 size-4 shrink-0 text-muted-foreground" />}
      <span>
        <span className="font-semibold text-secondary">{done ? "Updated" : "Cancelled"}</span>
        {job.finished && <span className="text-muted-foreground"> {relative(job.finished)}</span>}
        <span className="text-muted-foreground"> · {job.detail}</span>
      </span>
    </p>
  );
}
