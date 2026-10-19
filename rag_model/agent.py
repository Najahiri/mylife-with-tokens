"""Agent: Apertus (model "agent") orchestrates the request in a chat, with the pipeline steps as tools.

    search(passages)      B3 search; the agent writes the hypothetical passages itself (replaces B2)
    read_pages(pages)     full page texts (B4.1)
    add_items(items)      the agent composes the items itself (replaces B4.3); B5 checks them, accepted ones
                          join the list, the reasons for rejected ones go back to the agent
    remove_items(titles)  takes items off the list (e.g. when the user asks); they go to the trash
    restore_items(titles)            brings items back from the trash, unchanged (they were checked already)
    edit_item(title, changes)        changes one item as the user asks; never refused, what the source does not
                                     back is marked on the item
    update_presentation(...)         title-slide texts and which extra slides are shown

The current presentation (settings and every item) is part of the system prompt at every step, so the agent
can edit what the user sees.

A text answer without a tool call ends the turn, unless the agent has searched or read since it last added
items: then it is reminded, and the next step is forced to be the call that naturally follows (read_pages
after a search, add_items after reading; named tool choice, so the server generates the call and holds it to
the tool's schema). At most `NUDGES` times per message.
An identical repeated tool call is not run again.

Apertus sometimes writes its reasoning into the text, ended by <|inner_suffix|>, or a tool call in its raw
format (<|tools_prefix|>[...]<|tools_suffix|>) that the server's parser missed: `_clean` separates the reasoning
and turns raw tool calls into real ones.

Items the user deletes in the UI are taken off the list and the agent is told with the next message.

One Session per conversation, saved to data/sessions/<id>.json after every message and deletion, so a restart
of the API keeps the conversations. `turn()` runs one user message until the agent answers in text, and yields
events for the UI as it goes. Every page and tool result stays in the conversation (no pruning).
"""
import json
import re
import sqlite3
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from typing import Iterator

import yaml
from haystack import Document
from haystack.dataclasses import ChatMessage, ToolCall
from haystack.tools import Tool
from jinja2 import Template
from rapidfuzz import fuzz

from rag_model import config
from rag_model.brief import INDEX_DB, PROMPTS, _name_on_page, _norm, check, write_trace
from rag_model.llm import generator
from rag_model.presentation import DECK, category
from rag_model.search import ROOT, Searcher

SESSIONS = ROOT / "data" / "sessions"

CHANGES = ("add_items", "remove_items", "restore_items", "edit_item", "update_presentation")   # tools that change what the user sees
NUDGES = 3
CUT_OFF = ("Your last answer was cut off at the length limit. Work in smaller steps: add at most 5 items per "
           "add_items call, and keep your text short.")
NUDGE = {"read_pages": "Continue: read the relevant pages from the search results with read_pages now.",
         "add_items": "Continue: add the pitch items from the pages you have read with add_items now."}


def _force(tool: str) -> dict:
    return {"generation_kwargs": {"tool_choice": {"type": "function", "function": {"name": tool}}}}


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    messages: list[ChatMessage] = field(default_factory=list)
    pages: list[dict] = field(default_factory=list)      # page number = index + 1
    read: set[int] = field(default_factory=set)
    items: list[dict] = field(default_factory=list)      # the accepted list the user sees
    dropped: list[dict] = field(default_factory=list)    # rejected in the last add_items
    rejections: dict[str, int] = field(default_factory=dict)   # title -> times rejected
    notes: list[str] = field(default_factory=list)       # for the agent with the next message (e.g. user deletions)
    deck: dict = field(default_factory=lambda: dict(DECK))   # presentation settings, edited in the UI and by the agent
    trash: list[dict] = field(default_factory=list)      # removed items, can be restored
    events: list[dict] = field(default_factory=list)     # everything the UI shows, in order

    def number(self, page_id: str) -> int | None:
        return next((i + 1 for i, p in enumerate(self.pages) if p["page_id"] == page_id), None)

    def save(self) -> None:
        SESSIONS.mkdir(parents=True, exist_ok=True)
        data = {"id": self.id, "messages": [m.to_dict() for m in self.messages], "pages": self.pages,
                "read": sorted(self.read), "items": self.items, "dropped": self.dropped,
                "rejections": self.rejections, "notes": self.notes, "deck": self.deck, "trash": self.trash,
                "events": self.events}
        tmp = SESSIONS / f"{self.id}.json.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, default=str))
        tmp.replace(SESSIONS / f"{self.id}.json")

    @classmethod
    def load(cls, path) -> "Session":
        d = json.loads(path.read_text())
        return cls(id=d["id"], messages=[ChatMessage.from_dict(m) for m in d["messages"]], pages=d["pages"],
                   read=set(d["read"]), items=d["items"], dropped=d["dropped"], rejections=d.get("rejections", {}),
                   notes=d.get("notes", []), deck={**DECK, **d.get("deck", {})}, trash=d.get("trash", []),
                   events=d["events"])

    def view(self) -> dict:
        return {"id": self.id, "events": self.events, "pages": self.pages, "read": sorted(self.read),
                "items": self.items, "dropped": self.dropped, "deck": self.deck}


def _spec() -> dict:
    return yaml.safe_load((PROMPTS / "agent.yaml").read_text(encoding="utf-8"))


def _item_schema(max_items: int) -> dict:
    brief = yaml.safe_load((PROMPTS / "brief.yaml").read_text(encoding="utf-8"))
    return {**brief["schema"]["properties"]["items"], "maxItems": max_items}


def _tools(max_items: int) -> list[Tool]:
    d = _spec()["tools"]
    noop = lambda **_: None   # we run the tools ourselves, see _run_tool
    return [
        Tool("search", d["search"], {"type": "object", "required": ["passages"], "properties": {
            "passages": {"type": "array", "items": {"type": "string"}, "minItems": 1}}}, noop),
        Tool("read_pages", d["read_pages"], {"type": "object", "required": ["pages"], "properties": {
            "pages": {"type": "array", "items": {"type": "integer"}, "minItems": 1}}}, noop),
        Tool("add_items", d["add_items"], {"type": "object", "required": ["items"], "properties": {
            "items": _item_schema(max_items)}}, noop),
        Tool("remove_items", d["remove_items"], {"type": "object", "required": ["titles"], "properties": {
            "titles": {"type": "array", "items": {"type": "string"}, "minItems": 1}}}, noop),
        Tool("restore_items", d["restore_items"], {"type": "object", "required": ["titles"], "properties": {
            "titles": {"type": "array", "items": {"type": "string"}, "minItems": 1}}}, noop),
        Tool("edit_item", d["edit_item"], {"type": "object", "required": ["title", "changes"], "properties": {
            "title": {"type": "string"},
            "changes": {"type": "object", "properties": {k: v for k, v in _item_schema(max_items)["items"]["properties"].items()
                                                         if k in EDITABLE}}}}, noop),
        Tool("update_presentation", d["update_presentation"], {"type": "object", "properties": {
            "company": {"type": "string"}, "subtitle": {"type": "string"}, "label_above_title": {"type": "string"},
            "speaker": {"type": "string"}, "organisation": {"type": "string"},
            "overview_slide": {"type": "boolean"}, "contacts_slide": {"type": "boolean"}}}, noop),
    ]


# ---------- tools ----------
def _search(s: Session, searcher: Searcher, passages: list[str]) -> tuple[str, dict]:
    terms = list(dict.fromkeys(p.strip() for p in passages if isinstance(p, str) and p.strip()))
    found = searcher.search(terms) if terms else []
    lines = []
    for p in found:
        n = s.number(p.page_id)
        if n is None:
            s.pages.append({"page_id": p.page_id, "url": p.url, "title": p.title, "website": p.website,
                            "similarity": round(p.similarity, 3), "snippet": p.snippet})
            n = len(s.pages)
        seen = " (already read)" if n in s.read else ""
        excerpt = textwrap.shorten(" ".join(p.snippet.split()), 320, placeholder=" …")
        lines.append(f"[{n}] {p.website} · {p.title}{seen}\n    {p.url}\n    best match ({p.similarity:.2f}): {excerpt}")
    text = f"{len(found)} pages, best first:\n" + "\n".join(lines) if found else "No pages found. Try other passages."
    return text, {"passages": terms, "pages": [_page_info(s, s.number(p.page_id)) for p in found]}


def _page_info(s: Session, n: int) -> dict:
    p = s.pages[n - 1]
    return {"n": n, "title": p["title"], "website": p["website"], "url": p["url"], "similarity": p["similarity"]}


def _page_text(page_id: str) -> str:
    with sqlite3.connect(INDEX_DB) as db:
        row = db.execute("SELECT content FROM pages WHERE id = ?", (page_id,)).fetchone()
    return row[0] if row else ""


def _read_pages(s: Session, pages: list[int]) -> tuple[str, dict]:
    out, new = [], []
    for n in dict.fromkeys(pages):
        if not isinstance(n, int) or not 1 <= n <= len(s.pages):
            out.append(f"[Page {n}] does not exist. Use the numbers from the search results.")
        elif n in s.read:
            out.append(f"[Page {n}] already read above.")
        else:
            p = s.pages[n - 1]
            out.append(f"[Page {n}] {p['website']} · {p['title']}\nURL: {p['url']}\n{_page_text(p['page_id'])}")
            s.read.add(n)
            new.append(n)
    return "\n\n".join(out), {"pages": [_page_info(s, n) for n in new]}


def _normalize(item: dict) -> tuple[dict, list[str]]:
    """Read the item leniently ("Page 4" -> 4, contacts as plain strings) and name what is missing."""
    item, problems = dict(item), []
    item["category"] = category(str(item.get("category", "")))
    raw = item.get("sources")
    raw = raw if isinstance(raw, list) else [raw] if raw not in (None, "") else []
    item["sources"] = [int(m) for r in raw for m in re.findall(r"\d+", str(r))]
    if not item["sources"]:
        problems.append('missing "sources": the numbers of the pages it is based on, e.g. "sources": [4, 12]')
    if not str(item.get("evidence") or "").strip():
        problems.append('missing "evidence": one sentence copied word for word from a cited page')
    contacts = []
    for c in item.get("contacts") or []:
        if isinstance(c, dict) and c.get("name"):
            contacts.append(c)
        elif isinstance(c, str) and c.strip():
            c = c.strip()
            key = "email" if "@" in c else "phone" if sum(ch.isdigit() for ch in c) >= 7 else None
            if key and contacts:
                contacts[-1].setdefault(key, c)
            elif not key:
                contacts.append({"name": c})
    item["contacts"] = contacts
    return item, problems


def _titles(s: Session) -> str:
    return "; ".join(f"«{i['title']}»" for i in s.items) or "empty"


def _add(s: Session, searcher: Searcher, items: list[dict], max_items: int) -> tuple[str, dict]:
    malformed, valid = [], []
    for item, problems in map(_normalize, [i for i in items if isinstance(i, dict)]):
        (malformed if problems else valid).append({"item": item, "reasons": problems} if problems else item)
    docs = [Document(id=p["page_id"], content=_page_text(p["page_id"]),
                     meta={"url": p["url"], "title": p["title"], "website": p["website"]}) for p in s.pages]
    kept, dropped = check(valid, docs, searcher)
    dropped = malformed + dropped
    new_titles = {k["title"].strip().lower() for k in kept}
    s.items = [i for i in s.items if i["title"].strip().lower() not in new_titles]   # same title: replaced
    room = max(0, max_items - len(s.items))
    full = kept[room:]
    s.items += kept[:room]
    s.dropped = dropped
    lines = [f"{len(kept) - len(full)} of {len(kept) + len(dropped)} items added. "
             f"The list the user sees now has {len(s.items)}: {_titles(s)}."]
    if full:
        lines.append(f"{len(full)} accepted items were not added because the list is full ({max_items}); "
                     "remove less relevant items first if they matter more.")
    min_ratio = config.load()["check"]["evidence_min_ratio"]
    for d in dropped:
        title = str(d["item"].get("title", ""))
        s.rejections[title.strip().lower()] = s.rejections.get(title.strip().lower(), 0) + 1
        hint = ""
        if any(r.startswith("quote not found") for r in d["reasons"]):
            # the quote may be real but cited with the wrong page number: say where it is, the agent fixes it
            quote = _norm(d["item"].get("evidence") or "")
            found = [n for n in sorted(s.read) if fuzz.partial_ratio(quote, _norm(docs[n - 1].content or "")) >= min_ratio]
            hint = (f" The quote is on page {', '.join(map(str, found))}: cite that page." if found
                    else " It is on none of the pages you have read.")
        if s.rejections[title.strip().lower()] >= 2:
            hint += " Rejected twice now: leave this item out."
        lines.append(f"Rejected «{title}»: {'; '.join(d['reasons'])}.{hint}")
    for k in kept:
        notes = k["flags"] + [f"contact {c.get('name')} is not named on the cited pages, removed"
                              for c in k["contacts_removed"]]
        if notes:   # the item itself was added: say so, models read these notes as a rejection otherwise
            lines.append(f"«{k['title']}» is on the list. Only these details were left out: {'; '.join(notes)}.")
    if dropped:
        lines.append("To fix a rejected item, copy its quote word for word from a cited page and add only that "
                     "item again. Otherwise leave it out.")
    return "\n".join(lines), {"added": len(kept) - len(full), "rejected": len(dropped)}


def _take(s: Session, titles: list[str]) -> list[dict]:
    """Move the items with these titles from the list to the trash; returns them."""
    found = {i for i in (_find(s, t) for t in titles) if i is not None}
    gone = [it for n, it in enumerate(s.items) if n in found]
    s.items = [it for n, it in enumerate(s.items) if n not in found]
    s.trash = [t for t in s.trash if t["title"] not in {g["title"] for g in gone}] + gone
    return gone


def _remove(s: Session, titles: list[str]) -> tuple[str, dict]:
    gone = _take(s, titles)
    return (f"{len(gone)} items removed (they can be restored with restore_items). "
            f"The list now has {len(s.items)}: {_titles(s)}.", {"removed": len(gone)})


def _restore(s: Session, titles: list[str], max_items: int) -> tuple[str, dict]:
    back = []
    for t in titles:
        scored = [(fuzz.ratio(str(t).strip().lower(), it["title"].strip().lower()), n) for n, it in enumerate(s.trash)]
        score, n = max(scored, default=(0, None))
        if n is not None and score >= 80 and len(s.items) < max_items:
            back.append(s.trash.pop(n))
            s.items.append(back[-1])
    missing = len(titles) - len(back)
    return (f"{len(back)} items restored. The list now has {len(s.items)}: {_titles(s)}."
            + (f" {missing} not restored: not in the trash or the list is full." if missing else ""),
            {"restored": len(back)})


EDITABLE = ("title", "category", "organisation", "summary", "relevance", "facts", "contacts", "evidence")
DECK_ARGS = {"company": "company", "subtitle": "subtitle", "label_above_title": "kicker", "speaker": "author",
             "organisation": "organizer", "overview_slide": "overview", "contacts_slide": "contacts_slide"}


def _find(s: Session, title: str) -> int | None:
    t = str(title).strip().lower()
    exact = [i for i, it in enumerate(s.items) if it["title"].strip().lower() == t]
    if exact:
        return exact[0]
    scored = [(fuzz.ratio(t, it["title"].strip().lower()), i) for i, it in enumerate(s.items)]
    best = max(scored, default=(0, None))
    return best[1] if best[0] >= 80 else None


def _edit(s: Session, title: str, changes: dict) -> tuple[str, dict]:
    """Change one item as the user asks. The user has the last word: nothing is refused. What the source pages do
    not back (facts, contacts, quote) is marked on the item, so the evidence view shows it."""
    i = _find(s, title)
    if i is None:
        return f"There is no item «{title}». The items are: {_titles(s)}.", {}
    old = s.items[i]
    changes = {k: v for k, v in (changes or {}).items() if k in EDITABLE and v is not None}
    if not changes:
        return f"Nothing to change in «{old['title']}»: give the fields to change in \"changes\".", {}
    if "category" in changes:
        changes["category"] = category(str(changes["category"]))
    if "contacts" in changes:
        changes["contacts"] = _normalize({"contacts": changes["contacts"]})[0]["contacts"]
    if "facts" in changes:
        changes["facts"] = [str(f).strip() for f in changes["facts"] or [] if str(f).strip()]
    new_title = str(changes.get("title", old["title"])).strip()
    if any(j != i and it["title"].strip().lower() == new_title.lower() for j, it in enumerate(s.items)):
        return f"«{old['title']}» not changed: another item is already titled «{new_title}».", {}

    by_url = {p["url"]: p["page_id"] for p in s.pages}
    pages = [_norm(_page_text(by_url[src["url"]])) for src in old["sources"] if src["url"] in by_url]
    min_ratio = config.load()["check"]["evidence_min_ratio"]
    on_page = lambda text: any(fuzz.partial_ratio(_norm(text), p) >= min_ratio for p in pages)
    unbacked = [f"fact «{f}»" for f in changes.get("facts", []) if not on_page(f)]
    unbacked += [f"contact {c['name']}" for c in changes.get("contacts", []) if not any(_name_on_page(c["name"], p) for p in pages)]
    if "evidence" in changes and not on_page(str(changes["evidence"])):
        unbacked.append("quote")

    item = {**old, **changes, "title": new_title}
    item["edited"] = sorted(set(old.get("edited", [])) | set(changes))
    item["unbacked"] = list(dict.fromkeys(old.get("unbacked", []) + unbacked))
    note = f"changed on request: {', '.join(item['edited'])}"
    if item["unbacked"]:
        note += f"; not in the source: {', '.join(item['unbacked'])}"
    item["flags"] = [f for f in old.get("flags", []) if not f.startswith("changed on request")] + [note]
    s.items[i] = item
    return (f"«{old['title']}» updated" + (f" (now «{new_title}»)" if new_title != old["title"] else "") + "."
            + (f" Not backed by the source pages, marked for the user: {', '.join(unbacked)}." if unbacked else "")
            ), {"edited": new_title}


def _update_deck(s: Session, args: dict) -> tuple[str, dict]:
    changed = {DECK_ARGS[k]: v for k, v in args.items() if k in DECK_ARGS and v is not None}
    s.deck.update(changed)
    return f"Presentation updated: {', '.join(changed) or 'nothing'}.", {"changed": sorted(changed)}


def _state(s: Session) -> str:
    """The presentation as the user sees it now, for the system prompt."""
    d = s.deck
    lines = ["", "The presentation the user sees now:",
             f"- title slide: company «{d['company'] or '(not set)'}», subtitle «{d['subtitle'] or '(default)'}», "
             f"label above the title «{d['kicker'] or '(default)'}», speaker «{d['author']}», organisation «{d['organizer']}»",
             f"- overview slide «at a glance» (table of contents): {'shown' if d['overview'] else 'hidden'}; "
             f"contacts slide: {'shown' if d['contacts_slide'] else 'hidden'}. These two are not items: show or hide "
             f"them with update_presentation (overview_slide, contacts_slide true/false).",
             f"- {len(s.items)} item slides:" if s.items else "- no item slides yet"]
    if s.trash:
        lines.append(f"- removed earlier (bring back with restore_items): {'; '.join(f'«{t['title']}»' for t in s.trash)}")
    for n, it in enumerate(s.items, 1):
        contacts = ", ".join(c.get("name", "") for c in it.get("contacts") or []) or "none"
        lines.append(f"  {n}. «{it['title']}» [{it.get('category', '')}] {it.get('organisation', '')} | summary: "
                     f"{it.get('summary', '')} | relevance: {it.get('relevance', '')} | facts: "
                     f"{'; '.join(it.get('facts') or []) or 'none'} | contacts: {contacts}")
    return "\n".join(lines)


def _run_tool(s: Session, searcher: Searcher, name: str, args: dict, max_items: int) -> tuple[str, dict]:
    if name == "search":
        return _search(s, searcher, args.get("passages") or [])
    if name == "read_pages":
        return _read_pages(s, args.get("pages") or [])
    if name == "add_items":
        return _add(s, searcher, args.get("items") or [], max_items)
    if name == "remove_items":
        return _remove(s, args.get("titles") or [])
    if name == "restore_items":
        return _restore(s, args.get("titles") or [], max_items)
    if name == "edit_item":
        return _edit(s, args.get("title", ""), args.get("changes") or {})
    if name == "update_presentation":
        return _update_deck(s, args)
    raise ValueError(f"unknown tool {name}")


def remove_by_user(s: Session, titles: list[str]) -> None:
    """The user deleted slides in the UI: the items go, the agent learns it with the next message."""
    gone = [g["title"] for g in _take(s, titles)]
    if gone:
        s.notes.append("The user deleted these items from the list. Do not add them again unless the user asks for "
                       "them back, then use restore_items: " + "; ".join(f"«{t}»" for t in gone) + ".")
        s.events.append({"type": "note", "text": "Removed from the presentation: " + ", ".join(gone)})
        s.save()


def load_sessions() -> dict[str, Session]:
    return {s.id: s for s in (Session.load(p) for p in sorted(SESSIONS.glob("*.json")))} if SESSIONS.exists() else {}


# ---------- model output ----------
REASONING_END = "<|inner_suffix|>"
RAW_TOOLS = re.compile(r"<\|tools_prefix\|>(.*?)<\|tools_suffix\|>", re.S)
MARKER = re.compile(r"<\|[a-z_]+\|>")


def _clean(reply: ChatMessage) -> tuple[ChatMessage, str]:
    """Split Apertus' inline reasoning from the answer and recover raw tool calls. Returns (reply, reasoning)."""
    text, reasoning = reply.text or "", ""
    if REASONING_END in text:
        reasoning, text = text.rsplit(REASONING_END, 1)
    calls = list(reply.tool_calls)
    for block in RAW_TOOLS.findall(text):
        try:
            raw = json.loads(block)
        except json.JSONDecodeError:
            continue
        for c in raw if isinstance(raw, list) else [raw]:
            # {"name": ..., "arguments": {...}} or Apertus' own {"tool_name": {...}}
            if isinstance(c, dict) and "name" in c:
                name, args = c["name"], c.get("arguments") or {}
            elif isinstance(c, dict) and len(c) == 1:
                name, args = next(iter(c.items()))
            else:
                continue
            if isinstance(args, str):
                args = json.loads(args)
            calls.append(ToolCall(tool_name=name, arguments=args, id=f"raw-{uuid.uuid4().hex[:8]}"))
    text = MARKER.sub("", RAW_TOOLS.sub("", text)).strip()
    reasoning = MARKER.sub("", reasoning).strip()
    if text == (reply.text or "") and calls == list(reply.tool_calls):
        return reply, ""
    return ChatMessage.from_assistant(text=text or None, tool_calls=calls, meta=reply.meta), reasoning


# ---------- loop ----------
def turn(s: Session, text: str, searcher: Searcher) -> Iterator[dict]:
    """Run one user message. Yields the events the UI shows; they are also kept in s.events."""
    t0 = time.time()
    cfg = config.load()
    max_items, max_steps = cfg["brief"]["max_items"], cfg["agent"]["max_steps"]
    system = Template(_spec()["system"]).render(language=cfg["brief"]["language"], max_items=max_items)
    llm = generator("agent", cfg["llm"], tools=_tools(max_items))
    start = len(s.events)

    def emit(event: dict) -> dict:
        s.events.append(event)
        return event

    notes, s.notes = s.notes, []
    s.messages.append(ChatMessage.from_user("\n".join([*(f"[{n}]" for n in notes), text])))
    yield emit({"type": "user", "text": text})
    answered, nudges = False, 0
    pending = None    # the call that should follow: "read_pages" after a search, "add_items" after reading
    force = None
    done_calls = {json.dumps([c.tool_name, c.arguments], sort_keys=True)
                  for m in s.messages for c in m.tool_calls}
    for _ in range(max_steps):
        # after a reminder the next step is an add_items call; otherwise the model may also plan in text
        prompt = ChatMessage.from_system(system + "\n" + _state(s))
        reply = llm.run(messages=[prompt, *s.messages], **(_force(force) if force else {}))["replies"][0]
        cut_off = reply.meta.get("finish_reason") == "length"
        reply, reasoning = _clean(reply)
        if reasoning:
            yield emit({"type": "assistant", "text": reasoning, "final": False})
        s.messages.append(reply)
        force = None
        if cut_off and nudges < NUDGES:   # a half-written tool call or text: tell it and let it continue
            nudges += 1
            yield emit({"type": "note", "text": "Apertus' answer was too long and was cut off; it continues in smaller steps."})
            s.messages[-1] = ChatMessage.from_assistant(text=(reply.text or "")[:2000] or None, meta=reply.meta)
            s.messages.append(ChatMessage.from_user(CUT_OFF))
            continue
        if not reply.tool_calls:
            if pending and nudges < NUDGES:   # announced the next step in text and stopped
                nudges += 1
                if reply.text and reply.text.strip():
                    yield emit({"type": "assistant", "text": reply.text.strip(), "final": False})
                s.messages.append(ChatMessage.from_user(NUDGE[pending]))
                force = pending
                continue
            yield emit({"type": "assistant", "text": (reply.text or "").strip(), "final": True})
            answered = True
            break
        if reply.text and reply.text.strip():
            yield emit({"type": "assistant", "text": reply.text.strip(), "final": False})
        for call in reply.tool_calls:
            key = json.dumps([call.tool_name, call.arguments], sort_keys=True)
            if key in done_calls:
                s.messages.append(ChatMessage.from_tool(
                    "You already made exactly this call; its result is above. Continue with the next step.", origin=call))
                yield emit({"type": "tool_call", "id": call.id, "name": call.tool_name, "repeated": True,
                            "arguments": {} if call.tool_name == "add_items" else call.arguments})
                continue
            done_calls.add(key)
            if call.tool_name == "search":
                pending = pending or "read_pages"
            elif call.tool_name == "read_pages":
                pending = "add_items"
            elif call.tool_name == "add_items":
                pending = None
            yield emit({"type": "tool_call", "id": call.id, "name": call.tool_name,
                        "arguments": call.arguments if call.tool_name != "add_items"
                        else {"items": len(call.arguments.get("items") or [])}})
            try:
                result, info = _run_tool(s, searcher, call.tool_name, call.arguments, max_items)
                error = False
            except Exception as e:   # the agent sees the error and can react to it
                result, info, error = f"Error: {e}", {}, True
            s.messages.append(ChatMessage.from_tool(result, origin=call, error=error))
            yield emit({"type": "tool_result", "id": call.id, "name": call.tool_name, "error": error,
                        "info": info, "text": result if error or call.tool_name in CHANGES else ""})
            if call.tool_name in CHANGES and not error:
                yield {"type": "items", "items": s.items, "dropped": s.dropped}
                yield {"type": "deck", "deck": s.deck}
    if not answered:
        yield emit({"type": "assistant", "final": True,
                    "text": f"Stopped after {max_steps} steps (Settings → Agent). Ask me to continue if needed."})
    trace = write_trace({"agent_session": s.id, "prompt_version": _spec()["version"], "took_s": round(time.time() - t0, 1),
                         "events": s.events[start:], "pages": s.pages, "items": s.items, "dropped": s.dropped,
                         "messages": [m.to_dict() for m in s.messages]})
    yield emit({"type": "done", "took_s": round(time.time() - t0, 1), "trace": trace})
    s.save()


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Agent test in the terminal (API must be stopped: Qdrant lock)")
    ap.add_argument("message")
    args = ap.parse_args()
    s, searcher = Session(), Searcher()
    for e in turn(s, args.message, searcher):
        print(json.dumps(e, ensure_ascii=False)[:400])


if __name__ == "__main__":
    main()
