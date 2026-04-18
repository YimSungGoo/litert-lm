from __future__ import annotations

import chromadb
import config

_client: chromadb.PersistentClient | None = None
_collection: chromadb.Collection | None = None


def get_collection(cfg: config.Config) -> chromadb.Collection:
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=cfg.db_path)
        _collection = _client.get_or_create_collection(
            name="nvr_captions",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def reset():
    global _client, _collection
    _client = None
    _collection = None
