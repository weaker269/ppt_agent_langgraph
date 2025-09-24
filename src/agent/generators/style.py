"""样式选择器（轻量版）。"""

from __future__ import annotations

from ..domain import StyleTheme
from ..state import OverallState


class StyleSelector:
    """根据大纲特征选择一个基础主题。"""

    def select_style_theme(self, state: OverallState) -> OverallState:
        if not state.outline:
            state.selected_theme = StyleTheme.PROFESSIONAL
            return state

        title = state.outline.title.lower()
        keywords = " ".join(section.title.lower() for section in state.outline.sections)
        corpus = f"{title} {keywords}"

        state.selected_theme = self._choose_theme(corpus)
        return state

    @staticmethod
    def _choose_theme(corpus: str) -> StyleTheme:
        if any(word in corpus for word in ["研究", "学术", "analysis", "study"]):
            return StyleTheme.PROFESSIONAL
        if any(word in corpus for word in ["设计", "创新", "creative", "设计"]):
            return StyleTheme.CREATIVE
        if any(word in corpus for word in ["产品", "发布", "launch", "推广"]):
            return StyleTheme.MODERN
        return StyleTheme.PROFESSIONAL


__all__ = ["StyleSelector"]
