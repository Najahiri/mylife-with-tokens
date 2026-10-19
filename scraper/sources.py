"""The list of websites to crawl (sources.yaml), maintained through the UI page "Sources".

Each source: name (stable id, derived from the host), desc (label), url (start page),
optional sitemaps (list of URLs), max_pages (cap per crawl), enabled.
"""
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.yaml"
HEADER = ("# Websites for the crawler. Maintained through the UI (page \"Sources\").\n"
          "# Fields: name (id), desc (label), url (start page), optional: sitemaps, max_pages, enabled\n")


def load() -> list[dict]:
    return yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8")).get("sources", [])


def _name_for(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def validate(sources: list[dict]) -> list[dict]:
    out, seen = [], set()
    for s in sources:
        url = (s.get("url") or "").strip()
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.netloc:
            raise ValueError(f"Invalid start URL: {url!r} (must start with http:// or https://)")
        name = (s.get("name") or "").strip() or _name_for(url)
        if name in seen:
            raise ValueError(f"Website listed twice: {name}")
        seen.add(name)
        clean = {"name": name, "desc": (s.get("desc") or "").strip() or name, "url": url}
        sitemaps = [u.strip() for u in s.get("sitemaps") or [] if u and u.strip()]
        for u in sitemaps:
            if urlparse(u).scheme not in ("http", "https"):
                raise ValueError(f"Invalid sitemap URL for {name}: {u!r}")
        if sitemaps:
            clean["sitemaps"] = sitemaps
        if s.get("max_pages") not in (None, ""):
            mp = int(s["max_pages"])
            if mp < 1:
                raise ValueError(f"Max. pages for {name} must be at least 1")
            clean["max_pages"] = mp
        if s.get("enabled") is False:
            clean["enabled"] = False
        out.append(clean)
    return out


def save(sources: list[dict]) -> list[dict]:
    clean = validate(sources)
    SOURCES_FILE.write_text(HEADER + yaml.safe_dump({"sources": clean}, allow_unicode=True, sort_keys=False),
                            encoding="utf-8")
    return clean


def _counts(db: Path, sql: str) -> dict[str, int]:
    if not db.exists():
        return {}
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        return dict(con.execute(sql).fetchall())
    except sqlite3.Error:
        return {}


def with_status() -> list[dict]:
    """Sources plus how many pages each has in the crawl and in the search index."""
    crawled = _counts(ROOT / "data" / "crawl.sqlite",
                      "SELECT source, count(*) FROM pages WHERE status = 200 AND html IS NOT NULL GROUP BY source")
    indexed = _counts(ROOT / "data" / "index.sqlite", "SELECT source, count(*) FROM pages GROUP BY source")
    return [{**s, "enabled": s.get("enabled", True), "crawled": crawled.get(s["name"], 0),
             "indexed": indexed.get(s["name"], 0)} for s in load()]
