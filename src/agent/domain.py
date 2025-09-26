"""核心领域模型定义。

该模块集中维护项目使用的所有结构化模型，供生成器、评估器、工作流共享。
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# 基础枚举
# ---------------------------------------------------------------------------


class SlideType(str, Enum):
    TITLE = "title"
    INTRO = "intro"
    SECTION = "section"
    CONTENT = "content"
    COMPARISON = "comparison"
    DATA = "data"
    SUMMARY = "summary"
    CONCLUSION = "conclusion"


class SlideLayout(str, Enum):
    TITLE = "title"
    STANDARD = "standard"
    TWO_COLUMN = "two_column"
    IMAGE_TEXT = "image_text"
    BULLET = "bullet"
    DATA_TABLE = "data_table"


class StyleTheme(str, Enum):
    PROFESSIONAL = "professional"
    MODERN = "modern"
    CREATIVE = "creative"
    ACADEMIC = "academic"
    MINIMAL = "minimal"


# ---------------------------------------------------------------------------
# 大纲定义
# ---------------------------------------------------------------------------


class OutlineSection(BaseModel):
    index: int = Field(..., ge=1)
    title: str = Field(..., min_length=1, max_length=80)
    summary: str = Field("", max_length=300)
    key_points: List[str] = Field(default_factory=list)
    estimated_slides: int = Field(1, ge=1, le=10)

    @field_validator("key_points", mode="before")
    def _clean_points(cls, value: List[str]) -> List[str]:  # noqa: N805
        return [point.strip() for point in value or [] if point and point.strip()]


class PresentationOutline(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    subtitle: str = Field("", max_length=160)
    target_audience: str = Field("通用听众", max_length=120)
    estimated_duration: int = Field(15, ge=5, le=180)
    sections: List[OutlineSection] = Field(default_factory=list)

    @property
    def total_slides(self) -> int:
        return sum(section.estimated_slides for section in self.sections) + 2  # title + summary


# ---------------------------------------------------------------------------
# 幻灯片定义
# ---------------------------------------------------------------------------


class SlideContent(BaseModel):
    slide_id: int
    title: str
    body: str = ""
    bullet_points: List[str] = Field(default_factory=list)
    speaker_notes: str = ""
    slide_type: SlideType = SlideType.CONTENT
    layout: SlideLayout = SlideLayout.STANDARD
    annotations: Dict[str, str] = Field(default_factory=dict)
    quality_score: Optional[float] = None
    reflection_count: int = 0

    def as_dict(self) -> Dict[str, object]:
        payload = self.model_dump()
        payload["bullet_points"] = [bp for bp in self.bullet_points if bp]
        return payload


class SlidingSummary(BaseModel):
    slide_id: int
    main_message: str
    key_concepts: List[str] = Field(default_factory=list)
    logical_link: str = ""


# ---------------------------------------------------------------------------
# 质量与一致性
# ---------------------------------------------------------------------------


class QualityDimension(str, Enum):
    LOGIC = "logic"
    RELEVANCE = "relevance"
    LANGUAGE = "language"
    LAYOUT = "layout"


class QualityScore(BaseModel):
    total_score: float = Field(..., ge=0.0, le=100.0)
    dimension_scores: Dict[QualityDimension, float]
    pass_threshold: bool
    confidence: float = Field(0.6, ge=0.0, le=1.0)


class QualityFeedback(BaseModel):
    dimension: QualityDimension
    issue_description: str
    suggestion: str
    priority: str = Field("medium", pattern="^(low|medium|high)$")


class ConsistencyIssueType(str, Enum):
    LOGICAL_BREAK = "logical_break"
    STYLE_INCONSISTENCY = "style_inconsistency"
    TERMINOLOGY = "terminology_mismatch"
    REDUNDANT_CONTENT = "redundant_content"
    STRUCTURE = "structure_violation"


class ConsistencyIssue(BaseModel):
    issue_type: ConsistencyIssueType
    severity: str = Field(..., pattern="^(low|medium|high|critical)$")
    slide_ids: List[int]
    description: str
    suggestion: str


class ConsistencyReport(BaseModel):
    overall_score: float = Field(..., ge=0.0, le=100.0)
    issues: List[ConsistencyIssue] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 样式模型
# ---------------------------------------------------------------------------


class StyleProfile(BaseModel):
    theme: StyleTheme
    color_palette: Dict[str, str] = Field(default_factory=dict)
    font_pairing: Dict[str, str] = Field(default_factory=dict)
    layout_preference: str = "balanced"
    reasoning: str = ""


__all__ = [
    "SlideType",
    "SlideLayout",
    "StyleTheme",
    "OutlineSection",
    "PresentationOutline",
    "SlideContent",
    "SlidingSummary",
    "QualityDimension",
    "QualityScore",
    "QualityFeedback",
    "ConsistencyReport",
    "ConsistencyIssue",
    "StyleProfile",
]
