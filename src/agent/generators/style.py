"""动态样式选择。"""

from __future__ import annotations

from ..ai_client import AIConfig, AIModelClient
from ..domain import StyleProfile, StyleTheme
from ..models import StyleAnalysisResponse
from ..state import OverallState
from ..utils import logger

_STYLE_SYSTEM_PROMPT = """
你是一位视觉设计顾问，需要根据演示文稿的主题与章节内容推荐最合适的样式主题。
输出 JSON，包含 recommended_theme, color_palette(数组), font_pairing(数组), layout_preference, reasoning。
"""

_STYLE_PROMPT_TEMPLATE = """
标题：{title}
目标受众：{audience}
章节：
{sections}
请分析内容类型（商业、技术、创意、学术等），并选择能够强化信息传达的视觉风格。
"""

_DEFAULT_PALETTES = {
    StyleTheme.PROFESSIONAL: StyleProfile(
        theme=StyleTheme.PROFESSIONAL,
        color_palette={"primary": "#1f2937", "background": "#f9fafb", "accent": "#2563eb"},
        font_pairing={"title": "Roboto", "body": "Source Sans"},
        layout_preference="balanced",
        reasoning="默认专业主题",
    ),
    StyleTheme.MODERN: StyleProfile(
        theme=StyleTheme.MODERN,
        color_palette={"primary": "#0f766e", "background": "#ecfdf5", "accent": "#14b8a6"},
        font_pairing={"title": "Montserrat", "body": "Inter"},
        layout_preference="wide",
        reasoning="现代风格默认方案",
    ),
    StyleTheme.CREATIVE: StyleProfile(
        theme=StyleTheme.CREATIVE,
        color_palette={"primary": "#7c3aed", "background": "#f5f3ff", "accent": "#f97316"},
        font_pairing={"title": "Poppins", "body": "Nunito"},
        layout_preference="dynamic",
        reasoning="创意主题默认方案",
    ),
    StyleTheme.ACADEMIC: StyleProfile(
        theme=StyleTheme.ACADEMIC,
        color_palette={"primary": "#1d4ed8", "background": "#eff6ff", "accent": "#0ea5e9"},
        font_pairing={"title": "Merriweather", "body": "Lato"},
        layout_preference="structured",
        reasoning="学术主题默认方案",
    ),
    StyleTheme.MINIMAL: StyleProfile(
        theme=StyleTheme.MINIMAL,
        color_palette={"primary": "#111827", "background": "#ffffff", "accent": "#9ca3af"},
        font_pairing={"title": "Helvetica", "body": "Arial"},
        layout_preference="compact",
        reasoning="极简主题默认方案",
    ),
}


class StyleSelector:
    """根据大纲与内容动态选择样式。"""

    def __init__(self, client: AIModelClient | None = None) -> None:
        self.client = client or AIModelClient(AIConfig(enable_stub=True))

    def select_style_theme(self, state: OverallState) -> OverallState:
        outline = state.outline
        if not outline:
            state.selected_style = _DEFAULT_PALETTES[StyleTheme.PROFESSIONAL]
            return state

        prompt = _STYLE_PROMPT_TEMPLATE.format(
            title=outline.title,
            audience=outline.target_audience,
            sections="\n".join(f"- {section.title}: {section.summary}" for section in outline.sections[:6]),
        )
        try:
            response = self.client.structured_completion(prompt, StyleAnalysisResponse, system=_STYLE_SYSTEM_PROMPT)
            palette = self._build_profile(response)
            state.selected_style = palette
            logger.info("样式选择：%s", palette.theme.value)
        except Exception as exc:  # pragma: no cover - 异常
            logger.error("样式选择失败，使用默认主题: %s", exc)
            state.selected_style = self._match_default(outline.title)
        return state

    def _build_profile(self, response: StyleAnalysisResponse) -> StyleProfile:
        palette_map = {
            "primary": response.color_palette[0] if response.color_palette else "#1f2937",
            "background": response.color_palette[1] if len(response.color_palette) > 1 else "#f9fafb",
            "accent": response.color_palette[2] if len(response.color_palette) > 2 else "#2563eb",
        }
        font_map = {
            "title": response.font_pairing[0] if response.font_pairing else "Roboto",
            "body": response.font_pairing[1] if len(response.font_pairing) > 1 else "Source Sans",
        }
        return StyleProfile(
            theme=response.recommended_theme,
            color_palette=palette_map,
            font_pairing=font_map,
            layout_preference=response.layout_preference,
            reasoning=response.reasoning,
        )

    def _match_default(self, title: str) -> StyleProfile:
        title_lower = title.lower()
        if any(keyword in title_lower for keyword in ["研究", "研究", "academic", "analysis"]):
            return _DEFAULT_PALETTES[StyleTheme.ACADEMIC] if StyleTheme.ACADEMIC in _DEFAULT_PALETTES else _DEFAULT_PALETTES[StyleTheme.PROFESSIONAL]
        if any(keyword in title_lower for keyword in ["创意", "设计", "creative"]):
            return _DEFAULT_PALETTES[StyleTheme.CREATIVE]
        if any(keyword in title_lower for keyword in ["产品", "创新", "modern"]):
            return _DEFAULT_PALETTES[StyleTheme.MODERN]
        return _DEFAULT_PALETTES[StyleTheme.PROFESSIONAL]


__all__ = ["StyleSelector"]
