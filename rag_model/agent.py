"""Agent: the LLM selects tools; the decision model routes each LLM call to 8B or 70B.

    search(passages)      B3 search; the agent writes the hypothetical passages itself (replaces B2)
    read_pages(pages)     full page texts (B4.1)
    add_items(items)      the agent composes the items itself (replaces B4.3); B5 checks them, accepted ones
                          join the list, the reasons for rejected ones go back to the agent
    remove_items(titles)  takes items off the list (e.g. when the user asks)
    edit_item(title, changes)        changes one item (text, title, category, facts, contacts); checked again
    update_presentation(...)         title-slide texts and which extra slides are shown

The current presentation (settings and every item) is part of the system prompt at every step, so the agent
can edit what the user sees.

Before acting, the LLM assesses whether the current user request needs retrieval.
The LLM chooses its own tools from those eligible for the current state; the separate decision
model chooses 8B or 70B for every LLM call, including assessment, repair and fact checking.
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
import copy
import re
import sqlite3
import textwrap
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Iterator

import yaml
from haystack import Document
from haystack.dataclasses import ChatMessage, ToolCall
from haystack.tools import Tool
from jinja2 import Template
from jsonschema import Draft202012Validator
from rapidfuzz import fuzz

from rag_model import config
from rag_model.brief import INDEX_DB, PROMPTS, _norm, check, write_trace
from rag_model.llm import generator, run_logged
from rag_model.pipeline_log import PipelineTrace, record, set_step
from rag_model.presentation import DECK, category
from rag_model.search import ROOT, Searcher
from rag_model.retrieval import assess_retrieval

SESSIONS = ROOT / "data" / "sessions"

CHANGES = (
    "add_items",
    "remove_items",
    "restore_items",
    "edit_item",
    "update_presentation",
)  # tools that change what the user sees
CUT_OFF = (
    "Your last answer was cut off at the length limit. Work in smaller steps: add at most 5 items per "
    "add_items call, and keep your text short."
)


def _step_tools(tools: list, action: str, s: "Session") -> list | None:
    """Give chat only the selected tool, constrained to the current page state."""
    tool = next((tool for tool in tools if tool.name == action), None)
    if tool is None or not isinstance(getattr(tool, "parameters", None), dict):
        return None
    selected = copy.copy(tool)
    selected.parameters = copy.deepcopy(tool.parameters)
    if action == "read_pages":
        pages = selected.parameters["properties"]["pages"]
        pages["items"]["enum"] = [
            n for n in range(1, len(s.pages) + 1) if n not in s.read
        ]
    elif action == "add_items":
        selected.parameters["properties"]["items"]["items"]["properties"]["sources"][
            "items"
        ]["enum"] = sorted(s.read)
    return [selected]


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    messages: list[ChatMessage] = field(default_factory=list)
    pages: list[dict] = field(default_factory=list)  # page number = index + 1
    read: set[int] = field(default_factory=set)
    items: list[dict] = field(default_factory=list)  # the accepted list the user sees
    dropped: list[dict] = field(default_factory=list)  # rejected in the last add_items
    rejections: dict[str, int] = field(default_factory=dict)  # title -> times rejected
    notes: list[str] = field(
        default_factory=list
    )  # for the agent with the next message (e.g. user deletions)
    deck: dict = field(
        default_factory=lambda: dict(DECK)
    )  # presentation settings, edited in the UI and by the agent
    trash: list[dict] = field(default_factory=list)  # removed items, can be restored
    updated: float = field(
        default_factory=time.time
    )  # last change, for the list of conversations
    stop: threading.Event = field(
        default_factory=threading.Event, repr=False, compare=False
    )  # stop button
    events: list[dict] = field(
        default_factory=list
    )  # everything the UI shows, in order

    def number(self, page_id: str) -> int | None:
        return next(
            (i + 1 for i, p in enumerate(self.pages) if p["page_id"] == page_id), None
        )

    def delete(self) -> None:
        (SESSIONS / f"{self.id}.json").unlink(missing_ok=True)

    def save(self) -> None:
        self.updated = time.time()
        SESSIONS.mkdir(parents=True, exist_ok=True)
        data = {
            "id": self.id,
            "messages": [m.to_dict() for m in self.messages],
            "pages": self.pages,
            "read": sorted(self.read),
            "items": self.items,
            "dropped": self.dropped,
            "rejections": self.rejections,
            "notes": self.notes,
            "deck": self.deck,
            "trash": self.trash,
            "updated": self.updated,
            "events": self.events,
        }
        tmp = SESSIONS / f"{self.id}.json.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, default=str))
        tmp.replace(SESSIONS / f"{self.id}.json")

    @classmethod
    def load(cls, path) -> "Session":
        d = json.loads(path.read_text())
        return cls(
            id=d["id"],
            messages=[ChatMessage.from_dict(m) for m in d["messages"]],
            pages=d["pages"],
            read=set(d["read"]),
            items=d["items"],
            dropped=d["dropped"],
            rejections=d.get("rejections", {}),
            notes=d.get("notes", []),
            deck={**DECK, **d.get("deck", {})},
            trash=d.get("trash", []),
            updated=d.get("updated", path.stat().st_mtime),
            events=d["events"],
        )

    def title(self) -> str:
        """The company if it is set, otherwise the start of the first message."""
        first = next((e["text"] for e in self.events if e["type"] == "user"), "")
        return (
            self.deck.get("company")
            or textwrap.shorten(first, 60, placeholder=" …")
            or "New conversation"
        )

    def summary(self) -> dict:
        return {
            "id": self.id,
            "title": self.title(),
            "updated": self.updated,
            "items": len(self.items),
        }

    def view(self) -> dict:
        return {
            "id": self.id,
            "events": self.events,
            "pages": self.pages,
            "read": sorted(self.read),
            "items": self.items,
            "dropped": self.dropped,
            "deck": self.deck,
        }


def _spec() -> dict:
    return yaml.safe_load((PROMPTS / "agent.yaml").read_text(encoding="utf-8"))


def _item_schema(max_items: int) -> dict:
    brief = yaml.safe_load((PROMPTS / "brief.yaml").read_text(encoding="utf-8"))
    schema = {**brief["schema"]["properties"]["items"], "maxItems": max_items}
    item = schema["items"]
    item["additionalProperties"] = False
    item["properties"]["contacts"]["items"]["additionalProperties"] = False
    item["properties"]["sources"]["minItems"] = 1
    item["properties"]["evidence"]["minLength"] = 1
    return schema


def _tools(max_items: int) -> list[Tool]:
    d = _spec()["tools"]
    noop = lambda **_: None  # we run the tools ourselves, see _run_tool
    return [
        Tool(
            "search",
            d["search"],
            {
                "type": "object",
                "required": ["passages"],
                "properties": {
                    "passages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    }
                },
            },
            noop,
        ),
        Tool(
            "read_pages",
            d["read_pages"],
            {
                "type": "object",
                "required": ["pages"],
                "properties": {
                    "pages": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 1,
                    }
                },
            },
            noop,
        ),
        Tool(
            "add_items",
            d["add_items"],
            {
                "type": "object",
                "required": ["items"],
                "properties": {"items": _item_schema(min(max_items, 5))},
            },
            noop,
        ),
        Tool(
            "remove_items",
            d["remove_items"],
            {
                "type": "object",
                "required": ["titles"],
                "properties": {
                    "titles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    }
                },
            },
            noop,
        ),
        Tool(
            "restore_items",
            d["restore_items"],
            {
                "type": "object",
                "required": ["titles"],
                "properties": {
                    "titles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    }
                },
            },
            noop,
        ),
        Tool(
            "edit_item",
            d["edit_item"],
            {
                "type": "object",
                "required": ["title", "changes"],
                "properties": {
                    "title": {"type": "string"},
                    "changes": {
                        "type": "object",
                        "properties": {
                            k: v
                            for k, v in _item_schema(max_items)["items"][
                                "properties"
                            ].items()
                            if k in EDITABLE
                        },
                    },
                },
            },
            noop,
        ),
        Tool(
            "update_presentation",
            d["update_presentation"],
            {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "subtitle": {"type": "string"},
                    "label_above_title": {"type": "string"},
                    "speaker": {"type": "string"},
                    "organisation": {"type": "string"},
                    "overview_slide": {"type": "boolean"},
                    "contacts_slide": {"type": "boolean"},
                },
            },
            noop,
        ),
    ]


# ---------- tools ----------
def _search(s: Session, searcher: Searcher, passages: list[str]) -> tuple[str, dict]:
    terms = list(
        dict.fromkeys(p.strip() for p in passages if isinstance(p, str) and p.strip())
    )
    found = searcher.search(terms) if terms else []
    lines = []
    for p in found:
        n = s.number(p.page_id)
        if n is None:
            s.pages.append(
                {
                    "page_id": p.page_id,
                    "url": p.url,
                    "title": p.title,
                    "website": p.website,
                    "similarity": round(p.similarity, 3),
                    "snippet": p.snippet,
                }
            )
            n = len(s.pages)
        seen = " (already read)" if n in s.read else ""
        excerpt = textwrap.shorten(" ".join(p.snippet.split()), 320, placeholder=" …")
        lines.append(
            f"[{n}] {p.website} · {p.title}{seen}\n    {p.url}\n    best match ({p.similarity:.2f}): {excerpt}"
        )
    text = (
        f"{len(found)} pages, best first:\n" + "\n".join(lines)
        if found
        else "No pages found. Try other passages."
    )
    return text, {
        "passages": terms,
        "pages": [_page_info(s, s.number(p.page_id)) for p in found],
    }


def _page_info(s: Session, n: int) -> dict:
    p = s.pages[n - 1]
    return {
        "n": n,
        "title": p["title"],
        "website": p["website"],
        "url": p["url"],
        "similarity": p["similarity"],
    }


def _page_text(page_id: str) -> str:
    with sqlite3.connect(INDEX_DB) as db:
        row = db.execute(
            "SELECT content FROM pages WHERE id = ?", (page_id,)
        ).fetchone()
    return row[0] if row else ""


def _read_pages(s: Session, pages: list[int]) -> tuple[str, dict]:
    out, new = [], []
    for n in dict.fromkeys(pages):
        if not isinstance(n, int) or not 1 <= n <= len(s.pages):
            out.append(
                f"[Page {n}] does not exist. Use the numbers from the search results."
            )
        elif n in s.read:
            out.append(f"[Page {n}] already read above.")
        else:
            p = s.pages[n - 1]
            out.append(
                f"[Page {n}] {p['website']} · {p['title']}\nURL: {p['url']}\n{_page_text(p['page_id'])}"
            )
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
        problems.append(
            'missing "sources": the numbers of the pages it is based on, e.g. "sources": [4, 12]'
        )
    if not str(item.get("evidence") or "").strip():
        problems.append(
            'missing "evidence": one sentence copied word for word from a cited page'
        )
    contacts = []
    for c in item.get("contacts") or []:
        if isinstance(c, dict) and c.get("name"):
            contacts.append(c)
        elif isinstance(c, str) and c.strip():
            c = c.strip()
            key = (
                "email"
                if "@" in c
                else "phone"
                if sum(ch.isdigit() for ch in c) >= 7
                else None
            )
            if key and contacts:
                contacts[-1].setdefault(key, c)
            elif not key:
                contacts.append({"name": c})
    item["contacts"] = contacts
    return item, problems


def _titles(s: Session) -> str:
    return "; ".join(f"«{i['title']}»" for i in s.items) or "empty"


def _add(
    s: Session, searcher: Searcher, items: list[dict], max_items: int
) -> tuple[str, dict]:
    malformed, valid = [], []
    for item, problems in map(_normalize, [i for i in items if isinstance(i, dict)]):
        (malformed if problems else valid).append(
            {"item": item, "reasons": problems} if problems else item
        )
    docs = [
        Document(
            id=p["page_id"],
            content=_page_text(p["page_id"]),
            meta={"url": p["url"], "title": p["title"], "website": p["website"]},
        )
        for p in s.pages
    ]
    kept, dropped = check(valid, docs, searcher)
    dropped = malformed + dropped
    new_titles = {k["title"].strip().lower() for k in kept}
    s.items = [
        i for i in s.items if i["title"].strip().lower() not in new_titles
    ]  # same title: replaced
    room = max(0, max_items - len(s.items))
    full = kept[room:]
    s.items += kept[:room]
    s.dropped = dropped
    lines = [
        f"{len(kept) - len(full)} of {len(kept) + len(dropped)} items added. "
        f"The list the user sees now has {len(s.items)}: {_titles(s)}."
    ]
    if full:
        lines.append(
            f"{len(full)} accepted items were not added because the list is full ({max_items}); "
            "remove less relevant items first if they matter more."
        )
    min_ratio = config.load()["check"]["evidence_min_ratio"]
    for d in dropped:
        title = str(d["item"].get("title", ""))
        s.rejections[title.strip().lower()] = (
            s.rejections.get(title.strip().lower(), 0) + 1
        )
        hint = ""
        if any(r.startswith("quote not found") for r in d["reasons"]):
            # the quote may be real but cited with the wrong page number: say where it is, the agent fixes it
            quote = _norm(d["item"].get("evidence") or "")
            found = [
                n
                for n in sorted(s.read)
                if fuzz.partial_ratio(quote, _norm(docs[n - 1].content or ""))
                >= min_ratio
            ]
            hint = (
                f" The quote is on page {', '.join(map(str, found))}: cite that page."
                if found
                else " It is on none of the pages you have read."
            )
        if s.rejections[title.strip().lower()] >= 2:
            hint += " Rejected twice now: leave this item out."
        lines.append(f"Rejected «{title}»: {'; '.join(d['reasons'])}.{hint}")
    for k in kept:
        notes = k["flags"] + [
            f"contact {c.get('name')} is not named on the cited pages, removed"
            for c in k["contacts_removed"]
        ]
        if notes:
            lines.append(f"«{k['title']}»: {'; '.join(notes)}.")
    if dropped:
        lines.append(
            "To fix a rejected item, copy its quote word for word from a cited page and add only that "
            "item again. Otherwise leave it out."
        )
    return "\n".join(lines), {"added": len(kept) - len(full), "rejected": len(dropped)}


def _remove(s: Session, titles: list[str]) -> tuple[str, dict]:
    gone = _take(s, titles)
    return (
        f"{len(gone)} items removed (they can be restored with restore_items). "
        f"The list now has {len(s.items)}: {_titles(s)}.",
        {"removed": len(gone)},
    )


EDITABLE = (
    "title",
    "category",
    "organisation",
    "summary",
    "relevance",
    "facts",
    "contacts",
    "evidence",
)
DECK_ARGS = {
    "company": "company",
    "subtitle": "subtitle",
    "label_above_title": "kicker",
    "speaker": "author",
    "organisation": "organizer",
    "overview_slide": "overview",
    "contacts_slide": "contacts_slide",
}


def _find(s: Session, title: str) -> int | None:
    t = str(title).strip().lower()
    exact = [i for i, it in enumerate(s.items) if it["title"].strip().lower() == t]
    if exact:
        return exact[0]
    scored = [
        (fuzz.ratio(t, it["title"].strip().lower()), i) for i, it in enumerate(s.items)
    ]
    best = max(scored, default=(0, None))
    return best[1] if best[0] >= 80 else None


def _edit(s: Session, title: str, changes: dict) -> tuple[str, dict]:
    """Change one item as the user asks. The user has the last word: nothing is refused. What the source pages do
    not back (facts, contacts, quote) is marked on the item, so the evidence view shows it."""
    from rag_model.brief import _name_on_page

    i = _find(s, title)
    if i is None:
        return f"There is no item «{title}». The items are: {_titles(s)}.", {}
    old = s.items[i]
    changes = {
        k: v for k, v in (changes or {}).items() if k in EDITABLE and v is not None
    }
    if not changes:
        return (
            f"Nothing to change in «{old['title']}»: give the fields to change in \"changes\".",
            {},
        )
    if "category" in changes:
        changes["category"] = category(str(changes["category"]))
    if "contacts" in changes:
        changes["contacts"] = _normalize({"contacts": changes["contacts"]})[0][
            "contacts"
        ]
    if "facts" in changes:
        changes["facts"] = [
            str(f).strip() for f in changes["facts"] or [] if str(f).strip()
        ]
    new_title = str(changes.get("title", old["title"])).strip()
    if any(
        j != i and it["title"].strip().lower() == new_title.lower()
        for j, it in enumerate(s.items)
    ):
        return (
            f"«{old['title']}» not changed: another item is already titled «{new_title}».",
            {},
        )

    by_url = {p["url"]: p["page_id"] for p in s.pages}
    pages = [
        _norm(_page_text(by_url[src["url"]]))
        for src in old["sources"]
        if src["url"] in by_url
    ]
    min_ratio = config.load()["check"]["evidence_min_ratio"]
    on_page = lambda text: any(
        fuzz.partial_ratio(_norm(text), p) >= min_ratio for p in pages
    )
    unbacked = [f"fact «{f}»" for f in changes.get("facts", []) if not on_page(f)]
    unbacked += [
        f"contact {c['name']}"
        for c in changes.get("contacts", [])
        if not any(_name_on_page(c["name"], p) for p in pages)
    ]
    if "evidence" in changes and not on_page(str(changes["evidence"])):
        unbacked.append("quote")

    item = {**old, **changes, "title": new_title}
    item["edited"] = sorted(set(old.get("edited", [])) | set(changes))
    item["unbacked"] = list(dict.fromkeys(old.get("unbacked", []) + unbacked))
    note = f"changed on request: {', '.join(item['edited'])}"
    if item["unbacked"]:
        note += f"; not in the source: {', '.join(item['unbacked'])}"
    item["flags"] = [
        f for f in old.get("flags", []) if not f.startswith("changed on request")
    ] + [note]
    s.items[i] = item
    return (
        f"«{old['title']}» updated"
        + (f" (now «{new_title}»)" if new_title != old["title"] else "")
        + "."
        + (
            f" Not backed by the source pages, marked for the user: {', '.join(unbacked)}."
            if unbacked
            else ""
        )
    ), {"edited": new_title}


def _update_deck(s: Session, args: dict) -> tuple[str, dict]:
    changed = {
        DECK_ARGS[k]: v for k, v in args.items() if k in DECK_ARGS and v is not None
    }
    s.deck.update(changed)
    return f"Presentation updated: {', '.join(changed) or 'nothing'}.", {
        "changed": sorted(changed)
    }


def _state(s: Session) -> str:
    """The presentation as the user sees it now, for the system prompt."""
    d = s.deck
    lines = [
        "",
        "The presentation the user sees now:",
        f"- title slide: company «{d['company'] or '(not set)'}», subtitle «{d['subtitle'] or '(default)'}», "
        f"label above the title «{d['kicker'] or '(default)'}», speaker «{d['author']}», organisation «{d['organizer']}»",
        f"- overview slide «at a glance» (table of contents): {'shown' if d['overview'] else 'hidden'}; "
        f"contacts slide: {'shown' if d['contacts_slide'] else 'hidden'}. These two are not items: show or hide "
        f"them with update_presentation (overview_slide, contacts_slide true/false).",
        f"- {len(s.items)} item slides:" if s.items else "- no item slides yet",
    ]
    if s.trash:
        lines.append(
            f"- removed earlier (bring back with restore_items): {'; '.join(f'«{t['title']}»' for t in s.trash)}"
        )
    for n, it in enumerate(s.items, 1):
        contacts = (
            ", ".join(c.get("name", "") for c in it.get("contacts") or []) or "none"
        )
        lines.append(
            f"  {n}. «{it['title']}» [{it.get('category', '')}] {it.get('organisation', '')} | summary: "
            f"{it.get('summary', '')} | relevance: {it.get('relevance', '')} | facts: "
            f"{'; '.join(it.get('facts') or []) or 'none'} | contacts: {contacts}"
        )
    return "\n".join(lines)


def _run_tool(
    s: Session, searcher: Searcher, name: str, args: dict, max_items: int
) -> tuple[str, dict]:
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
        s.notes.append(
            "The user deleted these items from the list. Do not add them again unless the user asks for "
            "them back, then use restore_items: "
            + "; ".join(f"«{t}»" for t in gone)
            + "."
        )
        s.events.append(
            {
                "type": "note",
                "text": "Removed from the presentation: " + ", ".join(gone),
            }
        )
        s.save()


def load_sessions() -> dict[str, Session]:
    return (
        {s.id: s for s in (Session.load(p) for p in sorted(SESSIONS.glob("*.json")))}
        if SESSIONS.exists()
        else {}
    )


# ---------- model output ----------
REASONING_END = "<|inner_suffix|>"
RAW_TOOLS = re.compile(r"<\|tools_prefix\|>(.*?)<\|tools_suffix\|>", re.S)
MARKER = re.compile(r"<\|[a-z_]+\|>")

TOOL_NAMES = (
    "search",
    "read_pages",
    "add_items",
    "remove_items",
    "restore_items",
    "edit_item",
    "update_presentation",
)
TEXT_CALL = re.compile(r"\s*(" + "|".join(TOOL_NAMES) + r")\s*\((.*)\)\s*", re.S)
TEXT_ARG = re.compile(r"\s*,?\s*(\w+)\s*[:=]\s*")


def _clean(reply: ChatMessage) -> tuple[ChatMessage, str]:
    """Split Apertus' inline reasoning from the answer and recover raw tool calls. Returns (reply, reasoning)."""
    text, reasoning = reply.text or "", ""
    if REASONING_END in text:
        reasoning, text = text.rsplit(REASONING_END, 1)
    calls = list(reply.tool_calls)
    blocks = RAW_TOOLS.findall(text)
    if blocks:
        recovered = []
        for block in blocks:
            parsed = _json_calls(block)
            if not parsed:
                raise ValueError("Invalid tool-call JSON inside Apertus markers")
            recovered.extend(parsed)
        text = RAW_TOOLS.sub("", text)
    else:
        text, recovered = _trailing_calls(text)
    for name, args in recovered:
        if not any(c.tool_name == name and c.arguments == args for c in calls):
            calls.append(
                ToolCall(
                    tool_name=name, arguments=args, id=f"raw-{uuid.uuid4().hex[:8]}"
                )
            )
    text = MARKER.sub("", RAW_TOOLS.sub("", text)).strip()
    if not calls and (call := _text_call(text)):
        calls.append(
            ToolCall(
                tool_name=call[0], arguments=call[1], id=f"raw-{uuid.uuid4().hex[:8]}"
            )
        )
        text = ""
    reasoning = MARKER.sub("", reasoning).strip()
    if text == (reply.text or "") and calls == list(reply.tool_calls) and not reasoning:
        return reply, ""
    return ChatMessage.from_assistant(
        text=text or None, tool_calls=calls, meta=reply.meta
    ), reasoning


def _json_calls(text: str) -> list[tuple[str, dict]]:
    """Recognize Apertus/OpenAI calls without interpreting arbitrary JSON as code."""
    text = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.S)
    if fenced:
        text = fenced.group(1)
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        if _tool_json_prefix(text):
            raise ValueError(
                f"Malformed tool-call JSON at line {error.lineno}, column {error.colno}: {error.msg}. "
                "Regenerate a complete call with balanced brackets; use a smaller batch of items."
            ) from error
        return []
    allowed = set(_spec()["tools"])
    parsed = []
    for call in raw if isinstance(raw, list) else [raw]:
        if not isinstance(call, dict):
            return []
        if isinstance(call.get("function"), dict):
            call = call["function"]
        if "name" in call and set(call) <= {"name", "arguments", "id", "type"}:
            name, args = call["name"], call.get("arguments", {})
        elif len(call) == 1:
            name, args = next(iter(call.items()))
        else:
            return []
        if not isinstance(name, str) or name not in allowed:
            return []
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON arguments for {name}") from error
        if not isinstance(args, dict):
            raise ValueError(f"Arguments for {name} must be an object")
        parsed.append((name, args))
    return parsed


def _tool_json_prefix(text: str) -> bool:
    names = "|".join(re.escape(name) for name in _spec()["tools"])
    return bool(
        re.match(
            rf'^\s*(?:\[\s*)?\{{\s*(?:"(?:{names})"\s*:|"name"\s*:|"function"\s*:|"type"\s*:\s*"function")',
            text,
        )
    )


def _trailing_calls(text: str) -> tuple[str, list[tuple[str, dict]]]:
    """Recover a complete call suffix, including prose followed by tool JSON.

    Quoted examples stay text. Every recovered call still has to match the
    available tool schema before execution or display.
    """
    calls = _json_calls(text)
    if calls:
        return "", calls
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", text):
        start = match.start()
        prefix = text[:start].rstrip()
        if re.search(
            r"(?:\bexample|\be\.g\.|\bfor instance|\bsuch as)\s*:?\s*$", prefix, re.I
        ):
            continue
        try:
            _, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError as error:
            if _tool_json_prefix(text[start:]):
                raise ValueError(
                    f"Malformed tool-call JSON at column {error.colno}: {error.msg}. "
                    "Regenerate a complete call with balanced brackets and a smaller batch."
                ) from error
            continue
        tail = text[end:].strip()
        prefix = text[:start].rstrip()
        if tail == "```" and re.search(r"```(?:json)?\s*$", prefix):
            prefix = re.sub(r"```(?:json)?\s*$", "", prefix).rstrip()
        elif tail:
            continue
        if re.search(
            r"(?:\bexample|\be\.g\.|\bfor instance|\bsuch as)\s*:?\s*$", prefix, re.I
        ):
            continue
        calls = _json_calls(text[start:end])
        if calls:
            return prefix, calls
    return text, []


def _plain_answer(reply: ChatMessage) -> ChatMessage:
    """Accept a complete answer envelope; retry broken protocol output as plain text.

    Some generations prepend self-narration to {"answer": "..."}. That prefix
    remains in the raw trace, while only the explicit answer reaches chat.
    """
    text = reply.text or ""
    match = re.search(r'(?:\[\s*)?\{\s*"answer"\s*:', text)
    if not match:
        return reply
    try:
        payload, end = json.JSONDecoder().raw_decode(text, match.start())
    except json.JSONDecodeError as error:
        raise ValueError(
            "Final answer contains malformed answer JSON. Return only the final plain-language answer; "
            "omit reasoning, step descriptions, and JSON wrappers."
        ) from error
    tail = text[end:].strip()
    if tail and not (
        tail == "```" and re.search(r"```(?:json)?\s*$", text[: match.start()])
    ):
        raise ValueError(
            "Final answer contains incomplete or extra protocol output; return plain language only."
        )
    if isinstance(payload, list) and len(payload) == 1:
        payload = payload[0]
    if (
        not isinstance(payload, dict)
        or set(payload) != {"answer"}
        or not isinstance(payload["answer"], str)
        or not payload["answer"].strip()
    ):
        raise ValueError(
            "Final answer wrapper must contain one non-empty answer string; return plain language only."
        )
    return ChatMessage.from_assistant(text=payload["answer"].strip(), meta=reply.meta)


def _validate_item_call(call, s: Session, max_items: int) -> None:
    if call.tool_name != "add_items":
        return
    schema = {
        "type": "object",
        "required": ["items"],
        "additionalProperties": False,
        "properties": {"items": _item_schema(min(max_items, 5))},
    }
    errors = list(Draft202012Validator(schema).iter_errors(call.arguments))
    if errors:
        details = []
        for error in errors[:3]:
            path = ".".join(map(str, error.absolute_path)) or "arguments"
            message = (
                f"at most {error.validator_value} entries"
                if error.validator == "maxItems"
                else f"expected {error.validator_value}"
                if error.validator == "type"
                else error.message[:300]
            )
            details.append(f"{path}: {message}")
        raise ValueError(
            "Invalid add_items structure: "
            + "; ".join(details)
            + ". Put slide objects in items; contacts contains only people. "
            "Every item requires its own evidence quote and specific sources."
        )
    for index, item in enumerate(call.arguments["items"]):
        unread = [n for n in item["sources"] if n not in s.read]
        if unread:
            raise ValueError(
                f"items.{index}.sources cites unread pages {unread}; "
                "use only pages already read."
            )


def _call_key(call) -> str:
    return json.dumps([call.tool_name, call.arguments], sort_keys=True)


def _completed_calls(s: Session) -> set[str]:
    # An assistant's attempted call is not evidence that the tool succeeded.
    return {
        _call_key(result.origin)
        for message in s.messages
        for result in (getattr(message, "tool_call_results", None) or [])
        if not result.error
    }


def _context_state(s: Session, text: str, pending: str | None) -> dict:
    """Compact conversation progress for the retrieval assessment."""
    recent = []
    for message in s.messages[-3:]:
        role = getattr(message, "role", None)
        entry = {
            "role": getattr(role, "value", role),
            "text": (message.text or "")[:300],
        }
        if message.tool_calls:
            entry["tool_calls"] = [
                {
                    "name": c.tool_name,
                    "arguments": json.dumps(c.arguments, ensure_ascii=False)[:200],
                }
                for c in message.tool_calls
            ]
        results = getattr(message, "tool_call_results", None) or []
        if results:
            entry["tool_results"] = [
                {
                    "name": r.origin.tool_name,
                    "error": r.error,
                    "text": str(r.result)[:300],
                }
                for r in results
            ]
        recent.append(entry)
    unread = [n for n in range(1, len(s.pages) + 1) if n not in s.read]
    return {
        "user_request": text[:400],
        "pages": len(s.pages),
        "read_pages": len(s.read),
        "items": len(s.items),
        "trashed_items": len(s.trash),
        "trash_titles": [item.get("title", "")[:60] for item in s.trash[:4]],
        "unfinished_step": pending,
        "unread_page_numbers": unread[:8],
        "read_page_numbers": sorted(s.read)[:8],
        "page_previews": [
            {"number": n, "title": s.pages[n - 1].get("title", "")[:70]}
            for n in (unread[:4] + sorted(s.read)[-2:])
        ],
        "item_titles": [item.get("title", "")[:60] for item in s.items[:4]],
        "recent_messages": recent,
    }


def _take(s: Session, titles: list[str]) -> list[dict]:
    """Move the items with these titles from the list to the trash; returns them."""
    found = {i for i in (_find(s, t) for t in titles) if i is not None}
    gone = [it for n, it in enumerate(s.items) if n in found]
    s.items = [it for n, it in enumerate(s.items) if n not in found]
    s.trash = [
        t for t in s.trash if t["title"] not in {g["title"] for g in gone}
    ] + gone
    return gone


def _restore(s: Session, titles: list[str], max_items: int) -> tuple[str, dict]:
    back = []
    for t in titles:
        scored = [
            (fuzz.ratio(str(t).strip().lower(), it["title"].strip().lower()), n)
            for n, it in enumerate(s.trash)
        ]
        score, n = max(scored, default=(0, None))
        if n is not None and score >= 80 and len(s.items) < max_items:
            back.append(s.trash.pop(n))
            s.items.append(back[-1])
    missing = len(titles) - len(back)
    return (
        f"{len(back)} items restored. The list now has {len(s.items)}: {_titles(s)}."
        + (
            f" {missing} not restored: not in the trash or the list is full."
            if missing
            else ""
        ),
        {"restored": len(back)},
    )


def _text_call(text: str) -> tuple[str, dict] | None:
    """A whole answer that is one tool call written as text, `name(key: value, …)` with JSON values."""
    m = TEXT_CALL.fullmatch(text)
    if not m:
        return None
    body, args, i = m.group(2), {}, 0
    while k := TEXT_ARG.match(body, i):
        try:
            args[k.group(1)], i = json.JSONDecoder().raw_decode(body, k.end())
        except json.JSONDecodeError:
            return None
    return (m.group(1), args) if args and not body[i:].strip() else None


def _close_open_calls(s: Session) -> None:
    """After a stop, every tool call needs a result, otherwise the next request to the API is rejected."""
    answered = {
        result.origin.id
        for message in s.messages
        for result in (getattr(message, "tool_call_results", None) or [])
    }
    for m in list(s.messages):
        for call in m.tool_calls:
            if call.id not in answered:
                s.messages.append(
                    ChatMessage.from_tool(
                        "Not run: the user stopped this answer.",
                        origin=call,
                        error=True,
                    )
                )
                answered.add(call.id)


class Stopped(Exception):
    pass


# ---------- loop ----------
def turn(s: Session, text: str, searcher: Searcher) -> Iterator[dict]:
    """Trace each advance separately: SSE may resume this generator in different threads."""
    trace = PipelineTrace(s.id)
    started = time.monotonic()
    trace.write(
        "turn_start",
        user_request=text,
        messages=[m.to_dict() for m in s.messages],
        pages=s.pages,
        read_pages=sorted(s.read),
        items=s.items,
        deck=s.deck,
        notes=s.notes,
    )
    s.stop.clear()
    events = _turn(s, text, searcher)
    status = "cancelled"
    try:
        while True:
            try:
                with trace.bind():
                    event = next(events)
            except StopIteration:
                status = "completed"
                break
            yield event
    except Stopped:
        status = "stopped"
        _close_open_calls(s)
        s.notes.append("The user stopped your previous answer before it was finished.")
        event = {"type": "stopped"}
        with trace.bind():
            record("agent_event", output=event)
        s.events.append(event)
        yield event
        s.save()
    except Exception as error:
        status = "error"
        trace.write(
            "turn_error",
            error_type=type(error).__name__,
            error=str(error),
            traceback=traceback.format_exc(),
        )
        raise
    finally:
        with trace.bind():
            events.close()
        trace.write(
            "turn_end",
            status=status,
            elapsed_s=round(time.monotonic() - started, 3),
            pages=s.pages,
            read_pages=sorted(s.read),
            items=s.items,
        )


def _available_tools(
    s: Session,
    tools: list,
    *,
    retrieval: bool,
    pending: str | None,
    blocked: set[str],
    remaining: int,
    worked: bool,
    retrieval_started: bool = True,
) -> list:
    """State/validity guards; tool choice itself belongs to the LLM."""
    if remaining == 1 and worked:
        return []
    allowed = []
    unread = bool(set(range(1, len(s.pages) + 1)) - s.read)
    for tool in tools:
        name = tool.name
        if name in blocked:
            continue
        if name in ("search", "read_pages") and not retrieval:
            continue
        if retrieval and not retrieval_started and name not in ("search", "read_pages"):
            continue
        if name == "read_pages" and (not unread or pending == "add_items"):
            continue
        if name == "search" and pending in ("read_pages", "add_items"):
            continue
        if name == "add_items" and not s.read:
            continue
        if name in ("remove_items", "edit_item") and not s.items:
            continue
        if name == "restore_items" and not s.trash:
            continue
        if remaining == 2 and pending == "add_items" and name != "add_items":
            continue
        allowed.extend(_step_tools(tools, name, s) or [tool])
    return allowed


def _turn(s: Session, text: str, searcher: Searcher) -> Iterator[dict]:
    t0 = time.time()
    cfg = config.load()
    max_items, max_steps = cfg["brief"]["max_items"], cfg["agent"]["max_steps"]
    system = Template(_spec()["system"]).render(
        language=cfg["brief"]["language"], max_items=max_items
    )
    tools = _tools(max_items)
    record(
        "turn_context",
        config=cfg,
        prompt_version=_spec()["version"],
        system_prompt=system,
    )

    def watch(_chunk=None):
        if s.stop.is_set():
            raise Stopped()

    start = len(s.events)

    def emit(event):
        record("agent_event", output=event)
        s.events.append(event)
        return event

    notes, s.notes = s.notes, []
    s.messages.append(
        ChatMessage.from_user("\n".join([*(f"[{n}]" for n in notes), text]))
    )
    yield emit({"type": "user", "text": text})
    assessment = assess_retrieval(
        text,
        {**_context_state(s, text, None), "presentation": _state(s)},
        on_chunk=watch,
    )
    watch()
    retrieval = assessment["needs_retrieval"]
    yield emit(
        {
            "type": "note",
            "text": ("Retrieval needed. " if retrieval else "No retrieval needed. ")
            + assessment["reason"],
            "retrieval": assessment,
        }
    )
    llm = generator("agent", cfg["llm"], tools=tools, on_chunk=watch)
    done_calls, blocked = _completed_calls(s), set()
    pending, worked, answered, retrieval_started = None, False, False, False
    for step in range(1, max_steps + 1):
        watch()
        set_step(step)
        available = _available_tools(
            s,
            tools,
            retrieval=retrieval,
            pending=pending,
            blocked=blocked,
            remaining=max_steps - step + 1,
            worked=worked,
            retrieval_started=retrieval_started,
        )
        names = {t.name for t in available}
        must_work = bool(available) and (
            pending is not None or (retrieval and not retrieval_started)
        )
        tool_choice = "required" if must_work else "auto" if available else "none"
        instruction = (
            "Choose the next useful tool yourself and generate exactly one call, or answer the user directly. "
            "Do not narrate internal reasoning. Finish in plain language, never tool-call JSON. "
            "Report only the items actually added to the presentation, using added/rejected counts. "
            f"Retrieval assessment: {assessment['reason']} "
            + (
                "New retrieval is allowed. "
                if retrieval
                else "Do not search or read pages for this request. "
            )
            + (
                f"Complete the pending {pending} step before further research or an answer. "
                if pending
                else ""
            )
            + (
                "Use an available tool now; a text-only plan is not enough. "
                if must_work
                else ""
            )
            + (
                "No tools remain for this step. Give an honest final answer using the current state. "
                if not available
                else ""
            )
        )
        prompt = ChatMessage.from_system(system + "\n" + _state(s) + "\n" + instruction)
        generation_messages = [prompt, *s.messages]
        attempts = max(1, cfg["llm"].get("json_attempts", 2))
        for attempt in range(1, attempts + 1):
            watch()
            output = run_logged(
                llm,
                messages=generation_messages,
                tools=available,
                generation_kwargs={"tool_choice": tool_choice},
                purpose="agent_step",
            )
            watch()
            raw = output["replies"][0]
            try:
                if raw.meta.get("finish_reason") == "length":
                    raise ValueError(CUT_OFF)
                reply, reasoning = _clean(raw)
                if not reply.tool_calls:
                    reply = _plain_answer(reply)
                    if must_work:
                        raise ValueError(
                            "Use one available tool to complete the pending work; do not stop with a plan."
                        )
                    if not (reply.text or "").strip():
                        raise ValueError(
                            "Return a nonempty answer or one available tool call."
                        )
                else:
                    if len(reply.tool_calls) != 1:
                        raise ValueError("Generate exactly one tool call per step.")
                    call = reply.tool_calls[0]
                    if call.tool_name not in names:
                        raise ValueError(
                            f"Tool {call.tool_name} is not available. Available tools: {sorted(names)}"
                        )
                    selected = next(t for t in available if t.name == call.tool_name)
                    errors = list(
                        Draft202012Validator(selected.parameters).iter_errors(
                            call.arguments
                        )
                    )
                    if errors:
                        raise ValueError(errors[0].message[:400])
                    _validate_item_call(call, s, max_items)
                break
            except ValueError as error:
                record(
                    "generation_rejected",
                    attempt=attempt,
                    error=str(error),
                    reply=raw.to_dict(),
                )
                if attempt == attempts:
                    raise ValueError(
                        f"Apertus returned invalid agent output: {error}"
                    ) from error
                generation_messages.append(
                    ChatMessage.from_user(
                        f"Your previous output was invalid: {error}. {instruction}\nPrevious output: {raw.text or '[invalid tool call]'}"
                    )
                )
                yield emit(
                    {
                        "type": "note",
                        "text": "Apertus returned invalid output; retrying the current step.",
                    }
                )
        if output.get("routing"):
            yield emit(
                {
                    "type": "note",
                    "text": f"Generation model selected: {output['routing']['model']}.",
                    "routing": output["routing"],
                }
            )
        record("chat_parsed", reply=reply.to_dict(), reasoning=reasoning)
        s.messages.append(reply)
        if not reply.tool_calls:
            yield emit({"type": "assistant", "text": reply.text.strip(), "final": True})
            answered = True
            break
        # Tool-call prose often contains leaked planning; tool events convey the operation to the UI.
        call = reply.tool_calls[0]
        watch()
        key = _call_key(call)
        repeated = key in done_calls
        record(
            "tool_call",
            tool_call_id=call.id,
            name=call.tool_name,
            arguments=call.arguments,
            repeated=repeated,
        )
        yield emit(
            {
                "type": "tool_call",
                "id": call.id,
                "name": call.tool_name,
                "arguments": call.arguments
                if call.tool_name != "add_items"
                else {"items": len(call.arguments.get("items") or [])},
                "repeated": repeated,
            }
        )
        watch()
        if repeated:
            blocked.add(call.tool_name)
            result, info, error = (
                "You already made exactly this call; its result is above. Choose another available operation or answer.",
                {},
                False,
            )
            record(
                "action_blocked",
                action=call.tool_name,
                reason="Identical successful call repeated",
            )
        else:
            before_read = len(s.read)
            try:
                result, info = _run_tool(
                    s, searcher, call.tool_name, call.arguments, max_items
                )
                error = False
            except Stopped:
                raise
            except Exception as error_value:
                result, info, error = f"Error: {error_value}", {}, True
                record(
                    "tool_error",
                    tool_call_id=call.id,
                    name=call.tool_name,
                    error_type=type(error_value).__name__,
                    error=str(error_value),
                    traceback=traceback.format_exc(),
                )
            if not error:
                done_calls.add(key)
                worked = True
                if call.tool_name in ("search", "read_pages"):
                    retrieval_started = True
                if call.tool_name == "search" and len(s.pages) > len(s.read):
                    pending = "read_pages"
                elif call.tool_name == "read_pages" and len(s.read) > before_read:
                    pending = "add_items"
                elif call.tool_name == "add_items":
                    pending = None
        record(
            "tool_response",
            tool_call_id=call.id,
            name=call.tool_name,
            text=result,
            info=info,
            error=error,
            skipped=repeated,
            pages=s.pages,
            read_pages=sorted(s.read),
            items=s.items,
        )
        s.messages.append(ChatMessage.from_tool(result, origin=call, error=error))
        yield emit(
            {
                "type": "tool_result",
                "id": call.id,
                "name": call.tool_name,
                "error": error,
                "info": info,
                "text": result if error or call.tool_name in CHANGES else "",
            }
        )
        if call.tool_name in CHANGES and not error and not repeated:
            yield {"type": "items", "items": s.items, "dropped": s.dropped}
            yield {"type": "deck", "deck": s.deck}
    if not answered:
        yield emit(
            {
                "type": "assistant",
                "final": True,
                "text": f"Stopped after {max_steps} steps (Settings → Agent). Ask me to continue if needed.",
            }
        )
    trace = write_trace(
        {
            "agent_session": s.id,
            "prompt_version": _spec()["version"],
            "took_s": round(time.time() - t0, 1),
            "events": s.events[start:],
            "pages": s.pages,
            "items": s.items,
            "dropped": s.dropped,
            "messages": [m.to_dict() for m in s.messages],
        }
    )
    yield emit({"type": "done", "took_s": round(time.time() - t0, 1), "trace": trace})
    s.save()


def main():
    import argparse

    ap = argparse.ArgumentParser(
        description="Agent test in the terminal (API must be stopped: Qdrant lock)"
    )
    ap.add_argument("message")
    args = ap.parse_args()
    s, searcher = Session(), Searcher()
    for e in turn(s, args.message, searcher):
        print(json.dumps(e, ensure_ascii=False)[:400])


if __name__ == "__main__":
    main()
