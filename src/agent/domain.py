
"""领域模型定义集合，统一描述 PPT Agent 的核心结构。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# 枚举定义
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
# 大纲结构
# ---------------------------------------------------------------------------


_TEMPLATE_SUGGESTIONS = {
    "simple_content",
    "text_with_chart",
    "text_with_table",
    "full_width_image",
    "standard_single_column",
    "standard_dual_column",
    "title_section",
}


class OutlineKeyPoint(BaseModel):
    """章节下的单个要点，包含布局建议。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    point: str = Field(..., min_length=1, max_length=200, description="要点内容")
    template_suggestion: str = Field(
        "simple_content",
        min_length=1,
        max_length=40,
        description="针对该要点推荐的页面模板",
    )

    @field_validator("point", mode="before")
    def _strip_point(cls, value: str) -> str:  # noqa: N805
        if isinstance(value, str):
            value = value.strip()
        if not value:
            raise ValueError("要点内容不能为空")
        return value

    @field_validator("template_suggestion", mode="before")
    def _normalise_template(cls, value: Optional[str]) -> str:  # noqa: N805
        suggestion = (value or "simple_content").strip().lower()
        if suggestion not in _TEMPLATE_SUGGESTIONS:
            return "simple_content"
        return suggestion


class OutlineSection(BaseModel):
    index: int = Field(..., ge=1)
    title: str = Field(..., min_length=1, max_length=80)
    summary: str = Field("", max_length=300)
    key_points: List[OutlineKeyPoint] = Field(default_factory=list)
    estimated_slides: int = Field(1, ge=1, le=10)

    @field_validator("key_points", mode="before")
    def _clean_points(cls, value: Optional[List[Any]]) -> List[Any]:  # noqa: N805
        if not value:
            return []
        normalised: List[Any] = []
        for item in value:
            if isinstance(item, OutlineKeyPoint):
                normalised.append(item)
            elif isinstance(item, dict):
                normalised.append(item)
            elif isinstance(item, str):
                normalised.append({"point": item})
        return normalised


class PresentationOutline(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    subtitle: str = Field("", max_length=160)
    target_audience: str = Field("通用听众", max_length=120)
    estimated_duration: int = Field(15, ge=5, le=180)
    sections: List[OutlineSection] = Field(default_factory=list)

    @property
    def total_slides(self) -> int:
        """粗略估算总页数：标题页 + 总结页 + 各章节估算。"""

        return sum(section.estimated_slides for section in self.sections) + 2


# ---------------------------------------------------------------------------
# 幻灯片内容
# ---------------------------------------------------------------------------


class EChart(BaseModel):
    """ECharts 配置载体。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    element_id: str = Field(..., alias="elementId", min_length=3, description="容器 DOM ID")
    options: Dict[str, Any] = Field(..., description="完整的 ECharts option 对象")

    @field_validator("element_id", mode="before")
    def _strip_element_id(cls, value: str) -> str:  # noqa: N805
        if isinstance(value, str):
            value = value.strip()
        if not value:
            raise ValueError("图表 elementId 不能为空")
        return value


class SlideContent(BaseModel):
    """单页幻灯片的结构化蓝图。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    slide_id: int
    section_title: str = ""
    section_summary: str = ""
    key_point: str = ""
    template_suggestion: str = "simple_content"
    slide_type: SlideType = SlideType.CONTENT
    layout_template: str = Field("standard_single_column", description="使用的布局模板名称")
    page_title: str = Field("", max_length=120, description="幻灯片显示标题")
    slide_html: str = Field(..., description="完整的 HTML 结构字符串")
    charts: List[EChart] = Field(default_factory=list, description="本页涉及的 ECharts 配置")
    speaker_notes: str = ""
    quality_score: Optional[float] = None
    reflection_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展字段保留位")

    @field_validator("slide_html", mode="before")
    def _ensure_html(cls, value: str) -> str:  # noqa: N805
        if isinstance(value, str):
            value = value.strip()
        if not value:
            raise ValueError("slide_html 不能为空")
        return value

    def as_dict(self, *, by_alias: bool = False) -> Dict[str, Any]:
        """导出为渲染层可直接消费的字典。"""

        return self.model_dump(by_alias=by_alias)


class SlidingSummary(BaseModel):
    slide_id: int
    main_message: str
    key_concepts: List[str] = Field(default_factory=list)
    logical_link: str = ""
    supporting_evidence_ids: List[str] = Field(
        default_factory=list,
        description="本页引用的证据块 ID 列表，用于上下文追踪"
    )
    transition_hint: str = Field(
        "",
        max_length=200,
        description="到下一页的过渡提示，辅助上下文衔接"
    )


# ---------------------------------------------------------------------------
# 质量评估结构
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
# 样式配置
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 滑动窗口配置（TODO 2.3）
# ---------------------------------------------------------------------------


class WindowConfig(BaseModel):
    """滑动窗口配置参数。
    
    根据 TODO 2.3 要求，使滑窗长度、证据数量、摘要策略可配置。
    """
    
    max_prev_slides: int = Field(
        3,
        ge=1,
        le=10,
        description="滑动窗口大小，保留最近 N 页摘要用于上下文"
    )
    max_evidence_per_slide: int = Field(
        3,
        ge=1,
        le=10,
        description="每页最多检索的证据块数量"
    )
    summary_strategy: str = Field(
        "auto",
        pattern="^(auto|detailed|concise)$",
        description="摘要生成策略：auto 自动、detailed 详细、concise 简洁"
    )
    enable_transition_hints: bool = Field(
        True,
        description="是否生成过渡提示"
    )


# ---------------------------------------------------------------------------
# 样式配置
# ---------------------------------------------------------------------------

class StyleProfile(BaseModel):
    theme: StyleTheme
    color_palette: Dict[str, str] = Field(default_factory=dict)
    chart_colors: List[str] = Field(default_factory=list, description="推荐的图表颜色序列")
    font_pairing: Dict[str, str] = Field(default_factory=dict)
    layout_preference: str = "balanced"
    reasoning: str = ""


__all__ = [
    "SlideType",
    "SlideLayout",
    "StyleTheme",
    "OutlineKeyPoint",
    "OutlineSection",
    "PresentationOutline",
    "SlideContent",
    "SlidingSummary",
    "WindowConfig",
    "EChart",
    "QualityDimension",
    "QualityScore",
    "QualityFeedback",
    "ConsistencyReport",
    "ConsistencyIssue",
    "ConsistencyIssueType",
    "StyleProfile",
]
