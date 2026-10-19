import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** One step of the pitch workflow: red step label, serif title, optional actions on the right, then content. */
export function Step({ n, title, meta, actions, disabled, children }: {
  n: number;
  title: string;
  meta?: ReactNode;
  actions?: ReactNode;
  disabled?: boolean;
  children?: ReactNode;
}) {
  return (
    <section className={cn("flex flex-col gap-4", disabled && "opacity-40")} aria-disabled={disabled}>
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <div className="flex flex-col gap-1.5">
          <span className="eyebrow text-primary">Step {String(n).padStart(2, "0")}</span>
          <h2 className="text-3xl leading-none font-bold">{title}</h2>
        </div>
        {meta && <span className="pb-0.5 text-sm text-muted-foreground">{meta}</span>}
        {actions && <div className="ml-auto flex flex-wrap gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p className="border-l-4 border-primary bg-cream py-2 pl-3 text-sm text-foreground">
      {error instanceof Error ? error.message : String(error)}
    </p>
  );
}
