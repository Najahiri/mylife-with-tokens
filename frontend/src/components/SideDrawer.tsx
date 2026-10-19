import type { CSSProperties, ReactNode } from "react";
import { cn } from "@/lib/utils";

const OPEN = "min(52vw, 54rem)";   // width of the open drawer

/** A panel on the right that slides in and out and pushes the content next to it. Folded away it takes no space;
 *  the button that opens it lives elsewhere. The content keeps its width while sliding, so it moves instead of being
 *  squeezed. Below lg it is always shown, under the content. */
export function SideDrawer({ open, children }: { open: boolean; children: ReactNode }) {
  return (
    <div style={{ "--drawer-w": OPEN } as CSSProperties} inert={!open}
         className={cn("lg:min-h-0 lg:shrink-0 lg:overflow-hidden",
                       "motion-safe:lg:transition-[width,opacity] motion-safe:lg:duration-500 motion-safe:lg:ease-[cubic-bezier(0.2,0.7,0.2,1)]",
                       open ? "lg:w-(--drawer-w) lg:opacity-100" : "lg:w-0 lg:opacity-0")}>
      <div className="h-full lg:w-(--drawer-w) lg:border-l lg:border-secondary/15 lg:pl-5">{children}</div>
    </div>
  );
}
