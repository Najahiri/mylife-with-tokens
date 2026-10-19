"""Pipeline 1 (A2–A4): crawl.sqlite -> cleaned pages + chunks -> embeddings in Qdrant.

Usage:
    python indexing/index.py prepare   # A2–A3: HTML -> pages + chunks in data/index.sqlite (no embedding model)
    python indexing/embed.py           # A4.1: vectors into data/index.sqlite (CPU or GPU machine)
    python indexing/index.py load      # A4.2: vectors -> Qdrant
    python indexing/index.py activate --db data/index.new.sqlite --qdrant data/qdrant.new   # swap in a new index (API stopped)
"""
import argparse
import hashlib
import json
import sqlite3
import sys
import time
import zlib
from pathlib import Path

import yaml
from haystack import Document, Pipeline
from haystack.components.converters import HTMLToDocument
from haystack.components.joiners import DocumentJoiner
from haystack.components.preprocessors import DocumentCleaner, RecursiveDocumentSplitter
from haystack.components.routers import DocumentLengthRouter
from haystack.dataclasses import ByteStream
from haystack_integrations.components.classifiers.langdetect import DocumentLanguageClassifier
from selectolax.lexbor import LexborHTMLParser

sys.path.insert(0, str(Path(__file__).parent))
from components import BoilerplateRemover, PageFilter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CRAWL_DB = ROOT / "data" / "crawl.sqlite"
INDEX_DB = ROOT / "data" / "index.sqlite"
QDRANT_PATH = ROOT / "data" / "qdrant"
LIVE_DB, LIVE_QDRANT = INDEX_DB, QDRANT_PATH
SOURCES = ROOT / "sources.yaml"
sys.path.insert(0, str(ROOT))
from rag_model import config  # noqa: E402

CONFIG = config.load()
BATCH = 500


def collection_name(model: str) -> str:
    """One Qdrant collection per embedding model, so switching models never mixes vectors."""
    return "chunks__" + "".join(c if c.isalnum() else "_" for c in model.lower())

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    id TEXT PRIMARY KEY, url TEXT, source TEXT, website TEXT, title TEXT,
    language TEXT, crawled_at REAL, content TEXT
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY, page_id TEXT, position INT, content TEXT, meta TEXT
);
CREATE INDEX IF NOT EXISTS chunks_page ON chunks(page_id);
"""


def build_convert_pipeline() -> Pipeline:
    """A2.1: HTML -> Markdown text. Runs in batches; everything after needs the whole corpus."""
    p = Pipeline()
    p.add_component("convert", HTMLToDocument(extraction_kwargs={"output_format": "markdown", "include_tables": True}))
    return p


def build_prepare_pipeline(boilerplate: BoilerplateRemover, page_filter: PageFilter) -> Pipeline:
    """A2.2–A3.1: clean, filter, detect language, split long pages."""
    cfg = CONFIG["prepare"]
    p = Pipeline()
    p.add_component("boilerplate", boilerplate)
    p.add_component("filter", page_filter)
    p.add_component("language", DocumentLanguageClassifier(languages=["de", "en", "fr", "it"]))
    p.add_component("router", DocumentLengthRouter(threshold=cfg["short_page_chars"]))
    p.add_component("split", RecursiveDocumentSplitter(
        split_length=cfg["chunk_words"], split_overlap=cfg["overlap_words"], split_unit="word",
        separators=["\n# ", "\n## ", "\n### ", "\n\n", "sentence", " "]))
    p.add_component("join", DocumentJoiner(join_mode="concatenate", sort_by_score=False))
    p.add_component("clean", DocumentCleaner(remove_empty_lines=True, remove_extra_whitespaces=True, keep_id=True))
    p.connect("boilerplate.documents", "filter.documents")
    p.connect("filter.documents", "language.documents")
    p.connect("language.documents", "router.documents")
    p.connect("router.short_documents", "join.documents")
    p.connect("router.long_documents", "split.documents")
    p.connect("split.documents", "join.documents")
    p.connect("join.documents", "clean.documents")
    return p


def iter_crawled_pages(websites: dict[str, str]):
    db = sqlite3.connect(f"file:{CRAWL_DB}?mode=ro", uri=True)
    # Shorter URLs first, so the canonical URL wins when duplicates are dropped.
    rows = db.execute("""
        SELECT url, final_url, source, fetched_at, html FROM pages
        WHERE status = 200 AND html IS NOT NULL ORDER BY length(final_url), final_url
    """)
    for url, final_url, source, fetched_at, html in rows:
        html = zlib.decompress(html).decode()
        title_node = LexborHTMLParser(html).css_first("title")
        title = " ".join(title_node.text().split()) if title_node else ""
        page_url = final_url or url
        yield ByteStream.from_string(html, meta={
            "page_id": hashlib.sha1(page_url.encode()).hexdigest()[:16],
            "url": page_url, "source": source, "website": websites.get(source, source),
            "title": title, "crawled_at": fetched_at,
        })


class Cancelled(Exception):
    pass


def _report(progress, share: float, detail: str, stop=None):
    if stop and stop():
        raise Cancelled()
    if progress:
        progress(share, detail)


def prepare(progress=None, stop=None):
    """progress(share 0…1, detail), stop() -> bool: optional, for the update job in the API."""
    websites = {s["name"]: s.get("label") or s.get("desc") or s["name"]
                for s in yaml.safe_load(SOURCES.read_text())["sources"]}
    INDEX_DB.unlink(missing_ok=True)
    out = sqlite3.connect(INDEX_DB)
    out.executescript(SCHEMA)

    t0 = time.time()
    with sqlite3.connect(f"file:{CRAWL_DB}?mode=ro", uri=True) as crawl:
        total = crawl.execute("SELECT count(*) FROM pages WHERE status = 200 AND html IS NOT NULL").fetchone()[0] or 1
    convert = build_convert_pipeline()
    converted, batch = [], []
    for stream in iter_crawled_pages(websites):
        batch.append(stream)
        if len(batch) == BATCH:
            converted += convert.run({"convert": {"sources": batch}})["convert"]["documents"]
            batch = []
            print(f"  converted {len(converted)} · {time.time() - t0:.0f}s", flush=True)
            _report(progress, 0.8 * len(converted) / total, f"{len(converted):,} of {total:,} pages converted", stop)
    if batch:
        converted += convert.run({"convert": {"sources": batch}})["convert"]["documents"]

    _report(progress, 0.82, "removing menus and duplicates, splitting into chunks", stop)
    cfg = CONFIG["prepare"]
    boilerplate, page_filter = BoilerplateRemover(**cfg["boilerplate"]), PageFilter(min_words=cfg["min_words"])
    result = build_prepare_pipeline(boilerplate, page_filter).run(
        {"boilerplate": {"documents": converted}}, include_outputs_from={"language"})

    for d in result["language"]["documents"]:
        m = d.meta
        out.execute("INSERT OR IGNORE INTO pages VALUES (?,?,?,?,?,?,?,?)",
                    (m["page_id"], m["url"], m["source"], m["website"], m["title"],
                     m.get("language"), m["crawled_at"], d.content))
    positions: dict[str, int] = {}
    for d in result["clean"]["documents"]:
        pid = d.meta["page_id"]
        pos = positions[pid] = positions.get(pid, -1) + 1
        meta = {k: v for k, v in d.meta.items() if k != "content_hash"}
        out.execute("INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?)",
                    (f"{pid}-{pos}", pid, pos, d.content, json.dumps(meta, ensure_ascii=False, default=str)))
    out.commit()

    n_pages, n_chunks = (out.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("pages", "chunks"))
    print(f"done: {len(converted)} crawled pages -> {n_pages} pages, {n_chunks} chunks · "
          f"boilerplate {boilerplate.stats} · filter {page_filter.stats} · {time.time() - t0:.0f}s")


def load(progress=None, stop=None):
    """A4.2: write the vectors from index.sqlite (computed by indexing/embed.py) into Qdrant.

    Qdrant in local mode commits every single point; on a disk that means one sync per chunk and half an hour for
    the whole index. So the store is built in memory (/dev/shm, if there is one) and moved into place at the end."""
    import shutil
    import tempfile
    shm = Path("/dev/shm")
    target = QDRANT_PATH
    build = Path(tempfile.mkdtemp(prefix="raglette-qdrant-", dir=shm)) if shm.is_dir() else target
    try:
        _load_into(build, progress, stop)
        if build != target:
            _report(progress, 0.97, "moving the vector store into place", stop)
            shutil.rmtree(target, ignore_errors=True)
            shutil.move(str(build), target)
    finally:
        if build != target:
            shutil.rmtree(build, ignore_errors=True)
    print(f"done: the vector store is at {target}")


def _load_into(path: Path, progress=None, stop=None):
    import numpy as np
    from haystack.components.writers import DocumentWriter
    from haystack.document_stores.types import DuplicatePolicy
    from haystack_integrations.document_stores.qdrant import QdrantDocumentStore

    model = CONFIG["embedding"]["model"]
    db = sqlite3.connect(INDEX_DB)
    rows = db.execute("""
        SELECT c.id, c.content, c.meta, v.vec FROM chunks c JOIN vectors v ON v.chunk_id = c.id AND v.model = ?
    """, (model,)).fetchall()
    total = db.execute("SELECT count(*) FROM chunks").fetchone()[0]
    if not rows:
        raise SystemExit(f"no vectors for {model} in {INDEX_DB}; run indexing/embed.py first")
    if len(rows) < total:
        print(f"warning: only {len(rows)} of {total} chunks have vectors for {model}")

    dim = len(np.frombuffer(rows[0][3], dtype=np.float32))
    store = QdrantDocumentStore(path=str(path), index=collection_name(model), embedding_dim=dim,
                                similarity="cosine", recreate_index=True)
    writer = DocumentWriter(document_store=store, policy=DuplicatePolicy.OVERWRITE)
    keep = ("page_id", "url", "source", "website", "title", "language", "crawled_at")
    for i in range(0, len(rows), 2000):
        docs = []
        for cid, content, meta, vec in rows[i:i + 2000]:
            m = json.loads(meta)
            docs.append(Document(id=cid, content=content, meta={k: m.get(k) for k in keep},
                                 embedding=np.frombuffer(vec, dtype=np.float32).tolist()))
        writer.run(documents=docs)
        print(f"  {i + len(docs)}/{len(rows)}", flush=True)
        _report(progress, 0.95 * (i + len(docs)) / len(rows), f"{i + len(docs):,} of {len(rows):,} chunks loaded", stop)
    if store._client is not None:   # local mode allows one client per folder, even within one process
        store._client.close()
    print(f"{len(rows)} chunks ({dim} dims) in collection {collection_name(model)}")


def activate(new_db: Path, new_qdrant: Path):
    """Make a freshly built index live: the current one is kept as *.old, the new one takes its place.

    The API must be stopped first, because Qdrant in local mode allows only one process on its folder.
    """
    import shutil
    for new, live in ((new_db, LIVE_DB), (new_qdrant, LIVE_QDRANT)):
        if not new.exists():
            raise SystemExit(f"{new} does not exist; build it with prepare/embed/load first")
        old = live.with_name(live.name.replace(".sqlite", "") + ".old" + (".sqlite" if live.suffix else ""))
        if old.exists():
            shutil.rmtree(old) if old.is_dir() else old.unlink()
        if live.exists():
            live.rename(old)
        new.rename(live)
        print(f"{new.name} is live as {live.name} (previous one kept as {old.name})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["prepare", "load", "activate"])
    ap.add_argument("--db", help="index database (default data/index.sqlite); build a new one next to the live index")
    ap.add_argument("--qdrant", help="Qdrant folder (default data/qdrant); load into a new folder while the API runs")
    args = ap.parse_args()
    global INDEX_DB, QDRANT_PATH
    INDEX_DB = Path(args.db).resolve() if args.db else INDEX_DB
    QDRANT_PATH = Path(args.qdrant).resolve() if args.qdrant else QDRANT_PATH
    if args.stage == "activate":
        activate(INDEX_DB, QDRANT_PATH)
    else:
        prepare() if args.stage == "prepare" else load()


if __name__ == "__main__":
    main()
