"""B3: search terms -> selected pages (embedding model + Qdrant, no language model).

    B3.1 embed each term · B3.2 top-K chunks per term · B3.3 group chunks to pages (best chunk counts)
    B3.4 fuse the per-term page lists with RRF · B3.5 drop near-identical pages (e.g. language variants)
    B3.6 at most M pages per website, top N · B3.7 drop pages below the minimum similarity

CLI for testing:
    python -m rag_model.search "continuous glucose monitoring" "wearable biosensors" --top-n 10
"""

import argparse
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from haystack import Document, Pipeline
from haystack.components.joiners import DocumentJoiner
from haystack_integrations.components.embedders.sentence_transformers import (
    SentenceTransformersTextEmbedder,
)
from haystack_integrations.components.retrievers.qdrant import QdrantEmbeddingRetriever
from haystack_integrations.document_stores.qdrant import QdrantDocumentStore

from rag_model import config

ROOT = config.ROOT


def collection_name(model: str) -> str:
    return "chunks__" + "".join(c if c.isalnum() else "_" for c in model.lower())


@dataclass
class Page:
    page_id: str
    url: str
    title: str
    website: str
    source: str
    similarity: float  # best chunk similarity over all terms
    rrf: float = 0.0  # fused rank score (B3.4)
    terms: dict[str, float] = field(
        default_factory=dict
    )  # term -> best similarity for that term
    snippet: str = ""  # best matching chunk
    variants: list[str] = field(
        default_factory=list
    )  # URLs merged into this page (B3.5)
    _embedding: np.ndarray | None = None


class Searcher:
    def __init__(self):
        emb = config.load()["embedding"]
        store = QdrantDocumentStore(
            path=str(ROOT / "data" / "qdrant"),
            index=collection_name(emb["model"]),
            embedding_dim=emb["dim"],
            similarity="cosine",
        )
        self.text_embedder = SentenceTransformersTextEmbedder(
            model=emb["model"],
            prefix=emb.get("query_prefix", ""),
            normalize_embeddings=True,
            progress_bar=False,
        )
        self.pipe = Pipeline()
        self.pipe.add_component("embed", self.text_embedder)
        self.pipe.add_component(
            "retrieve",
            QdrantEmbeddingRetriever(document_store=store, return_embedding=True),
        )
        self.pipe.connect("embed.embedding", "retrieve.query_embedding")
        self.joiner = DocumentJoiner(join_mode="reciprocal_rank_fusion")

    def embed(self, text: str) -> np.ndarray:
        self.text_embedder.warm_up()
        return np.asarray(self.text_embedder.run(text=text)["embedding"])

    def search(
        self,
        terms: list[str],
        top_k: int | None = None,
        top_n: int | None = None,
        max_per_site: int | None = None,
        min_similarity: float | None = None,
        variant_similarity: float | None = None,
    ) -> list[Page]:
        d = config.load()["search"]
        top_k = top_k or d["top_k"]
        top_n = top_n or d["top_n"]
        max_per_site = max_per_site or d["max_per_site"]
        min_similarity = (
            d["min_similarity"] if min_similarity is None else min_similarity
        )
        variant_similarity = variant_similarity or d.get("variant_similarity", 0.95)

        pages: dict[str, Page] = {}
        ranked_lists = []
        for term in terms:
            # B3.1 + B3.2
            chunks = self.pipe.run(
                {"embed": {"text": term}, "retrieve": {"top_k": top_k}}
            )["retrieve"]["documents"]
            # B3.3: one entry per page, scored by its best chunk for this term
            best: dict[str, Document] = {}
            for c in chunks:
                pid = c.meta["page_id"]
                if pid not in best or c.score > best[pid].score:
                    best[pid] = c
            for pid, c in best.items():
                p = pages.get(pid)
                if p is None:
                    p = pages[pid] = Page(
                        pid,
                        c.meta["url"],
                        c.meta.get("title") or "",
                        c.meta.get("website") or "",
                        c.meta.get("source") or "",
                        c.score,
                    )
                p.terms[term] = c.score
                if c.score >= p.similarity:
                    p.similarity, p.snippet, p._embedding = (
                        c.score,
                        c.content,
                        np.asarray(c.embedding),
                    )
            ranked_lists.append(
                sorted(
                    (
                        Document(id=pid, content="", score=c.score)
                        for pid, c in best.items()
                    ),
                    key=lambda x: -x.score,
                )
            )

        # B3.4: reciprocal rank fusion over the per-term page lists
        fused = (
            self.joiner.run(documents=ranked_lists)["documents"] if ranked_lists else []
        )
        ordered = []
        for doc in fused:
            pages[doc.id].rrf = doc.score
            ordered.append(pages[doc.id])

        # B3.5: near-identical pages (same text in another language or URL) collapse into the first one
        kept: list[Page] = []
        for p in ordered:
            twin = next(
                (
                    k
                    for k in kept
                    if p._embedding is not None
                    and k._embedding is not None
                    and float(p._embedding @ k._embedding) >= variant_similarity
                ),
                None,
            )
            if twin:
                twin.variants.append(p.url)
            else:
                kept.append(p)

        # B3.6: at most max_per_site pages per website, then top N
        per_site: dict[str, int] = {}
        selected = []
        for p in kept:
            if per_site.get(p.source, 0) < max_per_site:
                per_site[p.source] = per_site.get(p.source, 0) + 1
                selected.append(p)
            if len(selected) == top_n:
                break

        # B3.7: relevance threshold
        return [p for p in selected if p.similarity >= min_similarity]


def main():
    ap = argparse.ArgumentParser(description="B3 search test")
    ap.add_argument("terms", nargs="+")
    ap.add_argument("--top-k", type=int)
    ap.add_argument("--top-n", type=int)
    ap.add_argument("--max-per-site", type=int)
    ap.add_argument("--min-similarity", type=float)
    args = ap.parse_args()
    pages = Searcher().search(
        args.terms, args.top_k, args.top_n, args.max_per_site, args.min_similarity
    )
    if not pages:
        print("Keine Seite über der Relevanz-Schwelle: nichts Verlässliches gefunden.")
    for i, p in enumerate(pages, 1):
        terms = ", ".join(
            f"{t} {s:.2f}" for t, s in sorted(p.terms.items(), key=lambda x: -x[1])
        )
        print(
            f"{i:2}. [{p.similarity:.3f}] {p.website} · {p.title}\n    {p.url}\n    Begriffe: {terms}"
            + (f"\n    + {len(p.variants)} Variante(n)" if p.variants else "")
        )
        print(
            textwrap.indent(
                textwrap.shorten(p.snippet.replace("\n", " "), 220), "    > "
            )
        )


if __name__ == "__main__":
    main()
