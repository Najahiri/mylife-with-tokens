"""A4.1: embed all chunks of data/index.sqlite and store the vectors in the same file.

Runs anywhere (laptop CPU or GPU machine); only needs this file, config.yaml and index.sqlite.
Resumable: chunks that already have a vector for the configured model are skipped. With --reuse, the vectors of
chunks that are unchanged in the live index are copied instead of computed again.
Afterwards `python indexing/index.py load` writes the vectors into Qdrant.

Usage:
    python indexing/embed.py [--db data/index.sqlite] [--device cuda] [--fp16] [--reuse data/index.sqlite]
"""
import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path

import numpy as np
import yaml
from haystack import Document
from haystack.utils import ComponentDevice
from haystack_integrations.components.embedders.sentence_transformers import SentenceTransformersDocumentEmbedder

ROOT = Path(__file__).resolve().parent.parent
STEP = 1024  # chunks per commit


def _key(content: str, meta: str, fields: list[str]) -> str:
    """What the embedding depends on: the text and the context header fields."""
    m = json.loads(meta)
    return hashlib.sha1(json.dumps([content] + [m.get(f) for f in fields], ensure_ascii=False).encode()).hexdigest()


def reuse_vectors(db: sqlite3.Connection, live_path: Path, model: str, fields: list[str]) -> int:
    """Copy the vectors of chunks that are unchanged in the live index, so only new or changed chunks are embedded."""
    live = sqlite3.connect(f"file:{live_path}?mode=ro", uri=True)
    known = {_key(c, m, fields): cid for cid, c, m in live.execute(
        "SELECT c.id, c.content, c.meta FROM chunks c JOIN vectors v ON v.chunk_id = c.id AND v.model = ?", (model,))}
    pairs = [(cid, known[k]) for cid, c, m in db.execute(
        "SELECT id, content, meta FROM chunks WHERE id NOT IN (SELECT chunk_id FROM vectors WHERE model = ?)", (model,))
        if (k := _key(c, m, fields)) in known]
    for i in range(0, len(pairs), 900):
        part = pairs[i:i + 900]
        vecs = dict(live.execute(f"SELECT chunk_id, vec FROM vectors WHERE model = ? AND chunk_id IN ({','.join('?' * len(part))})",
                                 (model, *[old for _, old in part])).fetchall())
        db.executemany("INSERT OR REPLACE INTO vectors VALUES (?,?,?)", [(model, new, vecs[old]) for new, old in part if old in vecs])
    db.commit()
    live.close()
    return len(pairs)


def embed_chunks(db_path: Path, cfg: dict, device: str | None = None, fp16: bool = False,
                 reuse_from: Path | None = None, progress=None) -> dict:
    """Embed every chunk of db_path that has no vector yet. reuse_from: a live index to copy unchanged vectors from.
    progress(share 0…1, detail) is called after every batch (it may raise to stop)."""
    model, fields = cfg["model"], cfg["meta_fields_to_embed"]
    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE IF NOT EXISTS vectors (model TEXT, chunk_id TEXT, vec BLOB, PRIMARY KEY (model, chunk_id))")
    reused = reuse_vectors(db, reuse_from, model, fields) if reuse_from and Path(reuse_from).exists() else 0
    todo = db.execute("""
        SELECT id, content, meta FROM chunks
        WHERE id NOT IN (SELECT chunk_id FROM vectors WHERE model = ?) ORDER BY id
    """, (model,)).fetchall()
    total = db.execute("SELECT count(*) FROM chunks").fetchone()[0]
    print(f"{model}: {total - len(todo)}/{total} chunks done ({reused} reused), {len(todo)} to go", flush=True)
    if progress:
        progress(0.0, f"{reused:,} unchanged chunks reused, {len(todo):,} to embed")
    if todo:
        embedder = SentenceTransformersDocumentEmbedder(
            model=model, prefix=cfg.get("document_prefix", ""), batch_size=cfg["batch_size"],
            meta_fields_to_embed=fields, normalize_embeddings=True, progress_bar=False,
            device=ComponentDevice.from_str(device) if device else None,
            model_kwargs={"dtype": "float16"} if fp16 else None)
        embedder.warm_up()
        t0, step = time.time(), STEP if not progress else 64   # small batches when someone watches the progress
        for i in range(0, len(todo), step):
            docs = []
            for cid, content, meta in todo[i:i + step]:
                m = json.loads(meta)
                docs.append(Document(id=cid, content=content, meta={k: m.get(k) for k in fields}))
            docs = embedder.run(documents=docs)["documents"]
            db.executemany("INSERT OR REPLACE INTO vectors VALUES (?,?,?)",
                           [(model, d.id, np.asarray(d.embedding, dtype=np.float32).tobytes()) for d in docs])
            db.commit()
            done = i + len(docs)
            rate = done / (time.time() - t0)
            left = (len(todo) - done) / rate / 60
            print(f"  {done}/{len(todo)} · {rate:.1f} chunks/s · ~{left:.1f} min left", flush=True)
            if progress:
                progress(done / len(todo), f"{done:,} of {len(todo):,} chunks embedded · {rate:.1f}/s · ~{left:.0f} min left")
    db.close()
    print("done")
    return {"reused": reused, "embedded": len(todo), "chunks": total}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "index.sqlite"))
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--device", default=None, help="cpu, cuda, cuda:0 … (default: auto)")
    ap.add_argument("--fp16", action="store_true", help="half precision, only sensible on GPU")
    ap.add_argument("--reuse", help="live index.sqlite to copy the vectors of unchanged chunks from")
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))["embedding"]
    embed_chunks(Path(args.db), cfg, args.device, args.fp16, Path(args.reuse) if args.reuse else None)


if __name__ == "__main__":
    main()
