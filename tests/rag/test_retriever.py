"""验证混合检索流程。"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

from src.rag.index import IndexBuilder
from src.rag.loaders import load_documents
from src.rag.models import LoadedDocument
from src.rag.retriever import HybridRetriever, retrieve_evidence


class MockEmbeddingModel:
    """基于字符分桶的简易嵌入模型，用于测试。"""

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


def test_hybrid_retriever_returns_relevant_chunks(tmp_path) -> None:
    content = (
        "# 云网融合概述\n\n"
        "云网融合强调计算资源与网络资源的一体化编排，"
        "以提升跨地域业务调度效率。\n\n"
        "## 核心能力\n\n"
        "关键能力包括一体化调度、资源可视化以及智能运维。"
    )
    doc_path = tmp_path / "cloud.md"
    doc_path.write_text(content, encoding="utf-8")

    documents: Sequence[LoadedDocument] = load_documents([doc_path])
    builder = IndexBuilder(MockEmbeddingModel(dim=32), chunk_size=120, sentence_overlap=1)
    index = builder.build_from_documents(documents)
    retriever = HybridRetriever(index, dense_top_k=5, bm25_top_k=5, alpha=0.5)

    results = retriever.retrieve("什么是云网融合的一体化调度", top_k=3)

    assert results
    top_chunk_text = results[0].chunk.content
    assert "一体化" in top_chunk_text
    assert results[0].score >= results[-1].score


def test_hybrid_retriever_combines_dense_and_bm25(tmp_path) -> None:
    content = (
        "# 混合检索\n\n"
        "BM25 擅长匹配关键词，而向量检索可以捕捉语义。\n\n"
        "## 示例\n\n"
        "混合策略通过分数归一化后按权重融合，提高召回稳定性。"
    )
    doc_path = tmp_path / "retrieval.md"
    doc_path.write_text(content, encoding="utf-8")

    documents = load_documents([doc_path])
    builder = IndexBuilder(MockEmbeddingModel(dim=16), chunk_size=90, sentence_overlap=1)
    index = builder.build_from_documents(documents)

    retriever = HybridRetriever(index, dense_top_k=3, bm25_top_k=3, alpha=0.7)
    results = retriever.retrieve("融合分数归一化策略", top_k=2)

    assert results
    scores = [item.score for item in results]
    assert scores == sorted(scores, reverse=True)
    assert any("融合" in item.chunk.content for item in results)


def test_retrieve_evidence_helper_returns_results(tmp_path) -> None:
    content = "# 测试\n\n向量检索能够找出语义相近的段落。"
    doc_path = tmp_path / "helper.md"
    doc_path.write_text(content, encoding="utf-8")

    documents = load_documents([doc_path])
    builder = IndexBuilder(MockEmbeddingModel(dim=8), chunk_size=80, sentence_overlap=0)
    index = builder.build_from_documents(documents)

    results = retrieve_evidence(index, "语义相近", top_k=1)
    assert results and "语义" in results[0].chunk.content
