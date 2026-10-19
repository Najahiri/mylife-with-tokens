import { cn } from "@/lib/utils";

/** On/off switch; `label` is read out by screen readers (and shown next to it when `showLabel`). */
export function Switch({ checked, onChange, label, showLabel }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; showLabel?: boolean;
}) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={showLabel ? undefined : label}
            onClick={() => onChange(!checked)} className="flex items-center gap-3 text-sm">
      <span className={cn("relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200", checked ? "bg-secondary" : "bg-input")}>
        <span className={cn("absolute top-0.5 left-0.5 size-5 rounded-full bg-background shadow transition-transform duration-200",
                            checked && "translate-x-5")} />
      </span>
      {showLabel && label}
    </button>
  );
}
