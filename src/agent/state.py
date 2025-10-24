
"""全局状态与元数据模型。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .domain import (
    ConsistencyReport,
    PresentationOutline,
    QualityFeedback,
    QualityScore,
    SlideContent,
    SlidingSummary,
    StyleProfile,
    StyleTheme,
)


class GenerationMetadata(BaseModel):
    slide_id: int
    model_used: str
    generation_time: float
    token_usage: int = 0
    retry_count: int = 0
    quality_after_reflection: Optional[float] = None


class OverallState(BaseModel):
    """LangGraph 节点间传递的全局状态。"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # 运行信息
    run_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    snapshot_enabled: bool = True

    # 输入
    input_text: str = ""
    input_file_path: str = ""

    # 模型配置
    model_provider: str = "openai"
    model_name: str = "gpt-3.5-turbo"
    enable_quality_reflection: bool = True
    quality_threshold: float = 85.0
    max_reflection_attempts: int = 2

    # 生成结果
    outline: Optional[PresentationOutline] = None
    slides: List[SlideContent] = Field(default_factory=list)
    sliding_summaries: List[SlidingSummary] = Field(default_factory=list)
    selected_style: StyleProfile = Field(default_factory=lambda: StyleProfile(theme=StyleTheme.PROFESSIONAL))
    html_output: str = ""
    output_file_path: str = ""

    # 质量与评估
    slide_quality: Dict[int, QualityScore] = Field(default_factory=dict)
    quality_feedback: Dict[int, List[QualityFeedback]] = Field(default_factory=dict)
    consistency_report: Optional[ConsistencyReport] = None

    # RAG 资源
    rag_index: Optional[Any] = Field(default=None, exclude=True)
    retriever: Optional[Any] = Field(default=None, exclude=True)
    slide_evidence: Dict[int, List[Dict[str, Any]]] = Field(default_factory=dict)
    evidence_queries: Dict[int, str] = Field(default_factory=dict)

    # 元数据
    generation_metadata: List[GenerationMetadata] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    def record_error(self, message: str) -> None:
        self.errors.append(message)

    def record_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_slide(self, slide: SlideContent) -> None:
        self.slides.append(slide)

    def add_summary(self, summary: SlidingSummary, window_size: int) -> None:
        self.sliding_summaries.append(summary)
        if len(self.sliding_summaries) > window_size:
            self.sliding_summaries = self.sliding_summaries[-window_size:]

    def succeed(self) -> bool:
        return not self.errors and self.html_output != ""


__all__ = ["OverallState", "GenerationMetadata"]
