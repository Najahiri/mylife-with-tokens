"""Pipeline 2 (B2–B6): buzzwords -> search terms -> pages -> checked pitch information.

    B2   search terms: buzzwords directly, or translated by Apertus (model "queries")
    B3   search (rag_model/search.py)
    B4   full page texts, lost-in-the-middle order, Apertus (model "brief")
    B5   checks: sources exist, evidence quote is on a cited page, key facts are on a cited page, contacts
         (name, email, phone) are on a cited page, summary is close to its evidence
    B6   result + trace (data/traces/*.json)

CLI for testing:
    python -m rag_model.brief "digital health" "wearables" "precision diabetes care" --mode apertus
"""
import argparse
import json
import re
import sqlite3
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

import yaml
from haystack import Document, Pipeline
from haystack.components.builders import ChatPromptBuilder
from haystack.components.rankers import LostInTheMiddleRanker
from haystack.dataclasses import ChatMessage
from rapidfuzz import fuzz

from rag_model.llm import generator, parse_json
from rag_model import config
from rag_model.search import ROOT, Page, Searcher

PROMPTS = ROOT / "prompts"
INDEX_DB = ROOT / "data" / "index.sqlite"
TRACES = ROOT / "data" / "traces"
TITLES = {"prof", "dr", "med", "phil", "nat", "rer", "pd", "phd", "msc", "bsc", "dipl", "ing", "mag", "lic",
          "dvm", "vet", "em", "hon", "mba", "md", "mme", "mmed", "ma", "ba", "jur"}


def _prompt_pipeline(name: str, role: str, n_items: dict[str, int] | None = None,
                     max_items: dict[str, int] | None = None) -> Pipeline:
    """n_items / max_items: {list field: exact / maximum number of entries}, enforced through the answer schema."""
    spec = yaml.safe_load((PROMPTS / f"{name}.yaml").read_text(encoding="utf-8"))
    for field, n in (n_items or {}).items():
        spec["schema"]["properties"][field].update(minItems=n, maxItems=n)
    for field, n in (max_items or {}).items():
        spec["schema"]["properties"][field].update(maxItems=n)
    p = Pipeline()
    p.add_component("prompt", ChatPromptBuilder(template=[ChatMessage.from_system(spec["system"]),
                                                          ChatMessage.from_user(spec["user"])]))
    p.add_component("llm", generator(role, config.load()["llm"], spec.get("schema")))
    p.connect("prompt.prompt", "llm.messages")
    return p


def _ask_json(pipe: Pipeline, variables: dict, list_key: str = "items") -> tuple[dict, str]:
    """Run a prompt pipeline and parse its JSON answer.

    If the answer is not valid JSON, the model gets its own answer and the parser error back and is asked to fix it
    (repeating the same request would return the same broken answer at temperature 0).
    """
    messages = pipe.get_component("prompt").run(**variables)["prompt"]
    llm = pipe.get_component("llm")
    last = ""
    for _ in range(config.load()["llm"].get("json_attempts", 2)):
        last = llm.run(messages=messages)["replies"][0].text or ""
        try:
            return parse_json(last, list_key), last
        except (ValueError, json.JSONDecodeError) as e:
            messages = messages + [
                ChatMessage.from_assistant(last),
                ChatMessage.from_user(f"Your answer is not valid JSON ({e}). Reply again with the same content as "
                                      "valid JSON only, in exactly the requested shape."),
            ]
    raise ValueError(f"model answer is not valid JSON: {last[:300]}")


# ---------- B2 ----------
def search_terms(buzzwords: list[str], mode: str) -> list[dict]:
    """B2: what the search embeds per buzzword. 'apertus': hypothetical passages (HyDE), 'direct': the buzzword.

    One Apertus call per buzzword, run in parallel: small tasks are far more reliable for the 8B model.
    """
    if mode == "direct":
        return [{"buzzword": b, "terms": [b]} for b in buzzwords]
    n = config.load()["queries"]["passages_per_buzzword"]

    def one(buzzword: str) -> dict:
        data, _ = _ask_json(_prompt_pipeline("queries", "queries", {"passages": n}),
                            {"buzzword": buzzword, "n": n}, "passages")
        texts = data.get("passages") or [] if data.get("searchable", True) else []
        return {"buzzword": buzzword, "terms": [t.strip() for t in texts if isinstance(t, str) and t.strip()][:n]}

    with ThreadPoolExecutor(max_workers=min(8, len(buzzwords) or 1)) as pool:
        return list(pool.map(one, buzzwords))


# ---------- B4 ----------
def page_documents(page_ids: list[str]) -> list[Document]:
    """B4.1 + B4.2: full page texts in ranked order, then best pages at the beginning and the end of the prompt."""
    db = sqlite3.connect(INDEX_DB)
    docs = []
    for rank, pid in enumerate(page_ids):
        row = db.execute("SELECT url, title, website, content FROM pages WHERE id = ?", (pid,)).fetchone()
        if row:
            docs.append(Document(id=pid, content=row[3], score=1.0 / (rank + 1),
                                 meta={"url": row[0], "title": row[1], "website": row[2]}))
    return LostInTheMiddleRanker().run(documents=docs)["documents"]


def compose(buzzwords: list[str], docs: list[Document]) -> tuple[list[dict], str]:
    cfg = config.load()["brief"]
    data, raw = _ask_json(_prompt_pipeline("brief", "brief", max_items={"items": cfg["max_items"]}),
                          {"buzzwords": buzzwords, "pages": docs, "language": cfg["language"],
                           "max_items": cfg["max_items"]})
    return data.get("items", [])[:cfg["max_items"]], raw


# ---------- B5 ----------
def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def _name_on_page(name: str, page_norm: str) -> bool:
    tokens = [t for t in _norm(name).split() if t not in TITLES]
    if not tokens:
        return False
    words = set(page_norm.split())
    long = [t for t in tokens if len(t) > 1]
    if all(t in words for t in long):          # every name part appears, any order ("Muster, Anna")
        return True
    surname, given = long[-1] if long else tokens[-1], tokens[0]
    return surname in words and (given in words or bool(re.search(rf"\b{given[0]}\b", page_norm)))


EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?:\+|00)?\d[\d\s./()-]{7,}\d")


def _emails(text: str) -> set[str]:
    """Email addresses on a page, including the usual obfuscations "name(at)unibe.ch", "name [at] unibe [dot] ch"."""
    text = re.sub(r"\s*[\(\[]\s*at\s*[\)\]]\s*", "@", text, flags=re.I)
    text = re.sub(r"\s*[\(\[]\s*dot\s*[\)\]]\s*", ".", text, flags=re.I)
    return {e.lower().rstrip(".") for e in EMAIL.findall(text)}


def _phone_key(phone: str) -> str:
    """Digits only, Swiss international prefix written as the national 0: "+41 (0)31 684 11 11" -> "0316841111"."""
    digits = re.sub(r"[^\d+]", "", phone.replace("(0)", ""))
    return re.sub(r"^(?:\+|00)41", "0", digits)


def _phones(text: str) -> set[str]:
    return {k for k in (_phone_key(m) for m in PHONE.findall(text)) if len(k) >= 9}


def _contact_fields(c: dict, pages: list[str], flags: list[str]) -> dict:
    """Keep email and phone only if they are written on a cited page; anything else goes into the flags."""
    c = {k: v.strip() for k, v in c.items() if isinstance(v, str) and v.strip()}
    if "email" in c and not any(c["email"].lower() in _emails(p) for p in pages):
        flags.append(f"email of {c['name']} not found in the source, removed")
        del c["email"]
    if "phone" in c and not any(_phone_key(c["phone"]) in _phones(p) for p in pages):
        flags.append(f"phone number of {c['name']} not found in the source, removed")
        del c["phone"]
    return c


def check(items: list[dict], docs: list[Document], searcher: Searcher) -> tuple[list[dict], list[dict]]:
    cfg = config.load()["check"]
    pages_norm = [_norm(d.content or "") for d in docs]
    kept, dropped = [], []
    for item in items:
        reasons = []
        srcs = [s for s in item.get("sources", []) if isinstance(s, int) and 1 <= s <= len(docs)]
        if not srcs:
            reasons.append("no valid source")
        evidence = _norm(item.get("evidence") or "")
        if srcs and evidence:
            score = max(fuzz.partial_ratio(evidence, pages_norm[s - 1]) for s in srcs)
            if score < cfg["evidence_min_ratio"]:
                reasons.append(f"quote not found in the source ({score:.0f}%)")
        elif srcs:
            reasons.append("no quote")
        if reasons:
            dropped.append({"item": item, "reasons": reasons})
            continue

        flags, contacts, removed = [], [], []
        for c in item.get("contacts") or []:
            name = (c or {}).get("name", "")
            if name and any(_name_on_page(name, pages_norm[s - 1]) for s in srcs):
                contacts.append(_contact_fields(c, [docs[s - 1].content or "" for s in srcs], flags))
            else:
                removed.append(c)

        facts = []
        for f in item.get("facts") or []:
            if not isinstance(f, str) or not f.strip():
                continue
            if max(fuzz.partial_ratio(_norm(f), pages_norm[s - 1]) for s in srcs) >= cfg["evidence_min_ratio"]:
                facts.append(f.strip())
            else:
                flags.append(f"fact not found in the source, removed: «{f.strip()}»")

        sim = float(searcher.embed(item.get("summary", "")) @ searcher.embed(item.get("evidence", "")))
        if sim < cfg["summary_min_similarity"]:
            flags.append(f"summary differs from the quote ({sim:.2f})")
        kept.append({
            "title": item.get("title", ""), "category": item.get("category", ""),
            "organisation": item.get("organisation", ""), "summary": item.get("summary", ""),
            "relevance": item.get("relevance", ""), "facts": facts, "evidence": item.get("evidence", ""),
            "sources": [{"url": docs[s - 1].meta["url"], "title": docs[s - 1].meta["title"],
                         "website": docs[s - 1].meta["website"]} for s in srcs],
            "contacts": contacts, "contacts_removed": removed, "flags": flags,
        })
    return kept, dropped


def page_dict(p: Page) -> dict:
    return {k: v for k, v in asdict(p).items() if k != "_embedding"}


def write_trace(trace: dict) -> str:
    TRACES.mkdir(parents=True, exist_ok=True)
    path = TRACES / f"{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}.json"
    path.write_text(json.dumps(trace, ensure_ascii=False, indent=2, default=str))
    return str(path.relative_to(ROOT))


# ---------- B4–B6 for given pages ----------
def brief(buzzwords: list[str], page_ids: list[str], searcher: Searcher, context: dict | None = None) -> dict:
    """Compose and check pitch information from the selected pages (ranked order). Writes a trace."""
    t0 = time.time()
    trace = {**(context or {}), "buzzwords": buzzwords, "page_ids": page_ids,
             "prompt_versions": {n: yaml.safe_load((PROMPTS / f"{n}.yaml").read_text(encoding="utf-8"))["version"]
                                 for n in ("queries", "brief")}}
    result = {"items": [], "dropped": []}
    if not page_ids:
        result["status"] = "no_results"
    else:
        docs = page_documents(page_ids)
        trace["prompt_page_order"] = [d.meta["url"] for d in docs]
        items, raw = compose(buzzwords, docs)
        trace["llm_answer"] = raw
        kept, dropped = check(items, docs, searcher)
        result.update(items=kept, dropped=dropped, status="ok" if kept else "insufficient_evidence")
    result["took_s"] = round(time.time() - t0, 1)
    result["trace"] = write_trace({**trace, "result": result})
    return result


# ---------- whole run (CLI) ----------
def run(buzzwords: list[str], mode: str = "apertus", searcher: Searcher | None = None, **search_args) -> dict:
    t0 = time.time()
    searcher = searcher or Searcher()
    queries = search_terms(buzzwords, mode)
    terms = list(dict.fromkeys(t for q in queries for t in q["terms"]))
    pages = [page_dict(p) for p in searcher.search(terms, **search_args)] if terms else []
    context = {"mode": mode, "queries": queries, "search": {**config.load()["search"], **search_args}, "pages": pages}
    result = brief(buzzwords, [p["page_id"] for p in pages], searcher, context)
    return {"buzzwords": buzzwords, "queries": queries, "pages": pages, **result, "took_s": round(time.time() - t0, 1)}


def main():
    ap = argparse.ArgumentParser(description="Pipeline 2 end-to-end test")
    ap.add_argument("buzzwords", nargs="+")
    ap.add_argument("--mode", choices=["direct", "apertus"], default="apertus")
    ap.add_argument("--top-n", type=int)
    args = ap.parse_args()
    r = run(args.buzzwords, args.mode, top_n=args.top_n)
    print(f"Suchbegriffe: {[t for q in r['queries'] for t in q['terms']]}")
    print(f"{len(r['pages'])} Seiten · Status {r['status']} · {len(r['items'])} Punkte, "
          f"{len(r['dropped'])} gestrichen · {r['took_s']} s · Protokoll {r['trace']}\n")
    for i, it in enumerate(r["items"], 1):
        print(f"{i}. [{it['category']}] {it['title']}\n   {it['summary']}\n   Zitat: «{it['evidence'][:200]}»")
        for c in it["contacts"]:
            print(f"   Kontakt: {c.get('name')} ({c.get('role', '')})")
        for s in it["sources"]:
            print(f"   Quelle: {s['url']}")
        for f in it["flags"]:
            print(f"   ! {f}")
        print()
    for d in r["dropped"]:
        print(f"gestrichen: {d['item'].get('title')} – {', '.join(d['reasons'])}")


if __name__ == "__main__":
    main()
