import { useEffect, useRef, useState } from "react";
import { ChevronDown, Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type ExportFormat = "pptx" | "pdf";

const OPTIONS: { format: ExportFormat; label: string; hint: string }[] = [
  { format: "pptx", label: "PowerPoint (.pptx)", hint: "slides as pictures, their text in the notes" },
  { format: "pdf", label: "PDF", hint: "to send or print" },
];

/** "Export" button with a small menu to pick the file format. */
export function ExportMenu({ disabled, pending, onExport, up }: {
  disabled: boolean;
  up?: boolean;             // open the menu above the button
  pending: boolean;
  onExport: (format: ExportFormat) => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  // close on a click outside or Escape
  useEffect(() => {
    if (!open) return;
    const click = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", click);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", click);
      document.removeEventListener("keydown", key);
    };
  }, [open]);

  return (
    <div ref={box} className="relative">
      <Button size="sm" onClick={() => setOpen((o) => !o)} disabled={disabled || pending} className="shadow-lg"
              aria-haspopup="menu" aria-expanded={open}>
        {pending ? <Loader2 className="animate-spin" /> : <Download />} Export
        <ChevronDown className={cn("transition-transform duration-200", (open !== !!up) && "rotate-180")} />
      </Button>
      {open && (
        <div role="menu"
             className={cn("animate-zoom absolute right-0 z-20 flex w-64 flex-col rounded-2xl",
                           up ? "bottom-full mb-2 origin-bottom-right" : "top-full mt-2 origin-top-right",
                           " border border-secondary/15 bg-background p-1.5 shadow-lg")}>
          {OPTIONS.map((o) => (
            <button key={o.format} type="button" role="menuitem"
                    onClick={() => { setOpen(false); onExport(o.format); }}
                    className="flex flex-col items-start gap-0.5 rounded-xl px-3 py-2 text-left hover:bg-accent focus-visible:bg-accent focus-visible:outline-none">
              <span className="text-sm font-semibold">{o.label}</span>
              <span className="text-xs text-muted-foreground">{o.hint}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
