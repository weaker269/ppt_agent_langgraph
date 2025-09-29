"""Pydantic 模型：规范 LLM 结构化响应。"""

from __future__ import annotations

import re

from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator

from .domain import QualityDimension, StyleTheme


class OutlineSectionResponse(BaseModel):
    section_id: int = Field(..., ge=1)
    title: str = Field(..., min_length=1, max_length=80)
    summary: str = Field("", max_length=300)
    key_points: List[str] = Field(default_factory=list)
    estimated_slides: int = Field(1, ge=1, le=10)

    @field_validator("key_points", mode="before")
    def _clean_points(cls, value: List[str]) -> List[str]:  # noqa: N805
        return [point.strip() for point in value or [] if point and point.strip()]


class OutlineResponse(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    subtitle: str = Field("", max_length=160)
    target_audience: str = Field("通用听众")
    estimated_duration: int = Field(15, ge=5, le=180)
    sections: List[OutlineSectionResponse] = Field(default_factory=list, min_items=1, max_items=10)


class SlideResponse(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    body: str = Field("", max_length=2000)
    bullet_points: List[str] = Field(default_factory=list, max_items=6)
    speaker_notes: str = Field("", max_length=400)
    slide_type: str = Field("content")
    layout: str = Field("standard")

    @field_validator("bullet_points", mode="before")
    def _clean_points(cls, value: List[str]) -> List[str]:  # noqa: N805
        points = []
        for item in value or []:
            item = item.strip().lstrip("*-•123456789. ")
            if item:
                points.append(item)
        return points[:6]

class ColorSwatch(BaseModel):
    """描述单个色板条目。"""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=1, max_length=60)
    hex: str = Field(..., min_length=4, max_length=7)
    usage: Optional[str] = Field(default=None, max_length=40)

    @field_validator("name", "hex", "usage", mode="before")
    def _strip_text(cls, value):  # noqa: N805
        if value is None:
            return value
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("hex")
    def _normalize_hex(cls, value: str) -> str:  # noqa: N805
        if not value:
            raise ValueError("颜色值不能为空")
        candidate = value.upper().strip()
        if not candidate.startswith('#'):
            candidate = f"#{candidate}"
        if not re.fullmatch(r"#(?:[0-9A-F]{3}|[0-9A-F]{6})", candidate):
            raise ValueError("颜色值必须是 #RGB 或 #RRGGBB 形式")
        return candidate


class FontPairing(BaseModel):
    """描述字体搭配条目。"""

    model_config = ConfigDict(extra="ignore")

    role: str = Field(..., min_length=1, max_length=40)
    font_name: str = Field(..., min_length=1, max_length=60)
    fallback: Optional[str] = Field(default=None, max_length=60)

    @field_validator("role", "font_name", mode="before")
    def _strip_required(cls, value: str) -> str:  # noqa: N805
        if isinstance(value, str):
            value = value.strip()
        if not value:
            raise ValueError("字段不能为空")
        return value

    @field_validator("fallback", mode="before")
    def _strip_optional(cls, value):  # noqa: N805
        if isinstance(value, str):
            return value.strip() or None
        return value


class StyleAnalysisResponse(BaseModel):
    recommended_theme: StyleTheme
    color_palette: List[ColorSwatch] = Field(default_factory=list, max_length=8)
    font_pairing: List[FontPairing] = Field(default_factory=list, max_length=6)
    layout_preference: str = "balanced"
    reasoning: str = Field(..., min_length=20, max_length=300)


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

    def as_dimension_map(self) -> dict[str, float]:
        return {
            QualityDimension.LOGIC: self.logic_score,
            QualityDimension.RELEVANCE: self.relevance_score,
            QualityDimension.LANGUAGE: self.language_score,
            QualityDimension.LAYOUT: self.layout_score,
        }


class ConsistencyAnalysisResponse(BaseModel):
    overall_score: float = Field(..., ge=0.0, le=100.0)
    issues: List[dict] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


__all__ = [
    "OutlineResponse",
    "OutlineSectionResponse",
    "SlideResponse",
    "ColorSwatch",
    "FontPairing",
    "StyleAnalysisResponse",
    "QualityAssessmentResponse",
    "ConsistencyAnalysisResponse",
]
