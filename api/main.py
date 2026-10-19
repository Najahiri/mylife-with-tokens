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

from indexing import index as indexer
from indexing.update import UpdateJob
from rag_model import agent
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
    # after a fresh clone only index.sqlite is there (download, see README): build the vector store from its vectors
    if not (ROOT / "data" / "qdrant").exists() and (ROOT / "data" / "index.sqlite").exists():
        print("data/qdrant is missing: loading the vectors from data/index.sqlite (a few minutes, once)", flush=True)
        indexer.load()
    state["searcher"] = Searcher()
    state["searcher"].embed("warm up")   # load BGE-M3 once at start, not on the first request
    sessions.update(agent.load_sessions())
    busy.update({sid: threading.Lock() for sid in sessions})
    yield
    state.clear()


app = FastAPI(title="RAGlette", lifespan=lifespan)


# ---------- request bodies ----------
class SettingsIn(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
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
    format: Literal["pdf", "pptx"] = "pdf"   # for the export


def _llm_error(e: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=f"Apertus API: {e}")


# ---------- agent (chat) ----------
@app.get("/api/agent")
def list_sessions():
    """Saved conversations, most recently changed first (empty ones are left out)."""
    return {"sessions": sorted((s.summary() for s in sessions.values() if s.events),
                               key=lambda x: x["updated"], reverse=True)}


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


@app.delete("/api/agent/{sid}")
def delete_session(sid: str):
    """Delete a conversation for good (its saved file; traces stay)."""
    if sid not in sessions:
        raise HTTPException(404, "conversation not found")
    if busy[sid].locked():
        raise HTTPException(409, "the agent is still working on this conversation")
    sessions.pop(sid).delete()
    busy.pop(sid, None)
    return {"deleted": sid}


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


@app.post("/api/agent/{sid}/stop")
def stop_message(sid: str):
    """Stop button: the running answer ends after the current streamed chunk; nothing else runs."""
    if sid not in sessions:
        raise HTTPException(404, "conversation not found")
    sessions[sid].stop.set()
    return {"stopped": busy[sid].locked()}


@app.post("/api/agent/{sid}/messages")
def send_message(sid: str, body: MessageIn):
    """One chat message; streams the agent's steps as server-sent events until it answers."""
    if sid not in sessions:
        raise HTTPException(404, "conversation not found (the API was restarted?)")
    if state.get("switching") or "searcher" not in state:
        raise HTTPException(503, "The search index is being switched to the new version; try again in a few seconds.")
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


EXPORT_TYPES = {"pdf": "application/pdf",
                "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}


@app.post("/api/presentation/export")
def export(body: DeckIn):
    """The deck as a file: PDF, or PowerPoint with every slide as a picture and its text in the notes."""
    try:
        data = presentation.pptx(_deck(body)) if body.format == "pptx" else presentation.render(_deck(body), "pdf")
    except Exception as e:
        raise HTTPException(422, f"Typst: {e}")
    name = re.sub(r"[^\w-]+", "-", body.company.strip() or "company").strip("-")
    return Response(data, media_type=EXPORT_TYPES[body.format],
                    headers={"Content-Disposition": f'attachment; filename="{name}-business-case.{body.format}"'})


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
    return {"results": test_connection(verbose=False, roles=("agent",))}   # the UI only uses the agent


# ---------- search index: status and update ----------
class UpdateIn(BaseModel):
    refetch: bool = False   # fetch every page again, not only new ones (takes hours)


def switch_index(new_db, new_qdrant, progress):
    """Make a freshly built index live without a restart: wait for running agent turns, close the current index,
    move the new one in place (the current one is kept as *.old) and open it."""
    state["switching"] = True            # new chat messages wait
    try:
        while any(lock.locked() for lock in busy.values()):
            progress(0.1, "Waiting until the agent has answered …")
            time.sleep(1)
        progress(0.4, "Closing the current index …")
        old = state.pop("searcher", None)
        if old:
            old.close()
        indexer.activate(new_db, new_qdrant)
        progress(0.7, "Opening the new index …")
        state["searcher"] = Searcher()
        state["searcher"].embed("warm up")
        progress(1.0, "The new index is live.")
    finally:
        if "searcher" not in state:      # something went wrong: open whatever is live now
            try:
                state["searcher"] = Searcher()
            except Exception as e:
                print(f"could not open the index: {e!r}")
        state["switching"] = False


def _index_stats() -> dict:
    live = ROOT / "data" / "index.sqlite"
    if not live.exists():
        return {"pages": 0, "chunks": 0, "built": None}
    with sqlite3.connect(f"file:{live}?mode=ro", uri=True) as db:
        pages, chunks = (db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("pages", "chunks"))
    return {"pages": pages, "chunks": chunks, "built": live.stat().st_mtime}


@app.get("/api/index")
def index_status():
    job = state.get("job")
    return {**_index_stats(), "job": job.view() if job else None}


@app.post("/api/index/update")
def start_update(body: UpdateIn):
    job = state.get("job")
    if job and job.running:
        raise HTTPException(409, "an update is already running")
    state["job"] = UpdateJob(body.refetch, switch_index).start()
    return {**_index_stats(), "job": state["job"].view()}


@app.post("/api/index/update/cancel")
def cancel_update():
    job = state.get("job")
    if not job or not job.running:
        raise HTTPException(409, "no update is running")
    job.cancel()
    return {**_index_stats(), "job": job.view()}


@app.get("/api/health")
def health():
    db = sqlite3.connect(ROOT / "data" / "index.sqlite")
    pages, sites = db.execute("SELECT count(*), count(DISTINCT source) FROM pages").fetchone()
    s = public_settings()
    return {"status": "ok", "pages": pages, "websites": sites,
            "llm_configured": bool(s.get("key_set") and s.get("model_agent"))}


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
