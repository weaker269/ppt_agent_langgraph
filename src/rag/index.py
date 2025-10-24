"""RAG 索引构建与数据结构。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Protocol, Sequence

import faiss  # type: ignore
import jieba  # type: ignore
import numpy as np
from rank_bm25 import BM25Okapi  # type: ignore

from .chunkers import DEFAULT_CHUNK_SIZE, DEFAULT_SENTENCE_OVERLAP, chunk_documents
from .loaders import load_documents
from .models import DocumentChunk, LoadedDocument


class EmbeddingModel(Protocol):
    """定义最小化的嵌入模型协议。"""

    def encode(
        self,
        sentences: Sequence[str],
        batch_size: int = 32,
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        ...


@dataclass
class ChunkIndex:
    """保存 chunk 与检索所需结构。"""

    chunks: List[DocumentChunk]
    embeddings: np.ndarray
    bm25: BM25Okapi
    bm25_tokens: List[List[str]]
    faiss_index: faiss.IndexFlatIP
    embedding_model: EmbeddingModel
    embedding_model_name: str

    def __post_init__(self) -> None:
        self._id_to_pos: Dict[str, int] = {chunk.chunk_id: idx for idx, chunk in enumerate(self.chunks)}

    def __len__(self) -> int:
        return len(self.chunks)

    def chunk_by_id(self, chunk_id: str) -> DocumentChunk:
        return self.chunks[self._id_to_pos[chunk_id]]

    def encode_query(self, query: str, normalize_embeddings: bool = True) -> np.ndarray:
        vector = self.embedding_model.encode(
            [query],
            batch_size=1,
            convert_to_numpy=True,
            normalize_embeddings=normalize_embeddings,
            show_progress_bar=False,
        )
        if vector.dtype != np.float32:
            vector = vector.astype(np.float32)
        return vector.reshape(1, -1)

    def save(self, cache_dir: Path) -> None:
        """将索引持久化到磁盘。

        Args:
            cache_dir: 缓存目录路径，会在此目录下创建索引文件。
        """
        import json

        cache_dir.mkdir(parents=True, exist_ok=True)

        # 保存 Faiss 索引
        faiss.write_index(self.faiss_index, str(cache_dir / "faiss.index"))

        # 保存嵌入向量
        np.save(cache_dir / "embeddings.npy", self.embeddings)

        # 保存 chunks（Pydantic 序列化）
        chunks_data = [chunk.model_dump() for chunk in self.chunks]
        (cache_dir / "chunks.json").write_text(
            json.dumps(chunks_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 保存 BM25 tokens
        (cache_dir / "bm25_tokens.json").write_text(
            json.dumps(self.bm25_tokens, ensure_ascii=False),
            encoding="utf-8",
        )

        # 保存元数据
        metadata = {
            "embedding_model_name": self.embedding_model_name,
            "chunk_count": len(self.chunks),
            "embedding_dim": self.embeddings.shape[1],
        }
        (cache_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, cache_dir: Path, embedding_model: EmbeddingModel) -> ChunkIndex:
        """从磁盘加载索引。

        Args:
            cache_dir: 缓存目录路径。
            embedding_model: 嵌入模型实例（用于后续查询编码）。

        Returns:
            重建的 ChunkIndex 实例。

        Raises:
            FileNotFoundError: 缓存文件不存在。
            ValueError: 缓存数据损坏或不兼容。
        """
        import json

        if not cache_dir.exists():
            raise FileNotFoundError(f"缓存目录不存在: {cache_dir}")

        # 加载元数据
        metadata = json.loads((cache_dir / "metadata.json").read_text(encoding="utf-8"))

        # 加载 Faiss 索引
        faiss_index = faiss.read_index(str(cache_dir / "faiss.index"))

        # 加载嵌入向量
        embeddings = np.load(cache_dir / "embeddings.npy")

        # 加载 chunks
        chunks_data = json.loads((cache_dir / "chunks.json").read_text(encoding="utf-8"))
        chunks = [DocumentChunk.model_validate(data) for data in chunks_data]

        # 加载 BM25 tokens
        bm25_tokens = json.loads((cache_dir / "bm25_tokens.json").read_text(encoding="utf-8"))

        # 重建 BM25 索引
        bm25 = BM25Okapi(bm25_tokens)

        return cls(
            chunks=chunks,
            embeddings=embeddings,
            bm25=bm25,
            bm25_tokens=bm25_tokens,
            faiss_index=faiss_index,
            embedding_model=embedding_model,
            embedding_model_name=metadata["embedding_model_name"],
        )


class IndexBuilder:
    """负责将文档加载、分块并构建索引。"""

    def __init__(
        self,
        embedding_model: EmbeddingModel,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        sentence_overlap: int = DEFAULT_SENTENCE_OVERLAP,
        batch_size: int = 32,
        normalize_embeddings: bool = True,
        embedding_model_name: Optional[str] = None,
    ) -> None:
        self.embedding_model = embedding_model
        self.chunk_size = chunk_size
        self.sentence_overlap = sentence_overlap
        self.batch_size = batch_size
        self.normalize_embeddings = normalize_embeddings
        self.embedding_model_name = embedding_model_name or getattr(
            embedding_model, "name", embedding_model.__class__.__name__
        )

    def build_from_files(self, paths: Iterable[Path]) -> ChunkIndex:
        documents = load_documents(paths)
        return self.build_from_documents(documents)

    def build_from_documents(self, documents: Iterable[LoadedDocument]) -> ChunkIndex:
        chunk_list = chunk_documents(
            documents,
            chunk_size=self.chunk_size,
            sentence_overlap=self.sentence_overlap,
        )
        if not chunk_list:
            raise ValueError("未生成任何 chunk，无法构建索引。")

        texts = [chunk.content for chunk in chunk_list]
        embeddings = self.embedding_model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
        )
        if embeddings.dtype != np.float32:
            embeddings = embeddings.astype(np.float32)

        if embeddings.ndim != 2:
            raise ValueError("嵌入向量必须为二维矩阵。")

        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)

        tokens = [jieba.lcut(text) for text in texts]
        bm25 = BM25Okapi(tokens)

        return ChunkIndex(
            chunks=chunk_list,
            embeddings=embeddings,
            bm25=bm25,
            bm25_tokens=tokens,
            faiss_index=index,
            embedding_model=self.embedding_model,
            embedding_model_name=self.embedding_model_name,
        )


__all__ = ["ChunkIndex", "IndexBuilder", "EmbeddingModel"]
