const ago = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

/** "3 hours ago", "just now" … for a time in seconds since 1970. */
export function relative(seconds: number) {
  const diff = seconds - Date.now() / 1000;
  for (const [unit, size] of [["day", 86400], ["hour", 3600], ["minute", 60]] as const) {
    if (Math.abs(diff) >= size) return ago.format(Math.round(diff / size), unit);
  }
  return "just now";
}
