"""核心领域模型定义。

该模块收敛整个系统使用的枚举与数据结构，以便生成器、渲染器、状态管理共享同一套定义。
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SlideType(str, Enum):
    """幻灯片类型枚举（保持最小集合以覆盖快速验证场景）。"""

    TITLE = "title"
    SECTION = "section"
    CONTENT = "content"
    SUMMARY = "summary"


class SlideLayout(str, Enum):
    """幻灯片布局枚举。"""

    TITLE = "title"
    STANDARD = "standard"
    SPLIT = "split"


class StyleTheme(str, Enum):
    """样式主题（仅用于渲染时提供基础配色）。"""

    PROFESSIONAL = "professional"
    MODERN = "modern"
    CREATIVE = "creative"


class OutlineSection(BaseModel):
    """演示大纲中的单个章节。"""

    index: int = Field(..., ge=1, description="章节顺序")
    title: str = Field(..., min_length=1, max_length=80, description="章节标题")
    summary: str = Field("", description="章节摘要")
    key_points: List[str] = Field(default_factory=list, description="关键要点")

    @property
    def slide_estimate(self) -> int:
        """基于要点数量给出粗略的幻灯片估算。"""

        return max(1, len(self.key_points))


class PresentationOutline(BaseModel):
    """整体演示大纲。"""

    title: str = Field(..., min_length=1, max_length=120)
    sections: List[OutlineSection] = Field(default_factory=list)
    estimated_duration: int = Field(10, ge=5, le=90, description="预计演示时间（分钟）")
    target_audience: str = Field("通用听众", description="目标受众")

    @property
    def total_slides(self) -> int:
        """估算幻灯片总数。"""

        return sum(section.slide_estimate for section in self.sections) + 2  # 标题+总结


class SlideContent(BaseModel):
    """用于渲染的结构化幻灯片。"""

    slide_id: int
    title: str
    body: str = ""
    bullet_points: List[str] = Field(default_factory=list)
    notes: str = ""
    slide_type: SlideType = SlideType.CONTENT
    layout: SlideLayout = SlideLayout.STANDARD
    meta: Dict[str, str] = Field(default_factory=dict)

    def as_dict(self) -> Dict[str, str]:
        """用于模板渲染的字典表示。"""

        data = self.model_dump()
        data["bullet_points"] = [item for item in self.bullet_points if item]
        return data


__all__ = [
    "SlideType",
    "SlideLayout",
    "StyleTheme",
    "OutlineSection",
    "PresentationOutline",
    "SlideContent",
]
