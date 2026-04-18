from __future__ import annotations

import sys
import logging
from dataclasses import dataclass

import config
import db as db_module

logger = logging.getLogger(__name__)

_LITERT_SITE = "/home/yimstar9/.local/share/uv/tools/litert-lm/lib/python3.12/site-packages"
if _LITERT_SITE not in sys.path:
    sys.path.insert(0, _LITERT_SITE)

_embedder = None
_llm_engine = None


@dataclass
class SearchResult:
    filename: str
    filepath: str
    timestamp: str
    timestamp_sec: float
    caption: str
    score: float


def _ensure_loaded(cfg: config.Config):
    global _embedder, _db, _llm_engine

    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(cfg.embedding_model_path)
        logger.info("임베딩 모델 로드 완료")

    if _llm_engine is None:
        import litert_lm
        backend = litert_lm.Backend.GPU if cfg.backend == "gpu" else litert_lm.Backend.CPU
        _llm_engine = litert_lm.Engine(cfg.model_path, backend=backend)
        _llm_engine.__enter__()
        logger.info("LLM 엔진 로드 완료")


def search(query: str, cfg: config.Config) -> list[SearchResult]:
    _ensure_loaded(cfg)

    col = db_module.get_collection(cfg)
    embedding = _embedder.encode(query).tolist()
    results = col.query(
        query_embeddings=[embedding],
        n_results=min(cfg.top_k, max(1, col.count())),
        include=["documents", "metadatas", "distances"],
    )

    output = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        output.append(SearchResult(
            filename=meta["filename"],
            filepath=meta["filepath"],
            timestamp=meta["timestamp"],
            timestamp_sec=meta["timestamp_sec"],
            caption=doc,
            score=round(1 - dist, 4),
        ))

    return sorted(output, key=lambda r: r.score, reverse=True)


def summarize(query: str, results: list[SearchResult], cfg: config.Config) -> str:
    _ensure_loaded(cfg)

    if not results:
        return "검색 결과가 없습니다."

    context_lines = []
    for i, r in enumerate(results[:5], 1):
        context_lines.append(f"{i}. [{r.filename} {r.timestamp}] {r.caption}")
    context = "\n".join(context_lines)

    prompt = (
        f"다음은 보안 카메라 영상에서 검색된 장면 목록입니다:\n\n{context}\n\n"
        f'사용자 질문: "{query}"\n\n'
        "위 장면들을 바탕으로 질문에 답하고, 관련 영상 파일과 시각을 알려줘."
    )

    with _llm_engine.create_conversation() as conv:
        response = conv.send_message(prompt)

    texts = [p["text"] for p in response.get("content", []) if p.get("type") == "text"]
    return " ".join(texts).strip()


def db_count(cfg: config.Config) -> int:
    try:
        return db_module.get_collection(cfg).count()
    except Exception:
        return 0
