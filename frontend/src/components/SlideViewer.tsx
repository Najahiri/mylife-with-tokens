import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Loader2, Maximize, Trash2, X } from "lucide-react";
import { api } from "@/api/client";

/** Big view of the slides: arrow keys or buttons to page, F for full screen, Esc to close. Item slides can be deleted. */
export function SlideViewer({ request, preview, index, itemOf, locked, onRemove, onIndex, onClose }: {
  request: string;          // the same request as the small preview, rendered again at a higher resolution
  preview: string[];        // small slides, shown until the sharp ones are there
  index: number;
  itemOf: (i: number) => string | undefined;   // the item a slide shows, if it is an item slide
  locked: boolean;
  onRemove: (title: string) => void;
  onIndex: (i: number) => void;
  onClose: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const sharp = useQuery({
    queryKey: ["slides-hd", request], queryFn: () => api.slides({ ...JSON.parse(request), ppi: 170 }),
    staleTime: Infinity,
  });
  // the sharp slides only while they match the preview (after a deletion the preview is newer)
  const slides = sharp.data?.slides.length === preview.length ? sharp.data.slides : preview;
  const item = itemOf(index);
  const count = slides.length;
  const go = (d: number) => onIndex(Math.min(count - 1, Math.max(0, index + d)));

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !document.fullscreenElement) onClose();
      else if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === " ") { e.preventDefault(); go(1); }
      else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); go(-1); }
      else if (e.key.toLowerCase() === "f") fullscreen();
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  });

  function fullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else box.current?.requestFullscreen().catch(() => { /* not allowed here: the big view stays */ });
  }

  return (
    <div ref={box} role="dialog" aria-modal="true" aria-label={`Slide ${index + 1} of ${count}`}
         className="fixed inset-0 z-50 flex flex-col bg-black/92 text-white" onClick={onClose}>
      <div className="flex items-center gap-4 px-5 py-3 text-sm" onClick={(e) => e.stopPropagation()}>
        <span className="tabular-nums text-white/70">{index + 1} / {count}</span>
        {sharp.isFetching && <Loader2 className="size-4 animate-spin text-white/50" />}
        <span className="ml-auto hidden text-xs text-white/40 sm:inline">← → to page · F full screen · Esc close</span>
        {item && (
          <button type="button" onClick={() => onRemove(item)} disabled={locked}
                  title={locked ? "Wait until the agent has answered" : undefined}
                  className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs hover:bg-primary disabled:opacity-40 disabled:hover:bg-transparent">
            <Trash2 className="size-3.5" /> Delete slide
          </button>
        )}
        <button type="button" onClick={fullscreen} className="rounded-full p-2 hover:bg-white/10" aria-label="Full screen">
          <Maximize className="size-4" />
        </button>
        <button type="button" onClick={onClose} className="rounded-full p-2 hover:bg-white/10" aria-label="Close">
          <X className="size-5" />
        </button>
      </div>
      <div className="relative flex min-h-0 flex-1 items-center justify-center px-4 pb-6 sm:px-16">
        <img src={slides[index]} alt={`Slide ${index + 1}`} onClick={(e) => e.stopPropagation()}
             className="max-h-full max-w-full bg-white object-contain shadow-2xl" />
        <button type="button" onClick={(e) => { e.stopPropagation(); go(-1); }} disabled={index === 0}
                className="absolute left-2 rounded-full p-3 hover:bg-white/10 disabled:opacity-20 sm:left-4" aria-label="Previous slide">
          <ChevronLeft className="size-7" />
        </button>
        <button type="button" onClick={(e) => { e.stopPropagation(); go(1); }} disabled={index >= count - 1}
                className="absolute right-2 rounded-full p-3 hover:bg-white/10 disabled:opacity-20 sm:right-4" aria-label="Next slide">
          <ChevronRight className="size-7" />
        </button>
      </div>
    </div>
  );
}
