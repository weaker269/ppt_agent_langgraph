"""RAG 相关数据模型。"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    """文档级元数据。"""

    document_id: str = Field(..., description="文档唯一标识，通常为文件名或 UUID")
    source_path: str = Field(..., description="文档来源路径")
    media_type: str = Field("text/markdown", description="文档类型，例如 text/plain、application/pdf")
    extra: Dict[str, str] = Field(default_factory=dict, description="其他扩展信息")


class DocumentSection(BaseModel):
    """文档中的结构化章节。"""

    section_id: str
    title: Optional[str] = None
    level: int = 1
    text: str
    start_char: int = 0
    end_char: int = 0
    page_number: Optional[int] = None
    metadata: Dict[str, str] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.text.strip()


class LoadedDocument(BaseModel):
    """加载后的文档结构。"""

    metadata: DocumentMetadata
    sections: List[DocumentSection] = Field(default_factory=list)
    full_text: str = ""

    def non_empty_sections(self) -> List[DocumentSection]:
        return [section for section in self.sections if not section.is_empty()]


class DocumentChunk(BaseModel):
    """分块后的文档片段。"""

    chunk_id: str
    document_id: str
    content: str = Field(..., min_length=1)
    source: str
    section_title: Optional[str] = None
    section_level: Optional[int] = None
    page_number: Optional[int] = None
    start_char: int = 0
    end_char: int = 0
    metadata: Dict[str, str] = Field(default_factory=dict)

    @property
    def length(self) -> int:
        """片段长度（字符数）。"""

        return len(self.content)


class EvidenceItem(BaseModel):
    """用于 RAG 过程中提供参考信息的结构"""

    evidence_id: str = Field(..., description="证据ID")
    chunk_id: str = Field(..., description="对应 DocumentChunk 的ID")
    document_id: str = Field(..., description="所属原始文档ID")
    source_path: str = Field(..., description="原始文档路径")
    snippet: str = Field(..., min_length=1, description="用于提示模型的裁剪文本")
    section_title: Optional[str] = Field(default=None, description="所在文档章节标题")
    score: float = Field(0.0, description="综合得分")
    dense_score: float = Field(0.0, description="向量检索得分")
    bm25_score: float = Field(0.0, description="BM25 得分")
    metadata: Dict[str, str] = Field(default_factory=dict, description="扩展字段")

__all__ = [
    "DocumentMetadata",
    "DocumentSection",
    "LoadedDocument",
    "DocumentChunk",
    "EvidenceItem",
]
