"""FastAPI backend: the web UI talks to the RAG model only through these endpoints.

    uv run uvicorn api.main:app --port 8000          # development (UI via `npm run dev` in frontend/)
    uv run uvicorn api.main:app --host 0.0.0.0       # serves the built UI from frontend/dist as well

The search index (Qdrant, local mode) can only be opened by one process: stop the API before running
`python -m rag_model.search` or the indexing steps, and the other way round.
"""
import base64
import json
import re
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rag_model import agent
from rag_model import brief as rag
from rag_model import presentation
from rag_model import config
from rag_model.llm import load_settings, public_settings, save_settings
from rag_model.search import ROOT, Searcher
from rag_model.settings import list_models, test_connection
from scraper import sources as source_list

state: dict = {}
sessions: dict[str, agent.Session] = {}     # agent conversations, saved in data/sessions/
busy: dict[str, threading.Lock] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    state["searcher"] = Searcher()
    state["searcher"].embed("warm up")   # load BGE-M3 once at start, not on the first request
    sessions.update(agent.load_sessions())
    busy.update({sid: threading.Lock() for sid in sessions})
    yield
    state.clear()


app = FastAPI(title="RAGlette", lifespan=lifespan)


# ---------- request bodies ----------
class QueriesIn(BaseModel):
    buzzwords: list[str] = Field(min_length=1)
    mode: Literal["direct", "apertus"] | None = None   # default: Settings → Search terms


class RetrieveIn(BaseModel):
    terms: list[str] = Field(min_length=1)
    top_k: int | None = None
    top_n: int | None = None
    max_per_site: int | None = None
    min_similarity: float | None = None


class BriefIn(BaseModel):
    buzzwords: list[str] = Field(min_length=1)
    page_ids: list[str]
    queries: list[dict] | None = None     # only for the trace
    mode: str | None = None


class SettingsIn(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model_queries: str | None = None
    model_brief: str | None = None
    model_agent: str | None = None


class MessageIn(BaseModel):
    text: str = Field(min_length=1)


class DeckSettingsIn(BaseModel):
    company: str | None = None
    subtitle: str | None = None
    kicker: str | None = None
    author: str | None = None
    organizer: str | None = None
    overview: bool | None = None
    contacts_slide: bool | None = None


class RemoveIn(BaseModel):
    titles: list[str] = Field(min_length=1)


class DeckIn(BaseModel):
    items: list[dict] = Field(min_length=1)
    company: str = ""
    author: str = ""
    organizer: str = ""
    subtitle: str = ""
    kicker: str = ""
    overview: bool = True
    contacts_slide: bool = True
    ppi: int = Field(72, ge=30, le=220)   # preview resolution; the big view asks for more


def _clean(items: list[str]) -> list[str]:
    return list(dict.fromkeys(s.strip() for s in items if s and s.strip()))


def _llm_error(e: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=f"Apertus API: {e}")


# ---------- agent (chat) ----------
@app.post("/api/agent")
def new_session(deck: DeckSettingsIn | None = None):
    s = agent.Session()
    if deck:
        s.deck.update(deck.model_dump(exclude_none=True))
    sessions[s.id], busy[s.id] = s, threading.Lock()
    return s.view()


@app.get("/api/agent/{sid}")
def get_session(sid: str):
    if sid not in sessions:
        raise HTTPException(404, "conversation not found (the API was restarted?)")
    return sessions[sid].view()


@app.put("/api/agent/{sid}/deck")
def update_deck(sid: str, body: DeckSettingsIn):
    """Presentation settings changed in the UI (the agent changes the same settings with update_presentation)."""
    if sid not in sessions:
        raise HTTPException(404, "conversation not found")
    sessions[sid].deck.update(body.model_dump(exclude_none=True))
    sessions[sid].save()
    return {"deck": sessions[sid].deck}


@app.post("/api/agent/{sid}/remove")
def remove_items(sid: str, body: RemoveIn):
    """The user deletes slides: their items leave the list, the agent is told with the next message."""
    if sid not in sessions:
        raise HTTPException(404, "conversation not found (the API was restarted?)")
    if busy[sid].locked():
        raise HTTPException(409, "the agent is still working; delete the slide when it has answered")
    agent.remove_by_user(sessions[sid], body.titles)
    return sessions[sid].view()


@app.post("/api/agent/{sid}/messages")
def send_message(sid: str, body: MessageIn):
    """One chat message; streams the agent's steps as server-sent events until it answers."""
    if sid not in sessions:
        raise HTTPException(404, "conversation not found (the API was restarted?)")
    lock = busy[sid]
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "the agent is still working on the previous message")

    def events():
        try:
            for e in agent.turn(sessions[sid], body.text.strip(), state["searcher"]):
                yield f"data: {json.dumps(e, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Apertus API: {e}'})}\n\n"
        finally:
            sessions[sid].save()
            lock.release()

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ---------- presentation ----------
def _deck(body: DeckIn) -> dict:
    return presentation.deck_data(body.items, body.company, body.author, body.organizer, body.subtitle, body.kicker,
                                  body.overview, body.contacts_slide)


@app.post("/api/presentation/preview")
def preview(body: DeckIn):
    """One PNG per slide (title slide first) as data URLs, and what each slide shows."""
    data = _deck(body)
    try:
        slides = presentation.render(data, "png", ppi=body.ppi)
    except Exception as e:
        raise HTTPException(422, f"Typst: {e}")
    return {"slides": ["data:image/png;base64," + base64.b64encode(s).decode() for s in slides],
            "map": presentation.slide_map(data)}


@app.get("/api/presentation/defaults")
def deck_defaults():
    return presentation.defaults()


@app.post("/api/presentation/pdf")
def pdf(body: DeckIn):
    try:
        data = presentation.render(_deck(body), "pdf")
    except Exception as e:
        raise HTTPException(422, f"Typst: {e}")
    name = re.sub(r"[^\w-]+", "-", body.company.strip() or "company").strip("-")
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}-business-case.pdf"'})


# ---------- pipeline ----------
@app.post("/api/queries")
def queries(body: QueriesIn):
    """B2: buzzwords -> search terms."""
    t0 = time.time()
    try:
        mode = body.mode or config.load()["queries"]["mode"]
        out = rag.search_terms(_clean(body.buzzwords), mode)
    except RuntimeError as e:      # API not configured
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise _llm_error(e)
    return {"queries": out, "mode": mode, "took_s": round(time.time() - t0, 1)}


@app.post("/api/retrieve")
def retrieve(body: RetrieveIn):
    """B3: search terms -> selected pages."""
    t0 = time.time()
    pages = state["searcher"].search(_clean(body.terms), body.top_k, body.top_n, body.max_per_site, body.min_similarity)
    return {"pages": [rag.page_dict(p) for p in pages], "took_s": round(time.time() - t0, 1)}


@app.post("/api/brief")
def brief(body: BriefIn):
    """B4–B6: selected pages -> checked pitch information."""
    try:
        return rag.brief(_clean(body.buzzwords), body.page_ids, state["searcher"],
                         {"mode": body.mode or config.load()["queries"]["mode"], "queries": body.queries})
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise _llm_error(e)


# ---------- settings and status ----------
@app.get("/api/settings")
def get_settings():
    return {"llm": public_settings(), "search": config.load()["search"]}


@app.put("/api/settings")
def put_settings(body: SettingsIn):
    save_settings(body.model_dump())
    return {"llm": public_settings()}


@app.get("/api/settings/models")
def models():
    s = load_settings()
    if not (s.get("base_url") and s.get("api_key")):
        raise HTTPException(status_code=400, detail="API URL and key are missing")
    try:
        return {"models": list_models()}
    except Exception as e:
        raise _llm_error(e)


@app.get("/api/sources")
def get_sources():
    """Websites to crawl, with pages crawled and pages in the search index."""
    return {"sources": source_list.with_status()}


@app.put("/api/sources")
def put_sources(body: dict):
    try:
        source_list.save(body.get("sources", []))
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"sources": source_list.with_status()}


@app.get("/api/config")
def get_config():
    """All pipeline parameters with explanation, current value and default, grouped for the settings page."""
    return {"groups": config.describe()}


@app.put("/api/config")
def put_config(changes: dict[str, dict]):
    try:
        config.update(changes)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"groups": config.describe()}


@app.post("/api/config/reset")
def reset_config(section: str | None = None):
    config.reset(section)
    return {"groups": config.describe()}


@app.post("/api/settings/test")
def test():
    return {"results": test_connection(verbose=False)}


@app.get("/api/health")
def health():
    db = sqlite3.connect(ROOT / "data" / "index.sqlite")
    pages, sites = db.execute("SELECT count(*), count(DISTINCT source) FROM pages").fetchone()
    s = public_settings()
    return {"status": "ok", "pages": pages, "websites": sites,
            "llm_configured": bool(s.get("key_set") and s.get("model_queries") and s.get("model_brief"))}


# ---------- built UI ----------
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def ui(path: str):
        file = DIST / path
        if path and file.is_file():
            return FileResponse(file)
        # index.html must never be cached: it points to the current build's hashed asset files
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache, must-revalidate"})
