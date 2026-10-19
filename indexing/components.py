"""Custom Haystack components for the indexing pipeline."""

import hashlib
import re
from collections import Counter, defaultdict

from haystack import Document, component


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


@component
class BoilerplateRemover:
    """A2.2: remove menu/footer lines that repeat across many pages of the same website.

    Site-agnostic: a short line counts as boilerplate when it appears on many pages of its source
    (absolute count for large sites, share of pages for small ones). Must see a whole source at once.
    """

    def __init__(
        self, max_words: int = 12, min_pages: int = 3, share: float = 0.2, cap: int = 50
    ):
        self.max_words, self.min_pages, self.share, self.cap = (
            max_words,
            min_pages,
            share,
            cap,
        )
        self.stats = {"lines_removed": 0, "boilerplate_lines": 0}

    @component.output_types(documents=list[Document])
    def run(self, documents: list[Document]):
        by_source: dict[str, list[Document]] = defaultdict(list)
        for doc in documents:
            by_source[doc.meta.get("source", "")].append(doc)

        for docs in by_source.values():
            df = Counter()
            for doc in docs:
                df.update(
                    {
                        _norm(l)
                        for l in (doc.content or "").splitlines()
                        if l.strip() and len(l.split()) <= self.max_words
                    }
                )
            threshold = max(self.min_pages, min(self.cap, int(self.share * len(docs))))
            boiler = {line for line, n in df.items() if n >= threshold}
            self.stats["boilerplate_lines"] += len(boiler)
            for doc in docs:
                kept = []
                for line in (doc.content or "").splitlines():
                    if line.strip() and _norm(line) in boiler:
                        self.stats["lines_removed"] += 1
                    else:
                        kept.append(line)
                doc.content = "\n".join(kept)
        return {"documents": documents}


@component
class PageFilter:
    """A2.3 + A2.5: drop near-empty pages and exact duplicates (same normalized text).

    Keeps state across runs, so the pipeline can be fed in batches while deduplicating globally.
    """

    def __init__(self, min_words: int = 20):
        self.min_words = min_words
        self.seen: set[str] = set()
        self.stats = {"short": 0, "duplicate": 0, "kept": 0}

    @component.output_types(documents=list[Document])
    def run(self, documents: list[Document]):
        kept = []
        for doc in documents:
            text = doc.content or ""
            if len(text.split()) < self.min_words:
                self.stats["short"] += 1
                continue
            digest = hashlib.sha1(_norm(text).encode()).hexdigest()
            if digest in self.seen:
                self.stats["duplicate"] += 1
                continue
            self.seen.add(digest)
            doc.meta["content_hash"] = digest
            kept.append(doc)
        self.stats["kept"] += len(kept)
        return {"documents": kept}
