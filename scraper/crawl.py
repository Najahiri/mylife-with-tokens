"""Polite crawler: one worker per source, raw HTML stored zlib-compressed in SQLite.

Usage:
    python scraper/crawl.py sources.yaml data/crawl.sqlite --max-pages 150
Re-running continues where it stopped (frontier lives in the DB), so the cap can be raised later.
"""
import argparse
import asyncio
import gzip
import re
import sqlite3
import time
import zlib
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
import yaml
from protego import Protego
from selectolax.lexbor import LexborHTMLParser

UA = "ApertusHackathonBot/0.1 (research prototype, public pages only)"
DELAY = 1.0  # seconds between requests to the same host
SKIP_EXT = re.compile(
    r"\.(pdf|jpe?g|png|gif|svg|webp|ico|zip|gz|tar|docx?|docm|xlsx?|xlsm|pptx?|mp[34]|gb|fasta|eps|rar|7z|dmg|exe|mov|avi|wav|ics|css|js|json|xml|txt|eps|tiff?)$",
    re.I,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS frontier (
    url TEXT PRIMARY KEY, source TEXT, depth INT, state TEXT DEFAULT 'todo'  -- todo|done|skip|error
);
CREATE INDEX IF NOT EXISTS frontier_todo ON frontier(source, state, depth);
CREATE TABLE IF NOT EXISTS pages (
    url TEXT PRIMARY KEY, source TEXT, final_url TEXT, status INT, content_type TEXT,
    fetched_at REAL, bytes INT, html BLOB
);
CREATE TABLE IF NOT EXISTS offsite (  -- links to other hosts, to discover candidate sources
    host TEXT, source TEXT, n INT DEFAULT 1, PRIMARY KEY (host, source)
);
"""


def norm_host(h):
    return h.lower().removeprefix("www.")


def normalize(url):
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return None
    # Drop fragments and query strings (avoids preview/print/session traps).
    return urlunparse(("https", p.netloc.lower(), p.path or "/", "", "", ""))


def extract_links(html, base):
    tree = LexborHTMLParser(html)
    for a in tree.css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if href and not href.startswith(("mailto:", "tel:", "javascript:", "#")):
            u = normalize(urljoin(base, href))
            if u:
                yield u


async def fetch_sitemap_urls(client, url, seen=None, depth=0):
    seen = seen if seen is not None else set()
    if url in seen or depth > 3:
        return []
    seen.add(url)
    try:
        r = await client.get(url)
        body = gzip.decompress(r.content).decode() if url.endswith(".gz") else r.text
    except Exception:
        return []
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)
    if "<sitemapindex" in body:
        out = []
        for loc in locs:
            out += await fetch_sitemap_urls(client, loc, seen, depth + 1)
        return out
    return locs


class Crawler:
    def __init__(self, db, client, max_pages, stop=None):
        """stop: optional callable; when it returns True the crawl ends after the current page."""
        self.db, self.client, self.max_pages, self.stop = db, client, max_pages, stop
        self.fetched = 0           # pages fetched in this run
        self.finished = set()      # sources that are done

    def add(self, url, source, depth):
        self.db.execute("INSERT OR IGNORE INTO frontier(url, source, depth) VALUES (?,?,?)", (url, source, depth))

    def count_done(self, source):
        return self.db.execute(
            "SELECT count(*) FROM frontier WHERE source=? AND state IN ('done','error')", (source,)
        ).fetchone()[0]

    async def run_source(self, src):
        name = src["name"]
        cap = src.get("max_pages", self.max_pages)
        start = await self.client.get(src["url"])
        host = norm_host(urlparse(str(start.url)).netloc)
        base = f"https://{urlparse(str(start.url)).netloc}"

        robots_txt = ""
        try:
            rb = await self.client.get(base + "/robots.txt")
            robots_txt = rb.text if rb.status_code == 200 else ""
        except Exception:
            pass
        robots = Protego.parse(robots_txt)
        allowed = lambda u: robots.can_fetch(u, UA)

        self.add(normalize(str(start.url)), name, 0)
        for sm in set(src.get("sitemaps", [])) | set(robots.sitemaps):
            for u in await fetch_sitemap_urls(self.client, sm):
                if (u := normalize(u)) and norm_host(urlparse(u).netloc) == host:
                    self.add(u, name, 1)
        self.db.commit()

        while self.count_done(name) < cap and not (self.stop and self.stop()):
            row = self.db.execute(
                "SELECT url, depth FROM frontier WHERE source=? AND state='todo' ORDER BY depth LIMIT 1", (name,)
            ).fetchone()
            if not row:
                break
            url, depth = row
            if SKIP_EXT.search(urlparse(url).path) or not allowed(url):
                self.db.execute("UPDATE frontier SET state='skip' WHERE url=?", (url,))
                continue
            t0 = time.monotonic()
            state = "done"
            try:
                r = await self.client.get(url)
                ctype = r.headers.get("content-type", "")
                final = normalize(str(r.url))
                html = r.text if "html" in ctype else ""
                self.db.execute(
                    "INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?,?,?,?)",
                    (url, name, final, r.status_code, ctype, time.time(), len(r.content),
                     zlib.compress(html.encode()) if html else None),
                )
                if r.status_code == 200 and html and norm_host(urlparse(final).netloc) == host:
                    for link in extract_links(html, str(r.url)):
                        lh = norm_host(urlparse(link).netloc)
                        if lh == host:
                            self.add(link, name, depth + 1)
                        elif lh:
                            self.db.execute(
                                "INSERT INTO offsite(host, source) VALUES (?,?) "
                                "ON CONFLICT DO UPDATE SET n=n+1", (lh, name))
            except Exception as e:
                state = "error"
                print(f"[{name}] {url}: {e!r}")
            self.db.execute("UPDATE frontier SET state=? WHERE url=?", (state, url))
            self.db.commit()
            self.fetched += 1
            await asyncio.sleep(max(0, DELAY - (time.monotonic() - t0)))
        self.finished.add(name)
        print(f"[{name}] finished: {self.count_done(name)} fetched")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sources")
    ap.add_argument("db")
    ap.add_argument("--max-pages", type=int, default=150)
    ap.add_argument("--only", nargs="*", help="restrict to these source names")
    args = ap.parse_args()

    sources = [s for s in yaml.safe_load(open(args.sources))["sources"] if s.get("enabled", True)]
    if args.only:
        sources = [s for s in sources if s["name"] in args.only]
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)   # data/ does not exist in a fresh clone
    db = sqlite3.connect(args.db)
    db.executescript(SCHEMA)
    async with httpx.AsyncClient(headers={"User-Agent": UA}, follow_redirects=True, timeout=30,
                                 limits=httpx.Limits(max_connections=len(sources) + 2)) as client:
        crawler = Crawler(db, client, args.max_pages)
        results = await asyncio.gather(*(crawler.run_source(s) for s in sources), return_exceptions=True)
    for s, r in zip(sources, results):
        if isinstance(r, Exception):
            print(f"[{s['name']}] FAILED: {r!r}")


if __name__ == "__main__":
    asyncio.run(main())
