"""嵌入模型召回能力评测脚本。

该脚本对比多种中文嵌入模型与 BM25 关键词检索的表现，输出 Top-K 召回率、MRR、
平均相似度与耗时指标，辅助确定后续 RAG 流程中的模型选型。
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

import faiss  # type: ignore
import jieba  # type: ignore
import numpy as np
from rank_bm25 import BM25Okapi  # type: ignore
from sentence_transformers import SentenceTransformer  # type: ignore


@dataclass
class Passage:
    """表示已切分的文档片段。"""

    pid: str
    source: str
    text: str


@dataclass
class EvalSample:
    """评测查询样例。"""

    query: str
    answer_substrings: List[str]
    corpus_hint: List[str]


@dataclass
class RetrievalMetrics:
    """检索指标汇总结构。"""

    model_name: str
    top1: float
    top3: float
    top5: float
    mrr: float
    avg_top1_score: float
    build_time_s: float
    avg_query_time_ms: float


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""

    parser = argparse.ArgumentParser(description="评估嵌入模型检索表现")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("docs/rag/embedding_eval_samples.jsonl"),
        help="查询与答案样例文件 (JSONL)。",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        nargs="*",
        help="参与评测的语料文件列表，默认根据样例 hints 推断。",
    )
    parser.add_argument(
        "--models",
        nargs="*",
        default=[
            "BAAI/bge-large-zh-v1.5",
            "shibing624/text2vec-base-chinese",
            "moka-ai/m3e-base",
        ],
        help="需要评估的 SentenceTransformer 模型列表。",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="检索召回的 Top-K 范围。",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=280,
        help="单个文档片段的最大字符数。",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=40,
        help="长文本切分时的字符重叠。",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="批量编码时的 batch size。",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        help="SentenceTransformer 加载设备，例如 cpu / cuda。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="若提供，则将结果写入 JSON 文件。",
    )
    parser.add_argument(
        "--disable-bm25",
        action="store_true",
        help="关闭 BM25 对照评测。",
    )
    return parser.parse_args()


def load_eval_samples(path: Path) -> List[EvalSample]:
    """从 JSONL 文件读取评测样例。"""

    samples: List[EvalSample] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            samples.append(
                EvalSample(
                    query=data["query"],
                    answer_substrings=data["answer_substrings"],
                    corpus_hint=data.get("corpus_hint", []),
                )
            )
    if not samples:
        raise ValueError(f"样例文件 {path} 内容为空，无法评测。")
    return samples


def strip_markdown(text: str) -> str:
    """粗粒度去除 Markdown 标记，保留语义文本。"""

    text = text.replace("**", "")
    text = re.sub(r"`+", "", text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, max_chars: int, overlap: int) -> List[str]:
    """将输入文本切分为指定长度的片段。"""

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if not paragraphs:
        return []

    chunks: List[str] = []
    for para in paragraphs:
        if len(para) <= max_chars:
            chunks.append(para)
            continue

        start = 0
        window = max_chars
        overlap = max(0, min(overlap, max_chars // 2))
        stride = max(1, window - overlap)
        while start < len(para):
            end = min(len(para), start + window)
            chunk = para[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(para):
                break
            start += stride
    return chunks


def load_corpus(
    files: Sequence[Path],
    max_chars: int,
    overlap: int,
) -> List[Passage]:
    """读取并切分语料，生成段落列表。"""

    passages: List[Passage] = []
    for file_path in files:
        text = file_path.read_text(encoding="utf-8")
        cleaned = strip_markdown(text)
        chunks = chunk_text(cleaned, max_chars=max_chars, overlap=overlap)
        for idx, chunk in enumerate(chunks):
            pid = f"{file_path.stem}_{idx:03d}"
            passages.append(Passage(pid=pid, source=file_path.name, text=chunk))
    if not passages:
        raise ValueError("语料为空，请检查文件路径或内容。")
    return passages


def normalize_score_text(text: str) -> str:
    """用于答案匹配的文本归一化处理。"""

    return re.sub(r"\s+", "", text)


def contains_answer(text: str, answers: Sequence[str]) -> bool:
    """判断文本是否包含任意答案片段。"""

    normalized = normalize_score_text(text)
    for ans in answers:
        if normalize_score_text(ans) in normalized:
            return True
    return False


def evaluate_bm25(
    samples: Sequence[EvalSample],
    passages: Sequence[Passage],
    top_k: int,
) -> RetrievalMetrics:
    """基于 BM25 的检索评测。"""

    doc_tokens = [jieba.lcut(p.text) for p in passages]
    bm25 = BM25Okapi(doc_tokens)

    hits_top1 = hits_top3 = hits_top5 = 0
    mrr_total = 0.0
    top1_scores = []
    query_durations: List[float] = []

    for sample in samples:
        tokens = jieba.lcut(sample.query)
        start = time.perf_counter()
        scores = bm25.get_scores(tokens)
        query_durations.append(time.perf_counter() - start)
        ranking = np.argsort(scores)[::-1][:top_k]
        match_rank = None
        for rank, idx in enumerate(ranking):
            if contains_answer(passages[idx].text, sample.answer_substrings):
                match_rank = rank
                break

        top1_scores.append(scores[ranking[0]] if ranking.size > 0 else 0.0)
        if match_rank is not None:
            if match_rank == 0:
                hits_top1 += 1
            if match_rank <= 2:
                hits_top3 += 1
            if match_rank <= top_k - 1:
                hits_top5 += 1
            mrr_total += 1.0 / (match_rank + 1)

    n = len(samples)
    return RetrievalMetrics(
        model_name="BM25",
        top1=hits_top1 / n,
        top3=hits_top3 / n,
        top5=hits_top5 / n,
        mrr=mrr_total / n,
        avg_top1_score=float(np.mean(top1_scores)) if top1_scores else 0.0,
        build_time_s=0.0,
        avg_query_time_ms=float(np.mean(query_durations) * 1000) if query_durations else 0.0,
    )


def evaluate_embedding_model(
    model_name: str,
    samples: Sequence[EvalSample],
    passages: Sequence[Passage],
    top_k: int,
    batch_size: int,
    device: str,
) -> RetrievalMetrics:
    """评估单个嵌入模型的检索效果。"""

    model = SentenceTransformer(model_name, device=device)

    texts = [p.text for p in passages]
    start = time.perf_counter()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    build_time = time.perf_counter() - start

    if embeddings.dtype != np.float32:
        embeddings = embeddings.astype(np.float32)

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    hits_top1 = hits_top3 = hits_top5 = 0
    mrr_total = 0.0
    top1_scores: List[float] = []
    query_durations: List[float] = []

    for sample in samples:
        q_start = time.perf_counter()
        query_vec = model.encode(
            sample.query,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        if query_vec.dtype != np.float32:
            query_vec = query_vec.astype(np.float32)
        scores, indices = index.search(query_vec.reshape(1, -1), top_k)
        query_durations.append(time.perf_counter() - q_start)

        retrieved_indices = indices[0]
        retrieved_scores = scores[0]
        top1_scores.append(float(retrieved_scores[0]) if retrieved_scores.size > 0 else 0.0)

        match_rank = None
        for rank, idx in enumerate(retrieved_indices):
            if idx < 0:
                continue
            if contains_answer(passages[idx].text, sample.answer_substrings):
                match_rank = rank
                break

        if match_rank is not None:
            if match_rank == 0:
                hits_top1 += 1
            if match_rank <= 2:
                hits_top3 += 1
            if match_rank <= top_k - 1:
                hits_top5 += 1
            mrr_total += 1.0 / (match_rank + 1)

    n = len(samples)
    return RetrievalMetrics(
        model_name=model_name,
        top1=hits_top1 / n,
        top3=hits_top3 / n,
        top5=hits_top5 / n,
        mrr=mrr_total / n,
        avg_top1_score=float(np.mean(top1_scores)) if top1_scores else 0.0,
        build_time_s=build_time,
        avg_query_time_ms=float(np.mean(query_durations) * 1000) if query_durations else 0.0,
    )


def metrics_to_dict(metrics: RetrievalMetrics) -> dict:
    """将指标转为 JSON 友好格式。"""

    return {
        "model": metrics.model_name,
        "top1_recall": round(metrics.top1, 4),
        "top3_recall": round(metrics.top3, 4),
        "top5_recall": round(metrics.top5, 4),
        "mrr": round(metrics.mrr, 4),
        "avg_top1_score": round(metrics.avg_top1_score, 4),
        "build_time_s": round(metrics.build_time_s, 3),
        "avg_query_time_ms": round(metrics.avg_query_time_ms, 3),
    }


def print_report(metrics_list: Sequence[RetrievalMetrics]) -> None:
    """在终端输出对齐后的结果表格。"""

    header = (
        f"{'Model':40s}  Top1  Top3  Top5   MRR   Top1Score  Build(s)  Q(ms)"
    )
    print(header)
    print("-" * len(header))
    for m in metrics_list:
        print(
            f"{m.model_name:40s}  "
            f"{m.top1:4.2f}  {m.top3:4.2f}  {m.top5:4.2f}  "
            f"{m.mrr:4.2f}  {m.avg_top1_score:9.4f}  {m.build_time_s:7.2f}  {m.avg_query_time_ms:6.2f}"
        )


def main() -> None:
    args = parse_args()

    samples = load_eval_samples(args.dataset)
    if args.corpus:
        corpus_files = [Path(p) for p in args.corpus]
    else:
        hints = {hint for sample in samples for hint in sample.corpus_hint}
        corpus_files = [Path(h) for h in sorted(hints)]

    missing = [str(p) for p in corpus_files if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"以下语料文件不存在，请确认路径正确：{', '.join(missing)}"
        )

    passages = load_corpus(corpus_files, args.chunk_size, args.chunk_overlap)
    print(
        f"共载入 {len(passages)} 个文档片段，来源文件：{', '.join(p.name for p in corpus_files)}"
    )

    metrics_collection: List[RetrievalMetrics] = []

    if not args.disable_bm25:
        print("\n执行 BM25 基线评测...")
        bm25_metrics = evaluate_bm25(samples, passages, args.top_k)
        metrics_collection.append(bm25_metrics)

    for model_name in args.models:
        print(f"\n评测嵌入模型：{model_name}")
        metrics = evaluate_embedding_model(
            model_name,
            samples,
            passages,
            args.top_k,
            args.batch_size,
            args.device,
        )
        metrics_collection.append(metrics)

    print("\n评测结果汇总：")
    print_report(metrics_collection)

    if args.output:
        payload = {"results": [metrics_to_dict(m) for m in metrics_collection]}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"结果已写入 {args.output}")


if __name__ == "__main__":
    main()
