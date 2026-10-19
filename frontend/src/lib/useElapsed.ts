import { useEffect, useState } from "react";

/** mm:ss since `since` (ms timestamp), ticking every second while active. */
export function useElapsed(active: boolean, since: number) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active]);
  const seconds = active ? Math.max(0, Math.floor((now - since) / 1000)) : 0;
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
