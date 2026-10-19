import type { ReactNode } from "react";

export const settingsInput = "h-10 w-full rounded-xl border border-input bg-background px-3 text-sm tabular-nums outline-none "
  + "transition-colors focus:border-secondary focus:ring-2 focus:ring-secondary/15";

/** One card of the settings page; `id` is the anchor the side navigation jumps to. */
export function SettingsCard({ id, title, intro, applies, children, footer }: {
  id: string; title: string; intro?: string; applies?: string; children: ReactNode; footer?: ReactNode;
}) {
  return (
    <section id={id} className="flex scroll-mt-6 flex-col gap-6 rounded-3xl bg-cream p-6 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="flex flex-col gap-1">
          <h2 className="text-2xl leading-none font-bold">{title}</h2>
          {intro && <p className="text-sm text-muted-foreground">{intro}</p>}
        </div>
        {applies && (
          <span className="rounded-full bg-background px-3 py-1 text-[11px] font-medium text-muted-foreground">
            applies {applies}
          </span>
        )}
      </div>
      {children}
      {footer}
    </section>
  );
}

/** Label, control and explanation of one setting. */
export function SettingsField({ label, note, hint, children }: {
  label: string; note?: ReactNode; hint?: string; children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="flex flex-wrap items-baseline gap-x-2 text-sm font-semibold text-secondary">
        {label}
        {note}
      </span>
      {children}
      {hint && <span className="text-xs leading-relaxed text-muted-foreground">{hint}</span>}
    </div>
  );
}
