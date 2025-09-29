"""动态样式选择。"""

from __future__ import annotations

from ..ai_client import AIConfig, AIModelClient
from ..domain import StyleProfile, StyleTheme
from ..models import ColorSwatch, FontPairing, StyleAnalysisResponse
from ..state import OverallState
from ..utils import logger

_STYLE_SYSTEM_PROMPT = """
你是一位视觉设计顾问，需要根据演示文稿的主题与章节内容推荐最合适的样式主题。
请严格输出 JSON，字段要求如下：
{
  "recommended_theme": "professional|modern|creative|academic|minimal",
  "color_palette": [
    {"name": "颜色用途", "hex": "#RRGGBB", "usage": "primary|background|accent|text|text_muted|border|on_primary"}
  ],
  "font_pairing": [
    {"role": "Headings", "font_name": "标题字体"},
    {"role": "Body Text", "font_name": "正文字体"}
  ],
  "layout_preference": "balanced|wide|dynamic|structured|compact",
  "reasoning": "不超过280字的中文说明，概述推荐理由"
}
至少提供3个配色（建议覆盖背景、正文文本、强调），字体至少包含标题与正文字体，可选提供 usage/role 解释。
"""

_STYLE_PROMPT_TEMPLATE = """
标题：{title}
目标受众：{audience}
章节：
{sections}
请分析内容类型（商业、技术、创意、学术等），并严格按照字段要求输出 JSON。
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
        palette_defaults = {
            "primary": "#1f2937",
            "background": "#f9fafb",
            "accent": "#2563eb",
            "secondary": "#a855f7",
            "text": "#111827",
            "text_muted": "#4b5563",
            "border": "#d1d5db",
            "on_primary": "#ffffff",
        }
        palette_defaults.update(self._map_palette_entries(response.color_palette))

        font_defaults = {"title": "Roboto", "body": "Source Sans"}
        font_defaults.update(self._map_font_entries(response.font_pairing))

        return StyleProfile(
            theme=response.recommended_theme,
            color_palette=palette_defaults,
            font_pairing=font_defaults,
            layout_preference=response.layout_preference,
            reasoning=response.reasoning,
        )

    @staticmethod
    def _map_palette_entries(entries: list[ColorSwatch]) -> dict[str, str]:
        mapping: dict[str, str] = {}

        for swatch in entries:
            name = swatch.name.lower()
            usage = (swatch.usage or "").lower()

            def matched(*keywords: str) -> bool:
                return any(keyword in name for keyword in keywords) or any(keyword in usage for keyword in keywords)

            key: str
            if matched("background", "bg"):
                key = "background"
            elif matched("on_primary", "onprimary"):
                key = "on_primary"
            elif matched("muted", "subtle", "support"):
                key = "text_muted"
            elif matched("text", "copy", "body"):
                key = "text"
            elif matched("border", "divider", "line"):
                key = "border"
            elif matched("secondary"):
                key = "secondary"
            elif matched("accent", "highlight"):
                key = "accent"
            elif matched("primary"):
                key = "primary"
            elif "accent" in usage:
                key = "accent"
            elif "background" in usage:
                key = "background"
            elif "text" in usage:
                key = "text"
            else:
                key = "accent" if "accent" in name or "accent" in usage else "primary"

            mapping[key] = swatch.hex

        return mapping

    @staticmethod
    def _map_font_entries(entries: list[FontPairing]) -> dict[str, str]:
        mapping: dict[str, str] = {}

        for font in entries:
            role = font.role.lower()
            if any(keyword in role for keyword in ["heading", "title", "header"]):
                mapping["title"] = font.font_name
            elif any(keyword in role for keyword in ["body", "paragraph", "text"]):
                mapping["body"] = font.font_name
            elif "caption" in role or "note" in role:
                mapping.setdefault("caption", font.font_name)
            elif "accent" in role or "display" in role:
                mapping.setdefault("accent", font.font_name)
            else:
                mapping.setdefault("body", font.font_name)

        return mapping

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
