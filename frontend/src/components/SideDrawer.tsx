import type { CSSProperties, ReactNode } from "react";
import { ChevronsLeft, ChevronsRight } from "lucide-react";

const OPEN = "min(52vw, 54rem)";   // width of the open drawer, handle included
const HANDLE = "2.75rem";

/** A panel on the right that slides in and out and pushes the content next to it.
 *  The handle on its left edge toggles it; folded away only the handle stays, with the label written on it.
 *  The content keeps its width while sliding, so it moves instead of being squeezed. Below lg it is always open. */
export function SideDrawer({ open, onToggle, label, children }: {
  open: boolean;
  onToggle: () => void;
  label: string;
  children: ReactNode;
}) {
  const vars = { "--drawer-w": open ? OPEN : HANDLE, "--drawer-inner": `calc(${OPEN} - ${HANDLE})` } as CSSProperties;
  return (
    <div style={vars}
         className="flex lg:w-(--drawer-w) lg:min-h-0 lg:shrink-0 lg:overflow-hidden motion-safe:lg:transition-[width] motion-safe:lg:duration-300 motion-safe:lg:ease-in-out">
      <button type="button" onClick={onToggle} aria-expanded={open}
              aria-label={open ? "Fold the presentation away" : `Show the presentation: ${label}`}
              title={open ? "Fold the presentation away" : "Show the presentation"}
              className="group hidden w-11 shrink-0 cursor-pointer flex-col items-center gap-5 border-l border-secondary/15 pt-1 text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary lg:flex">
        <span className="rounded-full border border-secondary/25 p-1.5 transition-colors group-hover:border-primary">
          {open ? <ChevronsRight className="size-4" /> : <ChevronsLeft className="size-4" />}
        </span>
        {!open && <span className="eyebrow rotate-180 whitespace-nowrap [writing-mode:vertical-rl]">{label}</span>}
      </button>
      <div className="min-w-0 flex-1 lg:overflow-hidden" inert={!open}>
        <div className="h-full lg:w-(--drawer-inner) lg:pl-3">{children}</div>
      </div>
    </div>
  );
}
