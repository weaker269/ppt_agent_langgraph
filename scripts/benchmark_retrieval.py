"""检索链路基准测试脚本。

该脚本基于现有 ChunkIndex 与 HybridRetriever，对指定语料与查询集合执行
Top-K 检索，输出片段数量、平均耗时、命中率等指标，并在运行过程中写入
`logs/rag_metrics.jsonl` 便于持续监控。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sentence_transformers import SentenceTransformer  # type: ignore

from src.rag.index import IndexBuilder
from src.rag.metrics import RetrievalMetricsLogger
from src.rag.retriever import HybridRetriever, RetrievedChunk


@dataclass
class BenchmarkSample:
    """基准测试使用的查询样例。"""

    query: str
    answer_substrings: List[str]
    corpus_hint: List[str]


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""

    parser = argparse.ArgumentParser(description="检索链路监控与性能回归")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("docs/rag/embedding_eval_samples.jsonl"),
        help="包含查询与答案子串的 JSONL 文件路径。",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        nargs="*",
        help="指定语料文件列表，若省略则根据样例中的 corpus_hint 推断。",
    )
    parser.add_argument(
        "--corpus-root",
        type=Path,
        help="当 corpus_hint 为相对路径时的根目录，默认为 dataset 所在目录。",
    )
    parser.add_argument(
        "--model",
        default="shibing624/text2vec-base-chinese",
        help="用于构建索引的 SentenceTransformer 模型名称。",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="SentenceTransformer 加载设备，例如 cpu/cuda。",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="编码语料与查询时的 batch size。",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=280,
        help="文档分块的最大字符数。",
    )
    parser.add_argument(
        "--sentence-overlap",
        type=int,
        default=40,
        help="递归分块时的字符重叠长度。",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="最终返回的 Top-K 片段数量。",
    )
    parser.add_argument(
        "--dense-top-k",
        type=int,
        default=20,
        help="向量检索阶段保留的候选数量。",
    )
    parser.add_argument(
        "--bm25-top-k",
        type=int,
        default=20,
        help="BM25 阶段保留的候选数量。",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.6,
        help="融合得分时向量检索的权重。",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=Path("logs/rag_metrics.jsonl"),
        help="指标 JSONL 日志输出路径。",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        help="若提供，则将汇总结果写入指定 JSON 文件。",
    )
    parser.add_argument(
        "--print-misses",
        action="store_true",
        help="输出未命中的查询，便于后续人工分析。",
    )
    return parser.parse_args()


def load_samples(path: Path) -> List[BenchmarkSample]:
    """读取查询样例。"""

    samples: List[BenchmarkSample] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            samples.append(
                BenchmarkSample(
                    query=data["query"],
                    answer_substrings=list(data["answer_substrings"]),
                    corpus_hint=list(data.get("corpus_hint", [])),
                )
            )
    if not samples:
        raise ValueError(f"样例文件 {path} 内容为空，无法执行基准测试。")
    return samples


def resolve_corpus_files(
    corpus_args: Optional[Iterable[Path]],
    samples: List[BenchmarkSample],
    *,
    default_root: Path,
) -> List[Path]:
    """根据命令行或样例提示确定语料文件集合。"""

    if corpus_args:
        files = [path.resolve() for path in corpus_args]
    else:
        hints: List[Path] = []
        for sample in samples:
            for hint in sample.corpus_hint:
                hints.append((default_root / hint).resolve())
        files = hints
    unique_files: List[Path] = []
    seen: set[Path] = set()
    for file_path in files:
        if file_path not in seen:
            seen.add(file_path)
            unique_files.append(file_path)
    if not unique_files:
        raise ValueError("未找到任何语料文件，请通过 --corpus 或 corpus_hint 指定。")
    missing = [str(path) for path in unique_files if not path.exists()]
    if missing:
        raise FileNotFoundError(f"以下语料文件不存在：{', '.join(missing)}")
    return unique_files


def _normalize_text(text: str) -> str:
    """去除空白符后用于匹配。"""

    return "".join(text.split())


def find_best_rank(results: List[RetrievedChunk], answers: List[str]) -> Optional[int]:
    """查找首个命中答案子串的排名。"""

    normalized_answers = [_normalize_text(item) for item in answers if item]
    if not normalized_answers:
        return None
    for rank, item in enumerate(results, start=1):
        normalized_text = _normalize_text(item.chunk.content)
        if any(answer in normalized_text for answer in normalized_answers):
            return rank
    return None


def main() -> int:
    """脚本主入口。"""

    args = parse_args()
    samples = load_samples(args.dataset)
    corpus_root = args.corpus_root or args.dataset.parent
    corpus_files = resolve_corpus_files(args.corpus, samples, default_root=corpus_root)

    print(f"[INFO] 载入查询样例 {len(samples)} 条，语料文件 {len(corpus_files)} 个。")
    start_build = time.perf_counter()
    model = SentenceTransformer(args.model, device=args.device)
    builder = IndexBuilder(
        model,
        chunk_size=args.chunk_size,
        sentence_overlap=args.sentence_overlap,
        batch_size=args.batch_size,
        normalize_embeddings=True,
        embedding_model_name=args.model,
    )
    index = builder.build_from_files(corpus_files)
    build_time = time.perf_counter() - start_build
    print(
        f"[INFO] 索引构建完成：chunks={len(index)}，耗时={build_time:.2f}s，"
        f"embedding_model={args.model}"
    )

    metrics_logger = RetrievalMetricsLogger(args.log_path)
    retriever = HybridRetriever(
        index,
        dense_top_k=args.dense_top_k,
        bm25_top_k=args.bm25_top_k,
        alpha=args.alpha,
        metrics_logger=metrics_logger,
    )

    misses: List[Dict[str, object]] = []
    for idx, sample in enumerate(samples):
        extra = {
            "sample_id": idx,
            "corpus_hint": sample.corpus_hint,
            "mode": "benchmark_retrieval",
        }
        normalized_answers = [_normalize_text(answer) for answer in sample.answer_substrings if answer]
        results = retriever.retrieve_with_metrics(
            sample.query,
            top_k=args.top_k,
            match_fn=lambda item, norm_answers=normalized_answers: any(
                ans in _normalize_text(item.chunk.content) for ans in norm_answers
            ),
            extra=extra,
        )
        best_rank = find_best_rank(results, sample.answer_substrings)
        if best_rank is None:
            misses.append(
                {
                    "query": sample.query,
                    "expected": sample.answer_substrings,
                    "retrieved": [item.chunk.content[:60] for item in results],
                }
            )

    summary = metrics_logger.summary()
    print("\n=== 检索基准结果 ===")
    print(f"总查询数: {summary['total_queries']}")
    print(f"Chunk 总量: {summary['last_chunk_count']}")
    print(f"平均耗时: {summary['avg_latency_ms']:.3f} ms")
    print(f"平均返回条数: {summary['avg_retrieved']:.2f}")
    for key, value in summary["topk_hit_rate"].items():
        print(f"{key} 命中率: {value:.2%}")
    if summary["degradation_counts"]:
        print("降级统计:")
        for reason, count in summary["degradation_counts"].items():
            print(f"  - {reason}: {count}")

    if args.summary_output:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        with args.summary_output.open("w", encoding="utf-8") as file:
            json.dump(summary, file, ensure_ascii=False, indent=2)
        print(f"[INFO] 汇总结果已写入 {args.summary_output}")

    if args.print_misses and misses:
        print("\n未命中的查询列表：")
        for miss in misses:
            expected = " / ".join(miss["expected"])
            print(f"- {miss['query']} (期望包含: {expected})")

    if not misses:
        print("\n[INFO] 所有查询均在 Top-K 内命中。")
    else:
        print(f"\n[WARN] 未命中查询 {len(misses)} 条，可结合日志进一步排查。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
