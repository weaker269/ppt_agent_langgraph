"""测试索引持久化功能。"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

from src.rag.index import ChunkIndex, IndexBuilder
from src.rag.loaders import load_documents
from src.rag.models import LoadedDocument


class MockEmbeddingModel:
    """简易嵌入模型，用于测试。"""

    def __init__(self, dim: int = 16) -> None:
        self.dim = dim
        self.name = "mock-embedding"

    def encode(
        self,
        sentences: Sequence[str],
        batch_size: int = 32,
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        vectors = np.zeros((len(sentences), self.dim), dtype=np.float32)
        for row, sentence in enumerate(sentences):
            for ch in sentence:
                bucket = ord(ch) % self.dim
                vectors[row, bucket] += 1.0
        if normalize_embeddings:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            vectors = vectors / norms
        return vectors


def test_index_save_and_load(tmp_path: Path) -> None:
    """测试索引的保存和加载功能。"""
    content = (
        "# 云网融合概述\n\n"
        "云网融合强调计算资源与网络资源的一体化编排，"
        "以提升跨地域业务调度效率。\n\n"
        "## 核心能力\n\n"
        "关键能力包括一体化调度、资源可视化以及智能运维。"
    )
    doc_path = tmp_path / "cloud.md"
    doc_path.write_text(content, encoding="utf-8")

    # 构建索引
    documents: Sequence[LoadedDocument] = load_documents([doc_path])
    embedding_model = MockEmbeddingModel(dim=32)
    builder = IndexBuilder(embedding_model, chunk_size=120, sentence_overlap=1)
    original_index = builder.build_from_documents(documents)

    # 保存索引
    cache_dir = tmp_path / "cache"
    original_index.save(cache_dir)

    # 验证缓存文件存在
    assert (cache_dir / "faiss.index").exists()
    assert (cache_dir / "embeddings.npy").exists()
    assert (cache_dir / "chunks.json").exists()
    assert (cache_dir / "bm25_tokens.json").exists()
    assert (cache_dir / "metadata.json").exists()

    # 加载索引
    loaded_index = ChunkIndex.load(cache_dir, embedding_model)

    # 验证数据一致性
    assert len(loaded_index.chunks) == len(original_index.chunks)
    assert loaded_index.embedding_model_name == original_index.embedding_model_name
    assert np.allclose(loaded_index.embeddings, original_index.embeddings)

    # 验证 chunks 内容一致
    for orig_chunk, loaded_chunk in zip(original_index.chunks, loaded_index.chunks):
        assert orig_chunk.chunk_id == loaded_chunk.chunk_id
        assert orig_chunk.content == loaded_chunk.content
        assert orig_chunk.source == loaded_chunk.source

    # 验证 BM25 tokens 一致
    assert loaded_index.bm25_tokens == original_index.bm25_tokens


def test_index_load_missing_cache_raises_error(tmp_path: Path) -> None:
    """测试加载不存在的缓存时抛出错误。"""
    from src.rag.index import ChunkIndex

    embedding_model = MockEmbeddingModel()
    cache_dir = tmp_path / "nonexistent"

    try:
        ChunkIndex.load(cache_dir, embedding_model)
        assert False, "应该抛出 FileNotFoundError"
    except FileNotFoundError as exc:
        assert "缓存目录不存在" in str(exc)


def test_index_query_encoding_after_reload(tmp_path: Path) -> None:
    """测试重新加载后的索引仍能正确编码查询。"""
    content = "人工智能技术正在改变世界。机器学习是人工智能的核心领域。"
    doc_path = tmp_path / "ai.txt"
    doc_path.write_text(content, encoding="utf-8")

    # 构建并保存索引
    documents = load_documents([doc_path])
    embedding_model = MockEmbeddingModel(dim=16)
    builder = IndexBuilder(embedding_model, chunk_size=50, sentence_overlap=1)
    original_index = builder.build_from_documents(documents)

    cache_dir = tmp_path / "cache"
    original_index.save(cache_dir)

    # 加载索引
    loaded_index = ChunkIndex.load(cache_dir, embedding_model)

    # 验证查询编码功能
    query = "人工智能应用"
    original_vec = original_index.encode_query(query)
    loaded_vec = loaded_index.encode_query(query)

    assert np.allclose(original_vec, loaded_vec)
    assert original_vec.shape == (1, 16)
    assert loaded_vec.dtype == np.float32
