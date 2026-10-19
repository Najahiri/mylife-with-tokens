import { NavLink } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { cn } from "@/lib/utils";

const link = ({ isActive }: { isActive: boolean }) =>
  cn("eyebrow border-b-2 py-1 transition-colors",
    isActive ? "border-primary text-white" : "border-transparent text-white/70 hover:text-primary");

export function Header() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 60_000 });

  return (
    <header className="relative bg-deck text-deck-foreground">
      <div className="mx-auto flex h-20 max-w-[96rem] items-center gap-10 px-4 sm:px-6">
        <NavLink to="/" className="font-display text-[34px] leading-none font-extrabold tracking-[-0.02em] text-white"
                 aria-label="RAGlette">
          <span className="text-primary">RAG</span>lette
        </NavLink>
        <nav className="flex gap-6">
          <NavLink to="/" end className={link}>Chat</NavLink>
          <NavLink to="/sources" className={link}>Sources</NavLink>
          <NavLink to="/settings" className={link}>Settings</NavLink>
        </nav>
        {/* only shown when something needs attention */}
        <div className="ml-auto flex items-center gap-6 text-xs">
          {health.isError && (
            <span className="flex items-center gap-1.5 text-white/70">
              <span className="size-2 rounded-full bg-primary" /> Backend offline
            </span>
          )}
          {health.data && !health.data.llm_configured && (
            <NavLink to="/settings" className="flex items-center gap-1.5 text-white/70 hover:text-primary">
              <span className="size-2 rounded-full bg-amber-400" /> Set up Apertus
            </NavLink>
          )}
          <a href="https://hackapertus.ch/" target="_blank" rel="noreferrer"
             className="flex items-center gap-3 opacity-90 transition-opacity hover:opacity-100">
            <span className="eyebrow text-white/60">Built at</span>
            <img src="/hackapertus-logo-white.svg" alt="Hack Apertus" className="h-14 w-auto" />
          </a>
        </div>
      </div>
      <div className="absolute bottom-0 left-0 h-1 w-1/2 bg-primary" />
    </header>
  );
}
