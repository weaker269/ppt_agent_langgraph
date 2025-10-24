"""检索链路指标记录模块。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence


class DegradationReason(str, Enum):
    """降级原因枚举。"""

    EMPTY_RESULT = "empty_result"
    RERANK_TIMEOUT = "rerank_timeout"
    FALLBACK_OUTLINE = "fallback_outline"
    MANUAL_OVERRIDE = "manual_override"


@dataclass
class RetrievalRunStats:
    """检索运行期指标累计值。"""

    total_queries: int = 0
    total_latency_ms: float = 0.0
    total_retrieved: int = 0
    last_chunk_count: int = 0
    topk_hits: Dict[int, int] = field(default_factory=dict)
    degradation_counts: Dict[DegradationReason, int] = field(default_factory=dict)

    def register_topk_thresholds(self, topks: Iterable[int]) -> None:
        """初始化 Top-K 统计桶。"""

        for top_k in topks:
            self.topk_hits.setdefault(int(top_k), 0)

    def hit_rate(self, top_k: int) -> float:
        """返回 Top-K 命中率。"""

        if self.total_queries == 0:
            return 0.0
        return self.topk_hits.get(int(top_k), 0) / self.total_queries

    @property
    def average_latency_ms(self) -> float:
        """平均检索耗时。"""

        if self.total_queries == 0:
            return 0.0
        return self.total_latency_ms / self.total_queries

    @property
    def average_retrieved(self) -> float:
        """平均返回的片段数量。"""

        if self.total_queries == 0:
            return 0.0
        return self.total_retrieved / self.total_queries

    def to_dict(self) -> Dict[str, object]:
        """以字典形式返回指标摘要。"""

        return {
            "total_queries": self.total_queries,
            "avg_latency_ms": round(self.average_latency_ms, 3),
            "avg_retrieved": round(self.average_retrieved, 3),
            "last_chunk_count": self.last_chunk_count,
            "topk_hit_rate": {
                f"top@{k}": round(self.hit_rate(k), 4)
                for k in sorted(self.topk_hits)
            },
            "degradation_counts": {
                reason.value: count for reason, count in self.degradation_counts.items()
            },
        }


class RetrievalMetricsLogger:
    """负责记录检索指标并写入 JSONL 日志。"""

    def __init__(
        self,
        log_path: Path = Path("logs/rag_metrics.jsonl"),
        *,
        top_k_thresholds: Sequence[int] = (1, 3, 5),
        ensure_dir: bool = True,
    ) -> None:
        self.log_path = log_path
        self.top_k_thresholds = sorted({int(k) for k in top_k_thresholds})
        self.stats = RetrievalRunStats()
        self.stats.register_topk_thresholds(self.top_k_thresholds)
        if ensure_dir:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def record_query(
        self,
        *,
        query: str,
        latency_ms: float,
        retrieved: int,
        top_k: int,
        total_chunks: int,
        best_rank: Optional[int],
        degradation: Optional[DegradationReason] = None,
        extra: Optional[Dict[str, object]] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """记录单次检索的指标与详细信息。"""

        event_time = timestamp or datetime.now(timezone.utc)
        payload = {
            "timestamp": event_time.isoformat(),
            "query": query,
            "latency_ms": round(latency_ms, 3),
            "retrieved": int(retrieved),
            "top_k": int(top_k),
            "total_chunks": int(total_chunks),
            "best_rank": int(best_rank) if best_rank is not None else None,
            "topk_hits": {
                f"top@{k}": best_rank is not None and best_rank <= k
                for k in self.top_k_thresholds
            },
            "degradation": degradation.value if degradation else None,
            "extra": extra or {},
        }
        with self.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(payload, ensure_ascii=False) + "\n")

        self._update_stats(
            latency_ms=latency_ms,
            retrieved=retrieved,
            total_chunks=total_chunks,
            best_rank=best_rank,
            degradation=degradation,
        )

    def _update_stats(
        self,
        *,
        latency_ms: float,
        retrieved: int,
        total_chunks: int,
        best_rank: Optional[int],
        degradation: Optional[DegradationReason],
    ) -> None:
        """更新累计指标。"""

        self.stats.total_queries += 1
        self.stats.total_latency_ms += float(latency_ms)
        self.stats.total_retrieved += int(retrieved)
        self.stats.last_chunk_count = int(total_chunks)

        if best_rank is not None:
            for top_k in self.top_k_thresholds:
                if best_rank <= top_k:
                    self.stats.topk_hits[top_k] += 1
        if degradation is not None:
            self.stats.degradation_counts[degradation] = (
                self.stats.degradation_counts.get(degradation, 0) + 1
            )

    def summary(self) -> Dict[str, object]:
        """返回当前累计指标摘要。"""

        return self.stats.to_dict()


__all__ = ["DegradationReason", "RetrievalMetricsLogger", "RetrievalRunStats"]
