
"""Pydantic 模型：约束 LLM 的结构化响应格式。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .domain import QualityDimension, StyleTheme


# ---------------------------------------------------------------------------
# 大纲响应结构
# ---------------------------------------------------------------------------


class OutlineKeyPointResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    point: str = Field(..., min_length=1, max_length=200)
    template_suggestion: str = Field("simple_content", min_length=1, max_length=40)

    @field_validator("point", mode="before")
    def _strip_point(cls, value: str) -> str:  # noqa: N805
        if isinstance(value, str):
            value = value.strip()
        if not value:
            raise ValueError("要点内容不能为空")
        return value

    @field_validator("template_suggestion", mode="before")
    def _normalize_template(cls, value: Optional[str]) -> str:  # noqa: N805
        if isinstance(value, str):
            value = value.strip().lower()
        return value or "simple_content"


class OutlineSectionResponse(BaseModel):
    section_id: int = Field(..., ge=1)
    title: str = Field(..., min_length=1, max_length=80)
    summary: str = Field("", max_length=300)
    key_points: List[OutlineKeyPointResponse] = Field(default_factory=list, min_items=1)
    estimated_slides: int = Field(1, ge=1, le=10)


class OutlineResponse(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    subtitle: str = Field("", max_length=160)
    target_audience: str = Field("通用听众")
    estimated_duration: int = Field(15, ge=5, le=180)
    sections: List[OutlineSectionResponse] = Field(default_factory=list, min_items=1, max_items=10)


# ---------------------------------------------------------------------------
# 幻灯片内容响应结构
# ---------------------------------------------------------------------------


class SlideChartResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    element_id: str = Field(..., alias="elementId", min_length=3)
    options: Dict[str, Any] = Field(...)

    @field_validator("element_id", mode="before")
    def _strip_element_id(cls, value: str) -> str:  # noqa: N805
        if isinstance(value, str):
            value = value.strip()
        if not value:
            raise ValueError("elementId 不能为空")
        return value


class SlideResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    slide_html: str = Field(..., alias="slide_html", min_length=20)
    charts: List[SlideChartResponse] = Field(default_factory=list)
    speaker_notes: str = Field("", min_length=0, max_length=800)
    page_title: str = Field("", max_length=120)
    slide_type: str = Field("content")
    layout_template: str = Field("standard_single_column")
    template_suggestion: str = Field("simple_content")

    @field_validator("slide_html", mode="before")
    def _trim_html(cls, value: str) -> str:  # noqa: N805
        if isinstance(value, str):
            value = value.strip()
        if not value:
            raise ValueError("slide_html 不能为空")
        return value

    @field_validator("charts", mode="before")
    def _ensure_list(cls, value):  # noqa: N805
        if value is None:
            return []
        return value


# ---------------------------------------------------------------------------
# 样式响应结构
# ---------------------------------------------------------------------------


class StyleAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    recommended_theme: StyleTheme
    color_palette: Dict[str, str] = Field(default_factory=dict)
    chart_colors: List[str] = Field(default_factory=list, min_items=4)
    font_pairing: Dict[str, str] = Field(default_factory=dict)
    layout_preference: str = "balanced"
    reasoning: str = Field(..., min_length=20, max_length=320)


# ---------------------------------------------------------------------------
# 质量评估响应结构
# ---------------------------------------------------------------------------


class QualityAssessmentResponse(BaseModel):
    overall_score: float = Field(..., ge=0.0, le=100.0)
    logic_score: float = Field(..., ge=0.0, le=100.0)
    relevance_score: float = Field(..., ge=0.0, le=100.0)
    language_score: float = Field(..., ge=0.0, le=100.0)
    layout_score: float = Field(..., ge=0.0, le=100.0)
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    pass_threshold: bool = True

    def as_dimension_map(self) -> Dict[QualityDimension, float]:
        return {
            QualityDimension.LOGIC: self.logic_score,
            QualityDimension.RELEVANCE: self.relevance_score,
            QualityDimension.LANGUAGE: self.language_score,
            QualityDimension.LAYOUT: self.layout_score,
        }


# ---------------------------------------------------------------------------
# 一致性检查响应结构
# ---------------------------------------------------------------------------


class ConsistencyAnalysisResponse(BaseModel):
    overall_score: float = Field(..., ge=0.0, le=100.0)
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


__all__ = [
    "OutlineResponse",
    "OutlineSectionResponse",
    "OutlineKeyPointResponse",
    "SlideResponse",
    "SlideChartResponse",
    "StyleAnalysisResponse",
    "QualityAssessmentResponse",
    "ConsistencyAnalysisResponse",
]
