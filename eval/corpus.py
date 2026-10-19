"""One shared, frozen retrieval service for isolated benchmark workers."""

from contextlib import closing
import json
from multiprocessing.managers import BaseManager
import sqlite3
import threading


class CorpusManager(BaseManager):
    pass


CorpusManager.register("corpus")


class Corpus:
    def __init__(self, database, pipeline_config):
        import numpy as np
        from haystack import Document
        from haystack_integrations.document_stores.qdrant import QdrantDocumentStore
        from rag_model import config, search

        # This benchmark process never writes application configuration.
        config.load = lambda: pipeline_config
        embedding = pipeline_config["embedding"]
        store = QdrantDocumentStore(
            location=":memory:",
            index=search.collection_name(embedding["model"]),
            embedding_dim=embedding["dim"],
            similarity="cosine",
            progress_bar=False,
            force_disable_check_same_thread=True,
        )
        count = 0
        with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as db:
            rows = db.execute(
                "SELECT c.id,c.content,c.meta,v.vec FROM chunks c JOIN vectors v "
                "ON v.chunk_id=c.id WHERE v.model=?",
                (embedding["model"],),
            )
            while batch := rows.fetchmany(256):
                docs = []
                for identifier, content, metadata, vector in batch:
                    meta = json.loads(metadata)
                    docs.append(
                        Document(
                            id=identifier,
                            content=content,
                            meta={
                                key: meta.get(key)
                                for key in (
                                    "page_id",
                                    "url",
                                    "source",
                                    "website",
                                    "title",
                                    "language",
                                    "crawled_at",
                                )
                            },
                            embedding=np.frombuffer(vector, dtype=np.float32).tolist(),
                        )
                    )
                store.write_documents(docs)
                count += len(docs)
        if not count:
            store._client.close()
            raise ValueError(f"No vectors for {embedding['model']} in frozen corpus")
        factory = search.QdrantDocumentStore
        try:
            search.QdrantDocumentStore = lambda **kwargs: store
            self.searcher = search.Searcher()
        finally:
            search.QdrantDocumentStore = factory
        self.lock = threading.Lock()
        self.searcher.embed("benchmark initialization")
        print(
            f"Retrieval ready: {count:,} frozen vectors; embedding model warmed.",
            flush=True,
        )

    def search(self, *args, **kwargs):
        with self.lock:
            return self.searcher.search(*args, **kwargs)

    def embed(self, text):
        with self.lock:
            return self.searcher.embed(text)

    def close(self):
        with self.lock:
            self.searcher.close()


class RemoteSearcher:
    def __init__(self, address, authkey):
        self.manager = CorpusManager(address=tuple(address), authkey=authkey)
        self.manager.connect()
        self.proxy = self.manager.corpus()

    def search(self, *args, **kwargs):
        return self.proxy.search(*args, **kwargs)

    def embed(self, text):
        return self.proxy.embed(text)
