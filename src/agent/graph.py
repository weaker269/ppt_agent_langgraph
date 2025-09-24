"""PPT Agent 主流程（轻量版）。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .domain import PresentationOutline, SlideContent
from .generators.content import SlidingWindowContentGenerator
from .generators.outline import OutlineGenerator
from .generators.style import StyleSelector
from .renderers.html import HTMLRenderer
from .state import OverallState
from .utils import logger, result_saver


class PPTAgentGraph:
    """顺序执行的轻量工作流。"""

    def __init__(self) -> None:
        self.outline_generator = OutlineGenerator()
        self.content_generator = SlidingWindowContentGenerator()
        self.style_selector = StyleSelector()
        self.html_renderer = HTMLRenderer()

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def run(self, input_text: str = "", input_file_path: str = "") -> OverallState:
        state = OverallState(input_text=input_text, input_file_path=input_file_path)

        self._load_input(state)
        if state.errors:
            return state

        self.outline_generator.generate_outline(state)
        if state.errors:
            return state

        self.style_selector.select_style_theme(state)
        self.content_generator.generate_all_slides(state)
        if state.errors:
            return state

        self.html_renderer.render_presentation(state)
        if state.errors:
            return state

        self._persist(state)
        return state

    # ------------------------------------------------------------------
    # 内部步骤
    # ------------------------------------------------------------------
    def _load_input(self, state: OverallState) -> None:
        if state.input_text.strip():
            return

        if not state.input_file_path:
            state.record_error("请提供文本输入或文件路径")
            return

        path = Path(state.input_file_path)
        if not path.exists():
            state.record_error(f"找不到输入文件: {path}")
            return

        state.input_text = path.read_text(encoding="utf-8")
        logger.info("已从文件读取输入: %s", path)

    def _persist(self, state: OverallState) -> None:
        if not state.html_output:
            return

        title = state.outline.title if state.outline else "presentation"
        safe_name = title.replace(" ", "_")[:40] or "presentation"
        html_path = result_saver.save_html(state.html_output, safe_name)
        metadata = {
            "title": state.outline.title if state.outline else "",
            "slide_count": len(state.slides),
            "theme": state.selected_theme.value,
        }
        result_saver.save_json(metadata, f"{safe_name}_metadata")
        state.output_file_path = str(html_path)


# ----------------------------------------------------------------------
# 便捷函数
# ----------------------------------------------------------------------

def create_ppt_agent() -> PPTAgentGraph:
    return PPTAgentGraph()


def generate_ppt_from_text(text: str) -> OverallState:
    return create_ppt_agent().run(input_text=text)


def generate_ppt_from_file(file_path: str) -> OverallState:
    return create_ppt_agent().run(input_file_path=file_path)


__all__ = [
    "PPTAgentGraph",
    "create_ppt_agent",
    "generate_ppt_from_text",
    "generate_ppt_from_file",
]
