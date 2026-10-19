"""Probe every source domain: reachability, redirects, robots.txt, sitemap, HTML vs. JS."""

import asyncio
import json
import re
import sys
from urllib.parse import urljoin, urlparse

import httpx
import openpyxl
from selectolax.lexbor import LexborHTMLParser as HTMLParser

UA = "ApertusHackathonBot/0.1 (research prototype, public pages only)"


def load_sources(path):
    ws = openpyxl.load_workbook(path).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))[1:]
    return [{"name": r[0], "desc": r[1], "url": r[2]} for r in rows if r and r[2]]


async def probe(client, src):
    out = dict(src)
    try:
        r = await client.get(src["url"])
        out["status"] = r.status_code
        out["final_url"] = str(r.url)
        out["bytes"] = len(r.content)
        host = urlparse(str(r.url)).netloc
        tree = HTMLParser(r.text)
        for n in tree.css("script, style, noscript"):
            n.decompose()
        body = tree.body.text(separator=" ") if tree.body else ""
        out["text_chars"] = len(re.sub(r"\s+", " ", body).strip())
        links = {
            urljoin(str(r.url), a.attributes.get("href") or "").split("#")[0]
            for a in tree.css("a[href]")
        }
        out["same_host_links"] = sum(1 for l in links if urlparse(l).netloc == host)
        base = f"{urlparse(str(r.url)).scheme}://{host}"
        rb = await client.get(base + "/robots.txt")
        out["robots_sitemaps"] = (
            re.findall(r"(?im)^sitemap:\s*(\S+)", rb.text)
            if rb.status_code == 200
            else []
        )
        sm = await client.get(base + "/sitemap.xml")
        out["sitemap_xml"] = (
            sm.status_code
            if "<loc>" not in sm.text
            else f"{sm.status_code} ({sm.text.count('<loc>')} loc)"
        )
    except Exception as e:
        out["error"] = repr(e)
    return out


async def main(xlsx):
    sources = load_sources(xlsx)
    limits = httpx.Limits(max_connections=8)
    async with httpx.AsyncClient(
        headers={"User-Agent": UA}, follow_redirects=True, timeout=20, limits=limits
    ) as client:
        results = await asyncio.gather(*(probe(client, s) for s in sources))
    for r in results:
        print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
