
"""动态样式选择。"""

from __future__ import annotations

from typing import List

from ..ai_client import AIConfig, AIModelClient
from ..domain import StyleProfile, StyleTheme
from ..models import StyleAnalysisResponse
from ..state import OverallState
from ..utils import logger, snapshot_manager

_STYLE_SYSTEM_PROMPT = """
你是一位顶级的品牌与视觉设计总监，精通色彩心理学和信息设计。你的任务是根据演示文稿的主题与章节内容，推荐一套完整的样式主题。
请仅输出 JSON，包含以下字段：
{
  "recommended_theme": "professional|modern|creative|academic|minimal",
  "color_palette": {
    "primary": "#RRGGBB",
    "background": "#RRGGBB",
    "text": "#RRGGBB",
    "text_muted": "#RRGGBB",
    "accent": "#RRGGBB",
    "on_primary": "#FFFFFF",
    "border": "#DDDDDD"
  },
  "chart_colors": ["#RRGGBB", "#RRGGBB", "#RRGGBB", "#RRGGBB"],
  "font_pairing": {
    "title": "string",
    "body": "string"
  },
  "layout_preference": "balanced|wide|dynamic|structured|compact",
  "reasoning": "不超过280字的中文说明，强调色彩和字体如何服务于信息传达"
}
所有颜色必须是合法的十六进制色值，chart_colors 至少提供 4 个互有区分度的颜色。
"""

_STYLE_PROMPT_TEMPLATE = """
标题：{title}
目标受众：{audience}
章节摘要：
{sections}
请分析内容类型并输出满足字段要求的 JSON。
"""

_DEFAULT_CHART_COLORS: List[str] = ["#2563eb", "#16a34a", "#f59e0b", "#f97316"]

_DEFAULT_PALETTES = {
    StyleTheme.PROFESSIONAL: StyleProfile(
        theme=StyleTheme.PROFESSIONAL,
        color_palette={"primary": "#1f2937", "background": "#f9fafb", "accent": "#2563eb", "text": "#111827", "text_muted": "#4b5563", "border": "#d1d5db", "on_primary": "#ffffff"},
        chart_colors=_DEFAULT_CHART_COLORS,
        font_pairing={"title": "Roboto", "body": "Source Sans"},
        layout_preference="balanced",
        reasoning="默认专业主题",
    ),
    StyleTheme.MODERN: StyleProfile(
        theme=StyleTheme.MODERN,
        color_palette={"primary": "#0f766e", "background": "#ecfdf5", "accent": "#14b8a6", "text": "#134e4a", "text_muted": "#4c7a74", "border": "#99f6e4", "on_primary": "#ffffff"},
        chart_colors=["#0ea5e9", "#f97316", "#10b981", "#9333ea"],
        font_pairing={"title": "Montserrat", "body": "Inter"},
        layout_preference="wide",
        reasoning="现代风格默认方案",
    ),
    StyleTheme.CREATIVE: StyleProfile(
        theme=StyleTheme.CREATIVE,
        color_palette={"primary": "#7c3aed", "background": "#f5f3ff", "accent": "#f97316", "text": "#2e1065", "text_muted": "#6d28d9", "border": "#ddd6fe", "on_primary": "#ffffff"},
        chart_colors=["#f97316", "#22d3ee", "#facc15", "#a855f7"],
        font_pairing={"title": "Poppins", "body": "Nunito"},
        layout_preference="dynamic",
        reasoning="创意主题默认方案",
    ),
    StyleTheme.ACADEMIC: StyleProfile(
        theme=StyleTheme.ACADEMIC,
        color_palette={"primary": "#1d4ed8", "background": "#eff6ff", "accent": "#0ea5e9", "text": "#0f172a", "text_muted": "#1e3a8a", "border": "#cbd5f5", "on_primary": "#ffffff"},
        chart_colors=["#1d4ed8", "#0ea5e9", "#22c55e", "#eab308"],
        font_pairing={"title": "Merriweather", "body": "Lato"},
        layout_preference="structured",
        reasoning="学术主题默认方案",
    ),
    StyleTheme.MINIMAL: StyleProfile(
        theme=StyleTheme.MINIMAL,
        color_palette={"primary": "#111827", "background": "#ffffff", "accent": "#9ca3af", "text": "#111827", "text_muted": "#6b7280", "border": "#e5e7eb", "on_primary": "#ffffff"},
        chart_colors=["#0f172a", "#4b5563", "#94a3b8", "#d1d5db"],
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
        snapshot_manager.write_text(state.run_id, "02_style/prompt", prompt)
        try:
            response = self.client.structured_completion(prompt, StyleAnalysisResponse, system=_STYLE_SYSTEM_PROMPT)
            snapshot_manager.write_json(state.run_id, "02_style/response", response.model_dump())
            palette = self._build_profile(response)
            state.selected_style = palette
            logger.info("样式选择：%s", palette.theme.value)
        except Exception as exc:  # pragma: no cover - 异常
            logger.error("样式选择失败，使用默认主题: %s", exc)
            state.selected_style = self._match_default(outline.title)
            snapshot_manager.write_json(state.run_id, "02_style/fallback", state.selected_style.model_dump())
        return state

    def _build_profile(self, response: StyleAnalysisResponse) -> StyleProfile:
        palette_defaults = {
            "primary": "#1f2937",
            "background": "#f9fafb",
            "accent": "#2563eb",
            "text": "#111827",
            "text_muted": "#4b5563",
            "border": "#d1d5db",
            "on_primary": "#ffffff",
        }
        palette_defaults.update({k: v for k, v in response.color_palette.items() if isinstance(v, str) and v})

        chart_colors = response.chart_colors or _DEFAULT_CHART_COLORS
        if len(chart_colors) < 4:
            chart_colors = (chart_colors + _DEFAULT_CHART_COLORS)[:4]

        font_defaults = {"title": "Roboto", "body": "Source Sans"}
        for key, value in response.font_pairing.items():
            if isinstance(value, str) and value.strip():
                font_defaults[key] = value.strip()

        return StyleProfile(
            theme=response.recommended_theme,
            color_palette=palette_defaults,
            chart_colors=chart_colors,
            font_pairing=font_defaults,
            layout_preference=response.layout_preference,
            reasoning=response.reasoning,
        )

    def _match_default(self, title: str) -> StyleProfile:
        title_lower = title.lower()
        if any(keyword in title_lower for keyword in ["研究", "academic", "analysis", "报告"]):
            return _DEFAULT_PALETTES.get(StyleTheme.ACADEMIC, _DEFAULT_PALETTES[StyleTheme.PROFESSIONAL])
        if any(keyword in title_lower for keyword in ["创意", "设计", "creative"]):
            return _DEFAULT_PALETTES[StyleTheme.CREATIVE]
        if any(keyword in title_lower for keyword in ["产品", "创新", "modern"]):
            return _DEFAULT_PALETTES[StyleTheme.MODERN]
        if any(keyword in title_lower for keyword in ["极简", "minimal"]):
            return _DEFAULT_PALETTES[StyleTheme.MINIMAL]
        return _DEFAULT_PALETTES[StyleTheme.PROFESSIONAL]


__all__ = ["StyleSelector"]
