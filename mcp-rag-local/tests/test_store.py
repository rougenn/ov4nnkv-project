"""Unit-тесты для VectorStore (без скачивания тяжёлой модели — мокаем embedder)."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.store import VectorStore


class FakeEmbedder:
    """Детерминированный эмбеддер для тестов: bag-of-words → unit vector."""

    VOCAB = ["встреча", "бюджет", "релиз", "проект", "задача", "созвон"]

    def encode(self, text, normalize_embeddings=True):
        text_l = text.lower()
        vec = np.array([float(w in text_l) for w in self.VOCAB], dtype=np.float32)
        if vec.sum() == 0:
            vec = np.ones(len(self.VOCAB), dtype=np.float32)
        if normalize_embeddings:
            n = np.linalg.norm(vec)
            if n > 0:
                vec = vec / n
        return vec


@pytest.fixture
def tmp_store(tmp_path):
    return VectorStore(str(tmp_path / "store.json"), FakeEmbedder())


class TestAdd:
    def test_add_returns_id(self, tmp_store):
        result = tmp_store.add("Обсуждали бюджет проекта", metadata={"date": "2024-12-07"})
        assert result["id"].startswith("doc-")
        assert result["metadata"]["date"] == "2024-12-07"
        assert tmp_store.count() == 1

    def test_add_persists(self, tmp_path):
        path = str(tmp_path / "store.json")
        s1 = VectorStore(path, FakeEmbedder())
        s1.add("Релиз нового проекта")
        s1.add("Задача на следующую неделю")

        s2 = VectorStore(path, FakeEmbedder())
        assert s2.count() == 2

    def test_add_empty_raises(self, tmp_store):
        with pytest.raises(ValueError):
            tmp_store.add("")
        with pytest.raises(ValueError):
            tmp_store.add("   ")


class TestSearch:
    def test_empty_store(self, tmp_store):
        assert tmp_store.search("bla") == []

    def test_finds_most_relevant(self, tmp_store):
        tmp_store.add("Обсудили бюджет на следующий квартал")
        tmp_store.add("Релиз состоится в пятницу")
        tmp_store.add("Задача на проект Альфа")

        results = tmp_store.search("бюджет", top_k=2)
        assert len(results) == 2
        # Топ-результат — про бюджет
        assert "бюджет" in results[0]["content"].lower()
        assert results[0]["score"] > results[1]["score"]

    def test_top_k_limit(self, tmp_store):
        for i in range(5):
            tmp_store.add(f"Встреча {i} про задачу")
        results = tmp_store.search("встреча", top_k=3)
        assert len(results) == 3

    def test_empty_query_returns_empty(self, tmp_store):
        tmp_store.add("Что-то")
        assert tmp_store.search("") == []
        assert tmp_store.search("   ") == []


class TestClear:
    def test_clear(self, tmp_store):
        tmp_store.add("a")
        tmp_store.add("b")
        assert tmp_store.count() == 2
        removed = tmp_store.clear()
        assert removed == 2
        assert tmp_store.count() == 0
