"""Size estimate from a (partial) crawl: pages known per source, bytes per page, projected storage."""
import re
import sqlite3
import sys

db = sqlite3.connect(sys.argv[1])

rows = db.execute("""
    SELECT source, sum(state IN ('done','error')) FROM frontier GROUP BY source
""").fetchall()

sizes = dict(((s, (n, raw, comp)) for s, n, raw, comp in db.execute("""
    SELECT source, count(*), avg(bytes), avg(length(html)) FROM pages
    WHERE status = 200 AND html IS NOT NULL GROUP BY source
""")))

skip_ext = re.compile(r"\.(pdf|jpe?g|png|gif|svg|webp|ico|zip|docx?|xlsx?|pptx?|mp[34]|ics|css|js|xml)$", re.I)
pending = {}
for src, url in db.execute("SELECT source, url FROM frontier WHERE state='todo'"):
    if not skip_ext.search(url):
        pending[src] = pending.get(src, 0) + 1

lang = dict(db.execute("""
    SELECT source, round(100.0 * sum(url LIKE '%\\_fra.html' ESCAPE '\\' OR url LIKE '%\\_ita.html' ESCAPE '\\') / count(*))
    FROM frontier GROUP BY source
"""))

tot_known = tot_bytes = 0
print(f"{'source':26} {'fetched':>7} {'pending':>7} {'known':>7} {'done?':>5} {'KB raw':>7} {'KB zlib':>7} {'%fr/it':>6}")
for src, fetched in sorted(rows, key=lambda r: -(r[1] + pending.get(r[0], 0))):
    p = pending.get(src, 0)
    n, raw, comp = sizes.get(src, (0, 0, 0))
    known = fetched + p
    tot_known += known
    tot_bytes += known * (comp or 0)
    print(f"{src:26} {fetched:7} {p:7} {known:7} {'yes' if p == 0 else 'no':>5} "
          f"{(raw or 0)/1024:7.0f} {(comp or 0)/1024:7.0f} {lang.get(src, 0):6.0f}")

n, raw, comp = db.execute("SELECT count(*), avg(bytes), avg(length(html)) FROM pages WHERE html IS NOT NULL").fetchone()
print(f"\nfetched HTML pages: {n}, avg {raw/1024:.0f} KB raw, {comp/1024:.0f} KB compressed")
print(f"known URLs so far (lower bound): {tot_known}")
print(f"storage for known URLs: ~{tot_bytes/1e9:.2f} GB compressed (~{tot_known*raw/1e9:.2f} GB raw)")
