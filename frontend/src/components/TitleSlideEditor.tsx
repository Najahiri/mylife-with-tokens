import { Check } from "lucide-react";
import type { Deck } from "@/api/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const input = "w-full rounded-xl border border-input bg-background px-3.5 py-2 text-sm outline-none transition-colors "
  + "focus:border-secondary focus:ring-2 focus:ring-secondary/15";

/** Edits the title slide and which extra slides the deck has. Opens right below the title slide's preview. */
export function TitleSlideEditor({ deck, defaults, onDeck, onDone }: {
  deck: Deck;
  defaults?: { subtitle: string; kicker: string };
  onDeck: (change: Partial<Deck>) => void;
  onDone: () => void;
}) {
  // style: how the text looks on the slide, so the form reads like the slide
  const field = (key: "company" | "subtitle" | "kicker" | "author" | "organizer", label: string, placeholder?: string,
                 style?: string) => (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold text-secondary">{label}</span>
      <input value={deck[key]} placeholder={placeholder} onChange={(e) => onDeck({ [key]: e.target.value })}
             className={cn(input, style)} />
    </label>
  );
  const chip = (key: "overview" | "contacts_slide", label: string) => (
    <button type="button" aria-pressed={deck[key]} onClick={() => onDeck({ [key]: !deck[key] })}
            className={cn("flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-colors",
                          deck[key] ? "border-secondary bg-secondary text-secondary-foreground"
                                    : "border-input text-muted-foreground hover:border-secondary hover:text-secondary")}>
      {deck[key] && <Check className="size-3" />} {label}
    </button>
  );

  return (
    <form className="animate-in-up flex flex-col gap-4 rounded-3xl bg-cream p-5"
          onSubmit={(e) => { e.preventDefault(); onDone(); }}>
      {/* same order as on the title slide: label, company, subtitle, and speaker with unit at the bottom left */}
      <div className="sm:max-w-[50%]">{field("kicker", "Label above the title", defaults?.kicker, "text-xs font-bold text-primary placeholder:text-primary/50")}</div>
      {field("company", "Company", "Company name", "py-2.5 text-xl font-semibold")}
      {field("subtitle", "Subtitle", defaults?.subtitle, "text-base text-muted-foreground")}
      <div className="flex flex-col gap-3 pt-2 sm:max-w-[50%]">
        {field("author", "Speaker", "Name")}
        {field("organizer", "Organisation", "Unit, shown below the speaker")}
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-secondary/10 pt-4">
        <span className="mr-1 text-xs font-semibold text-secondary">Extra slides</span>
        {chip("overview", "Overview (at a glance)")}
        {chip("contacts_slide", "Contacts")}
        <Button type="submit" size="sm" className="ml-auto">Done</Button>
      </div>
    </form>
  );
}
