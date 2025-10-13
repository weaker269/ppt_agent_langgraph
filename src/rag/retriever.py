"""混合检索器，实现 BM25 + 向量召回。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import jieba  # type: ignore
import numpy as np

from .index import ChunkIndex
from .models import DocumentChunk


@dataclass
class RetrievedChunk:
    """混合检索结果。"""

    chunk: DocumentChunk
    score: float
    dense_score: float
    bm25_score: float


class HybridRetriever:
    """基于 ChunkIndex 的双阶段检索。"""

    def __init__(
        self,
        index: ChunkIndex,
        *,
        dense_top_k: int = 20,
        bm25_top_k: int = 20,
        alpha: float = 0.6,
        normalize_embeddings: bool = True,
    ) -> None:
        if not 0 <= alpha <= 1:
            raise ValueError("alpha 必须位于 [0, 1] 区间内。")
        self.index = index
        self.dense_top_k = dense_top_k
        self.bm25_top_k = bm25_top_k
        self.alpha = alpha
        self.normalize_embeddings = normalize_embeddings

    def retrieve(self, query: str, top_k: int = 5) -> List[RetrievedChunk]:
        if len(self.index) == 0:
            return []

        dense_candidates = self._dense_search(query)
        bm25_candidates = self._bm25_search(query)
        combined = self._merge_scores(dense_candidates, bm25_candidates)

        combined.sort(key=lambda item: item.score, reverse=True)
        return combined[:top_k]

    def _dense_search(self, query: str) -> Dict[int, float]:
        query_vec = self.index.encode_query(query, normalize_embeddings=self.normalize_embeddings)
        scores, indices = self.index.faiss_index.search(query_vec, self.dense_top_k)
        dense_scores: Dict[int, float] = {}
        for idx, score in zip(indices[0], scores[0]):
            if idx < 0:
                continue
            dense_scores[idx] = float(score)
        return dense_scores

    def _bm25_search(self, query: str) -> Dict[int, float]:
        tokens = jieba.lcut(query)
        scores = self.index.bm25.get_scores(tokens)
        ranking = np.argsort(scores)[::-1][: self.bm25_top_k]
        return {int(idx): float(scores[idx]) for idx in ranking if scores[idx] > 0}

    @staticmethod
    def _normalize_scores(score_map: Dict[int, float]) -> Dict[int, float]:
        if not score_map:
            return {}
        values = np.array(list(score_map.values()), dtype=np.float32)
        max_v = float(values.max())
        min_v = float(values.min())
        if max_v - min_v < 1e-9:
            normalized = 1.0 if max_v > 0 else 0.0
            return {idx: normalized for idx in score_map}
        norm_values = (values - min_v) / (max_v - min_v)
        return {idx: float(val) for idx, val in zip(score_map.keys(), norm_values)}

    def _merge_scores(
        self,
        dense_scores: Dict[int, float],
        bm25_scores: Dict[int, float],
    ) -> List[RetrievedChunk]:
        dense_norm = self._normalize_scores(dense_scores)
        bm25_norm = self._normalize_scores(bm25_scores)

        candidate_indices = set(dense_scores) | set(bm25_scores)
        results: List[RetrievedChunk] = []
        for idx in candidate_indices:
            combined = (
                self.alpha * dense_norm.get(idx, 0.0)
                + (1 - self.alpha) * bm25_norm.get(idx, 0.0)
            )
            results.append(
                RetrievedChunk(
                    chunk=self.index.chunks[idx],
                    score=combined,
                    dense_score=dense_scores.get(idx, 0.0),
                    bm25_score=bm25_scores.get(idx, 0.0),
                )
            )
        return results


def retrieve_evidence(
    index: ChunkIndex,
    query: str,
    top_k: int = 5,
    *,
    dense_top_k: int = 20,
    bm25_top_k: int = 20,
    alpha: float = 0.6,
    normalize_embeddings: bool = True,
) -> List[RetrievedChunk]:
    """便捷函数，供流程调用。"""

    retriever = HybridRetriever(
        index,
        dense_top_k=dense_top_k,
        bm25_top_k=bm25_top_k,
        alpha=alpha,
        normalize_embeddings=normalize_embeddings,
    )
    return retriever.retrieve(query, top_k=top_k)


__all__ = ["HybridRetriever", "RetrievedChunk", "retrieve_evidence"]
