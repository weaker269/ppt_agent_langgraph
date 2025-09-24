"""全局状态管理模块。

该文件不再复制领域模型，只负责维护工作流运行状态，确保 LangGraph
各节点之间传递的结构在一个地方统一管理。
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .domain import PresentationOutline, SlideContent, StyleTheme


class OverallState(BaseModel):
    """LangGraph 节点之间传递的共享状态。"""

    # 原始输入
    input_text: str = ""
    input_file_path: str = ""

    # 核心成果
    outline: Optional[PresentationOutline] = None
    slides: List[SlideContent] = Field(default_factory=list)
    html_output: str = ""
    output_file_path: str = ""

    # 渲染设定
    selected_theme: StyleTheme = StyleTheme.PROFESSIONAL

    # 运行告警
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    def record_error(self, message: str) -> None:
        self.errors.append(message)

    def record_warning(self, message: str) -> None:
        self.warnings.append(message)

    def succeed(self) -> bool:
        return not self.errors and bool(self.slides) and bool(self.html_output)


__all__ = ["OverallState"]
