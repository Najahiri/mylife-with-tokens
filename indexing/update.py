"""Update the search index while the API keeps running: crawl -> clean and split -> embed -> vector store -> switch.

The new index is built next to the live one (data/index.new.sqlite, data/qdrant.new). Only new or changed chunks are
embedded; the vectors of unchanged chunks are copied from the live index. At the end the API switches over without a
restart (see `switch_index` in api/main.py); the previous index stays as data/*.old.

The heavy stages run in a child process each (`python -m indexing.update <stage>`), which reports its progress as
JSON lines on stdout: the API stays small and responsive, and cancelling simply ends the child.

Started from Settings -> Search index in the UI (POST /api/index/update).
"""
import argparse
import asyncio
import json
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import traceback

from indexing import index as ix

NEW_DB = ix.LIVE_DB.with_name("index.new.sqlite")
NEW_QDRANT = ix.LIVE_QDRANT.with_name("qdrant.new")
MAX_PAGES = 5000   # per website, unless sources.yaml sets max_pages
STAGES = [("crawl", "Crawl the websites"), ("prepare", "Clean and split the pages"),
          ("embed", "Embed new and changed chunks"), ("load", "Build the vector store"), ("switch", "Switch to the new index")]


# ---------- stages (run in the child process) ----------
def crawl_stage(progress, refetch: bool) -> dict:
    import httpx
    import yaml
    from scraper import crawl
    sources = [s for s in yaml.safe_load(ix.SOURCES.read_text())["sources"] if s.get("enabled", True)]
    ix.CRAWL_DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(ix.CRAWL_DB)
    db.executescript(crawl.SCHEMA)
    if refetch:
        db.execute(f"UPDATE frontier SET state = 'todo' WHERE state IN ('done', 'error') "
                   f"AND source IN ({','.join('?' * len(sources))})", [s["name"] for s in sources])
        db.commit()

    async def go():
        async with httpx.AsyncClient(headers={"User-Agent": crawl.UA}, follow_redirects=True, timeout=30,
                                     limits=httpx.Limits(max_connections=len(sources) + 2)) as client:
            crawler = crawl.Crawler(db, client, MAX_PAGES)
            task = asyncio.ensure_future(asyncio.gather(*(crawler.run_source(s) for s in sources), return_exceptions=True))
            while not task.done():
                await asyncio.sleep(1)
                progress(len(crawler.finished) / max(1, len(sources)),
                         f"{crawler.fetched:,} pages fetched · {len(crawler.finished)} of {len(sources)} websites done")
            await task
            return crawler.fetched

    return {"fetched": asyncio.run(go())}


def prepare_stage(progress, refetch: bool) -> dict:
    NEW_DB.unlink(missing_ok=True)
    ix.INDEX_DB = NEW_DB
    ix.prepare(progress=progress)
    with sqlite3.connect(NEW_DB) as db:
        return {t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("pages", "chunks")}


def embed_stage(progress, refetch: bool) -> dict:
    from indexing.embed import embed_chunks
    out = embed_chunks(NEW_DB, ix.CONFIG["embedding"], reuse_from=ix.LIVE_DB, progress=progress)
    return {"reused": out["reused"], "embedded": out["embedded"]}


def load_stage(progress, refetch: bool) -> dict:
    ix.INDEX_DB, ix.QDRANT_PATH = NEW_DB, NEW_QDRANT
    ix.load(progress=progress)
    return {}


CHILD_STAGES = {"crawl": crawl_stage, "prepare": prepare_stage, "embed": embed_stage, "load": load_stage}


def child_main():
    """One stage in its own process: progress and the result as JSON lines on stdout, everything else to stderr."""
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=list(CHILD_STAGES))
    ap.add_argument("--refetch", action="store_true")
    args = ap.parse_args()
    out = sys.stdout
    sys.stdout = sys.stderr   # the indexing code prints its own log lines
    emit = lambda obj: (out.write(json.dumps(obj) + "\n"), out.flush())
    summary = CHILD_STAGES[args.stage](lambda share, detail: emit({"share": share, "detail": detail}), args.refetch)
    emit({"summary": summary})


# ---------- the job (runs in the API) ----------
class UpdateJob:
    def __init__(self, refetch: bool, switch):
        """refetch: fetch every page again, not only new ones. switch(new_db, new_qdrant, progress): makes the new
        index live in the running API."""
        self.refetch, self.switch = refetch, switch
        self.state, self.stage, self.share, self.detail = "running", 0, 0.0, "Starting …"
        self.started, self.finished, self.error, self.summary = time.time(), None, None, {}
        self._cancel = threading.Event()
        self._child: subprocess.Popen | None = None
        self._thread = threading.Thread(target=self._run, daemon=True, name="index-update")

    def start(self) -> "UpdateJob":
        self._thread.start()
        return self

    def cancel(self) -> None:
        if STAGES[self.stage][0] == "switch":
            return   # the switch takes seconds and is not interrupted halfway
        self._cancel.set()
        if self._child and self._child.poll() is None:
            self._child.terminate()

    @property
    def running(self) -> bool:
        return self.state == "running"

    def view(self) -> dict:
        status = lambda i: ("done" if i < self.stage or self.state == "done" else
                            self.state if i == self.stage else "pending")
        return {"state": self.state, "stage": STAGES[self.stage][0], "share": self.share, "detail": self.detail,
                "stages": [{"key": k, "label": label, "status": status(i)} for i, (k, label) in enumerate(STAGES)],
                "started": self.started, "finished": self.finished, "error": self.error, "summary": self.summary,
                "refetch": self.refetch}

    def _progress(self, share: float, detail: str) -> None:
        self.share, self.detail = max(0.0, min(1.0, share)), detail

    def _child_stage(self, key: str) -> None:
        cmd = [sys.executable, "-m", "indexing.update", key] + (["--refetch"] if self.refetch else [])
        self._child = subprocess.Popen(cmd, cwd=ix.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        log: list[str] = []
        drain = threading.Thread(target=lambda: log.extend(self._child.stderr), daemon=True)   # keep the last lines
        drain.start()
        for line in self._child.stdout:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "summary" in msg:
                self.summary.update(msg["summary"])
            else:
                self._progress(msg["share"], msg["detail"])
        code = self._child.wait()
        drain.join(timeout=5)
        if self._cancel.is_set():
            raise InterruptedError()
        if code != 0:
            tail = [l.strip() for l in log if l.strip()][-3:]
            raise RuntimeError(f"{key} failed: " + (" · ".join(tail) or f"exit code {code}"))

    def _run(self) -> None:
        try:
            for i, (key, _) in enumerate(STAGES):
                self.stage, self.share = i, 0.0
                if key == "switch":
                    self.switch(NEW_DB, NEW_QDRANT, self._progress)
                else:
                    self._child_stage(key)
            self.state, self.share = "done", 1.0
            s = self.summary
            self.detail = (f"{s.get('fetched', 0):,} pages fetched · {s.get('pages', 0):,} pages, {s.get('chunks', 0):,} chunks · "
                           f"{s.get('embedded', 0):,} chunks embedded, {s.get('reused', 0):,} reused")
        except InterruptedError:
            self.state, self.detail = "cancelled", "Cancelled; the live index is unchanged."
            self._clean()
        except Exception as e:
            traceback.print_exc()
            self.state, self.error = "error", str(e) or type(e).__name__
            self._clean()
        finally:
            self.finished = time.time()

    def _clean(self) -> None:
        if STAGES[self.stage][0] != "switch":   # the switch handles its own failures
            NEW_DB.unlink(missing_ok=True)
            shutil.rmtree(NEW_QDRANT, ignore_errors=True)


if __name__ == "__main__":
    child_main()
