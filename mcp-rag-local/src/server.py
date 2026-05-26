"""Локальный RAG MCP сервер.

Tools:
- search_knowledge_base — поиск top-K по cosine similarity
- add_to_knowledge_base — добавить документ
- rag_stats — диагностика
"""

import json
import logging
import os
from typing import Annotated, Optional

from dotenv import find_dotenv, load_dotenv
from fastmcp import FastMCP
from pydantic import Field

try:
    from .store import VectorStore
except ImportError:
    from store import VectorStore  # type: ignore

load_dotenv(find_dotenv())

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mcp-rag-local")

PORT = int(os.getenv("PORT", "8002"))
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
STORE_PATH = os.getenv("RAG_STORE_PATH", "./rag_store.json")

mcp = FastMCP(
    name="mcp-rag-local",
    instructions=(
        "Локальный RAG: поиск и добавление документов через sentence-transformers + "
        "cosine similarity. Совместим с инструментами search_knowledge_base / "
        "add_to_knowledge_base агента."
    ),
)

_store: Optional[VectorStore] = None


def _get_store() -> VectorStore:
    global _store
    if _store is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        # Принудительно CPU — на Apple Silicon MPS-инициализация иногда крашит процесс
        # при первой загрузке модели через xet-streaming.
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
        _store = VectorStore(STORE_PATH, embedder)
        logger.info(f"Store ready: {_store.count()} docs at {STORE_PATH}")
    return _store


# Имена tool'ов совпадают с MCP CloudRU, чтобы агент работал без изменений.
@mcp.tool(name="search")
async def search(
    query: Annotated[str, Field(description="Поисковый запрос на естественном языке")],
    top_k: Annotated[int, Field(default=5, ge=1, le=20)] = 5,
) -> dict:
    """Семантический поиск по локальной базе знаний."""
    try:
        store = _get_store()
        results = store.search(query, top_k=top_k)
        return {
            "success": True,
            "query": query,
            "total": len(results),
            "results": [
                {
                    "content": r["content"],
                    "metadata": r["metadata"],
                    "score": round(r["score"], 4),
                }
                for r in results
            ],
        }
    except Exception as e:
        logger.exception("search error")
        return {"success": False, "error": {"code": "SEARCH_ERROR", "message": str(e)}}


@mcp.tool(name="add_document")
async def add_document(
    content: Annotated[str, Field(description="Текст документа")],
    metadata: Annotated[
        Optional[dict], Field(default=None, description="Метаданные (произвольный JSON)")
    ] = None,
) -> dict:
    """Добавить документ в локальную базу знаний."""
    try:
        store = _get_store()
        result = store.add(content, metadata=metadata or {})
        return {
            "success": True,
            "id": result["id"],
            "total_docs": store.count(),
        }
    except Exception as e:
        logger.exception("add_document error")
        return {"success": False, "error": {"code": "ADD_ERROR", "message": str(e)}}


@mcp.tool(name="rag_stats")
async def rag_stats() -> dict:
    """Статус локального RAG: сколько документов, какая модель."""
    try:
        store = _get_store()
        return {
            "success": True,
            "total_docs": store.count(),
            "model": EMBEDDING_MODEL,
            "store_path": STORE_PATH,
        }
    except Exception as e:
        return {"success": False, "error": {"code": "STATS_ERROR", "message": str(e)}}


def main():
    print("=" * 60)
    print("🧠 LOCAL RAG MCP SERVER")
    print("=" * 60)
    print(f"🚀 MCP Server:  http://0.0.0.0:{PORT}/mcp")
    print(f"📦 Embedding:   {EMBEDDING_MODEL}")
    print(f"💾 Store path:  {STORE_PATH}")
    print("=" * 60)
    # Загружаем модель сразу при старте, чтобы первый запрос не висел
    _get_store()
    mcp.run(transport="streamable-http", host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
