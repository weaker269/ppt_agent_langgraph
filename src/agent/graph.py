"""PPT Agent 高级工作流。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from .ai_client import AIConfig, AIModelClient
from .domain import PresentationOutline, SlideContent
from .evaluators import QualityEvaluator
from .generators.content import SlidingWindowContentGenerator
from .generators.outline import OutlineGenerator
from .generators.style import StyleSelector
from .renderers.html import HTMLRenderer
from .state import OverallState
from .utils import logger, result_saver
from .validators import ConsistencyChecker


class PPTAgentGraph:
    """整合 LLM、质量评估、样式与一致性检查的工作流。"""

    def __init__(
        self,
        model_provider: str = "openai",
        model_name: str = "gpt-3.5-turbo",
        use_stub: bool = False,
    ) -> None:
        config = AIConfig(provider=model_provider, model=model_name, enable_stub=use_stub)
        self.client = AIModelClient(config)
        self.quality_evaluator = QualityEvaluator(self.client)
        self.outline_generator = OutlineGenerator(self.client)
        self.style_selector = StyleSelector(self.client)
        self.content_generator = SlidingWindowContentGenerator(self.client, self.quality_evaluator)
        self.consistency_checker = ConsistencyChecker(self.client)
        self.renderer = HTMLRenderer()

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------

    def run(self, input_text: str = "", input_file_path: str = "") -> OverallState:
        state = OverallState(
            input_text=input_text,
            input_file_path=input_file_path,
            model_provider=self.client.config.provider,
            model_name=self.client.config.model,
        )
        start_time = time.time()
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

        state.consistency_report = self.consistency_checker.check(state)
        self.renderer.render_presentation(state)
        if state.errors:
            return state

        self._persist(state)
        logger.info("完整流程完成，耗时 %.2fs", time.time() - start_time)
        return state

    # ------------------------------------------------------------------
    # 辅助步骤
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
        safe_name = title.replace(" ", "_")[:50] or "presentation"
        html_path = result_saver.save_html(state.html_output, safe_name)
        metadata = {
            "title": state.outline.title if state.outline else "",
            "slide_count": len(state.slides),
            "quality": {slide_id: score.total_score for slide_id, score in state.slide_quality.items()},
            "consistency": state.consistency_report.overall_score if state.consistency_report else None,
            "theme": state.selected_style.theme.value if state.selected_style else "",
        }
        result_saver.save_json(metadata, f"{safe_name}_metadata")
        state.output_file_path = str(html_path)


# ----------------------------------------------------------------------
# 便捷函数
# ----------------------------------------------------------------------

def create_ppt_agent(model_provider: str = "openai", model_name: str = "gpt-3.5-turbo", use_stub: bool = False) -> PPTAgentGraph:
    return PPTAgentGraph(model_provider=model_provider, model_name=model_name, use_stub=use_stub)


def generate_ppt_from_text(text: str, model_provider: str = "openai", model_name: str = "gpt-3.5-turbo", use_stub: bool = False) -> OverallState:
    return create_ppt_agent(model_provider, model_name, use_stub).run(input_text=text)


def generate_ppt_from_file(file_path: str, model_provider: str = "openai", model_name: str = "gpt-3.5-turbo", use_stub: bool = False) -> OverallState:
    return create_ppt_agent(model_provider, model_name, use_stub).run(input_file_path=file_path)


__all__ = [
    "PPTAgentGraph",
    "create_ppt_agent",
    "generate_ppt_from_text",
    "generate_ppt_from_file",
]
