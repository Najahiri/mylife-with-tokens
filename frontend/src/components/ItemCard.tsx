import { AlertTriangle, ExternalLink, Mail, Phone, User } from "lucide-react";
import type { Item } from "@/api/types";

/** One checked pitch item: what it is, why it matters, the literal evidence and its sources. */
const CATEGORY: Record<string, string> = {
  research: "Research partner", infrastructure: "Infrastructure", programme: "Programme & funding",
  network: "Network", education: "Education & talent",
};

export function ItemCard({ item, hitOf }: { item: Item; hitOf: (url: string) => number | undefined }) {
  return (
    <article className="flex flex-col gap-3 border-l-4 border-primary bg-cream p-6">
      <div className="flex flex-col gap-1.5">
        {item.category && <span className="eyebrow text-secondary/60">{CATEGORY[item.category] ?? item.category}</span>}
        <h3 className="text-xl leading-tight font-bold">{item.title}</h3>
        {item.organisation && <span className="text-xs text-muted-foreground">{item.organisation}</span>}
      </div>
      <p className="text-sm leading-relaxed">{item.summary}</p>
      {item.relevance && <p className="text-sm leading-relaxed"><span className="font-semibold text-primary">Why: </span>{item.relevance}</p>}
      {!!item.facts?.length && (
        <ul className="flex flex-col gap-0.5 text-[13px]">
          {item.facts.map((f) => <li key={f} className="flex gap-1.5"><span className="text-primary">–</span>{f}</li>)}
        </ul>
      )}
      <blockquote className="border-l-2 border-secondary/40 pl-3 text-[13px] leading-relaxed text-muted-foreground italic">
        «{item.evidence}»
      </blockquote>
      {item.contacts.length > 0 && (
        <ul className="flex flex-col gap-1 text-[13px]">
          {item.contacts.map((c) => (
            <li key={c.name} className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
              <User className="size-3.5 text-primary" />
              <span className="font-semibold text-secondary">{c.name}</span>
              {c.role && <span className="text-muted-foreground">· {c.role}</span>}
              {c.email && (
                <a href={`mailto:${c.email}`} className="flex items-center gap-1 text-muted-foreground hover:text-primary">
                  <Mail className="size-3" /> {c.email}
                </a>
              )}
              {c.phone && (
                <a href={`tel:${c.phone.replace(/\s/g, "")}`} className="flex items-center gap-1 text-muted-foreground hover:text-primary">
                  <Phone className="size-3" /> {c.phone}
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
      {!!item.edited?.length && (
        <p className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="rounded-full bg-secondary px-2 py-0.5 font-semibold text-secondary-foreground">Changed on request</span>
          <span className="text-muted-foreground">{item.edited.join(", ")}</span>
          {!!item.unbacked?.length && (
            <span className="text-amber-700 dark:text-amber-400">· not in the source: {item.unbacked.join(", ")}</span>
          )}
        </p>
      )}
      {item.flags.filter((f) => !f.startsWith("changed on request")).map((f) => (
        <p key={f} className="flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-400">
          <AlertTriangle className="size-3.5" /> {f}
        </p>
      ))}
      <ul className="mt-auto flex flex-col gap-1.5 border-t border-secondary/15 pt-3">
        {item.sources.map((s) => (
          <li key={s.url} className="min-w-0 text-xs">
            <a href={s.url} target="_blank" rel="noreferrer" className="flex items-baseline gap-1.5 hover:text-primary">
              <ExternalLink className="size-3 shrink-0 translate-y-0.5 text-muted-foreground" />
              <span className="truncate">
                {hitOf(s.url) && <span className="font-mono text-muted-foreground">Hit {hitOf(s.url)} · </span>}
                {s.title || s.url}
              </span>
            </a>
            <span className="pl-[18px] text-muted-foreground">{s.website}</span>
          </li>
        ))}
      </ul>
    </article>
  );
}
