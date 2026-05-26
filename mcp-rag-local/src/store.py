"""In-memory vector store с персистом в JSON."""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


class VectorStore:
    """Простой in-memory cosine-similarity store с автосейвом в JSON."""

    def __init__(self, store_path: str, embedder):
        self.store_path = Path(store_path)
        self.embedder = embedder
        self._docs: list[dict[str, Any]] = []  # [{id, content, metadata, embedding}]
        self._load()

    def _load(self) -> None:
        if not self.store_path.exists():
            logger.info(f"Store {self.store_path} не существует — создаём пустой.")
            return
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            self._docs = data.get("docs", [])
            logger.info(f"Loaded {len(self._docs)} docs from {self.store_path}")
        except Exception as e:
            logger.warning(f"Не удалось прочитать {self.store_path}: {e}. Старт с пустого.")
            self._docs = []

    def _save(self) -> None:
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            self.store_path.write_text(
                json.dumps({"docs": self._docs}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Не удалось сохранить {self.store_path}: {e}")

    def add(self, content: str, metadata: Optional[dict] = None) -> dict:
        """Добавить документ. Возвращает {id, ...}."""
        if not content or not content.strip():
            raise ValueError("content не может быть пустым")
        embedding = self.embedder.encode(content, normalize_embeddings=True).tolist()
        doc = {
            "id": f"doc-{int(time.time() * 1000)}-{len(self._docs)}",
            "content": content,
            "metadata": metadata or {},
            "embedding": embedding,
            "created_at": time.time(),
        }
        self._docs.append(doc)
        self._save()
        return {"id": doc["id"], "metadata": doc["metadata"]}

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Найти top_k ближайших по cosine. Возвращает [{content, metadata, score}]."""
        if not self._docs:
            return []
        if not query or not query.strip():
            return []
        q = self.embedder.encode(query, normalize_embeddings=True)
        embs = np.array([d["embedding"] for d in self._docs])  # (N, D)
        scores = embs @ q  # cosine, т.к. normalize_embeddings
        idx = np.argsort(scores)[::-1][:top_k]
        results = []
        for i in idx:
            d = self._docs[i]
            results.append(
                {
                    "id": d["id"],
                    "content": d["content"],
                    "metadata": d["metadata"],
                    "score": float(scores[i]),
                }
            )
        return results

    def count(self) -> int:
        return len(self._docs)

    def clear(self) -> int:
        n = len(self._docs)
        self._docs = []
        self._save()
        return n
