"""验证检索指标记录模块。"""

from __future__ import annotations

import json

from src.rag.metrics import DegradationReason, RetrievalMetricsLogger


def test_metrics_logger_records_summary(tmp_path) -> None:
    log_path = tmp_path / "rag_metrics.jsonl"
    logger = RetrievalMetricsLogger(log_path, top_k_thresholds=(1, 3, 5))

    logger.record_query(
        query="测试查询",
        latency_ms=12.345,
        retrieved=5,
        top_k=5,
        total_chunks=100,
        best_rank=2,
    )
    logger.record_query(
        query="空结果",
        latency_ms=20.0,
        retrieved=0,
        top_k=5,
        total_chunks=100,
        best_rank=None,
        degradation=DegradationReason.EMPTY_RESULT,
    )

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    payload = json.loads(lines[0])
    assert payload["query"] == "测试查询"
    assert payload["topk_hits"]["top@3"] is True

    summary = logger.summary()
    assert summary["total_queries"] == 2
    assert summary["last_chunk_count"] == 100
    assert summary["topk_hit_rate"]["top@1"] == 0.0
    assert summary["topk_hit_rate"]["top@3"] == 0.5
    assert summary["degradation_counts"]["empty_result"] == 1
