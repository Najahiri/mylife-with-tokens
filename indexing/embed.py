"""A4.1: embed all chunks of data/index.sqlite and store the vectors in the same file.

Runs anywhere (laptop CPU or GPU machine); only needs this file, config.yaml and index.sqlite.
Resumable: chunks that already have a vector for the configured model are skipped.
Afterwards `python indexing/index.py load` writes the vectors into Qdrant.

Usage:
    python indexing/embed.py [--db data/index.sqlite] [--device cuda] [--fp16]
"""

import argparse
import json
import sqlite3
import time
from pathlib import Path

import numpy as np
import yaml
from haystack import Document
from haystack.utils import ComponentDevice
from haystack_integrations.components.embedders.sentence_transformers import (
    SentenceTransformersDocumentEmbedder,
)

ROOT = Path(__file__).resolve().parent.parent
STEP = 1024  # chunks per commit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "index.sqlite"))
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument(
        "--device", default=None, help="cpu, cuda, cuda:0 … (default: auto)"
    )
    ap.add_argument(
        "--fp16", action="store_true", help="half precision, only sensible on GPU"
    )
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))["embedding"]
    model = cfg["model"]
    embedder = SentenceTransformersDocumentEmbedder(
        model=model,
        prefix=cfg.get("document_prefix", ""),
        batch_size=cfg["batch_size"],
        meta_fields_to_embed=cfg["meta_fields_to_embed"],
        normalize_embeddings=True,
        progress_bar=False,
        device=ComponentDevice.from_str(args.device) if args.device else None,
        model_kwargs={"dtype": "float16"} if args.fp16 else None,
    )
    embedder.warm_up()

    db = sqlite3.connect(args.db)
    db.execute(
        "CREATE TABLE IF NOT EXISTS vectors (model TEXT, chunk_id TEXT, vec BLOB, PRIMARY KEY (model, chunk_id))"
    )
    todo = db.execute(
        """
        SELECT id, content, meta FROM chunks
        WHERE id NOT IN (SELECT chunk_id FROM vectors WHERE model = ?) ORDER BY id
    """,
        (model,),
    ).fetchall()
    total = db.execute("SELECT count(*) FROM chunks").fetchone()[0]
    print(
        f"{model}: {total - len(todo)}/{total} chunks done, {len(todo)} to go",
        flush=True,
    )

    t0 = time.time()
    for i in range(0, len(todo), STEP):
        docs = []
        for cid, content, meta in todo[i : i + STEP]:
            m = json.loads(meta)
            docs.append(
                Document(
                    id=cid,
                    content=content,
                    meta={k: m.get(k) for k in cfg["meta_fields_to_embed"]},
                )
            )
        docs = embedder.run(documents=docs)["documents"]
        db.executemany(
            "INSERT OR REPLACE INTO vectors VALUES (?,?,?)",
            [
                (model, d.id, np.asarray(d.embedding, dtype=np.float32).tobytes())
                for d in docs
            ],
        )
        db.commit()
        done = i + len(docs)
        rate = done / (time.time() - t0)
        print(
            f"  {done}/{len(todo)} · {rate:.1f} chunks/s · ~{(len(todo) - done) / rate / 60:.1f} min left",
            flush=True,
        )
    print("done")


if __name__ == "__main__":
    main()
