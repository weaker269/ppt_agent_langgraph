
"""动态样式选择。"""

from __future__ import annotations

from typing import List

from ..ai_client import AIConfig, AIModelClient
from ..domain import StyleProfile, StyleTheme
from ..models import StyleAnalysisResponse
from ..state import OverallState
from ..utils import logger, snapshot_manager

_STYLE_SYSTEM_PROMPT = """
您是一位顶级的品牌与视觉设计总监，精通色彩心理学和信息设计。您的任务是根据演示文稿的主题与章节内容，推荐一套完整的样式主题。

**指令**:
1.  **分析内容**: 基于下方提供的标题、受众和章节摘要，判断演示文稿的整体风格需求。
2.  **推荐主题**: 从 `professional`, `modern`, `creative`, `academic`, `minimal` 中选择一个最贴切的主题风格。
3.  **设计配色**: 提供一套完整的16进制颜色代码方案，确保色彩搭配和谐且符合主题。
4.  **推荐字体**: 为标题和正文推荐合适的字体组合。
5.  **布局建议**: 推荐一种整体的布局偏好。
6.  **阐述理由**: 用简短的中文解释您的设计思路，说明色彩和字体如何服务于信息传达。
7.  **严格格式化输出**: 您的唯一合法输出就是一个严格遵循以下定义的扁平化 JSON 对象。

**输出 JSON 格式定义**:
- **重要规则**: 如果 JSON 字符串的值中包含双引号（"），您必须使用反斜杠进行转义（\\"）。
```json
{{
  "recommended_theme": "string // 必填，从 'professional', 'modern', 'creative', 'academic', 'minimal' 中选择",
  "color_palette": {{
    "primary": "string // 主色, #RRGGBB 格式",
    "background": "string // 背景色, #RRGGBB 格式",
    "text": "string // 主要文本颜色, #RRGGBB 格式",
    "text_muted": "string // 次要文本颜色, #RRGGBB 格式",
    "accent": "string // 强调色, #RRGGBB 格式",
    "on_primary": "string // 在主色上的文本颜色 (如 #FFFFFF), #RRGGBB 格式",
    "border": "string // 边框颜色 (如 #DDDDDD), #RRGGBB 格式"
  }},
  "chart_colors": "array[string] // 图表颜色序列，至少提供 4 个 #RRGGBB 格式的颜色值",
  "font_pairing": {{
    "title": "string // 标题字体名称",
    "body": "string // 正文字体名称"
  }},
  "layout_preference": "string // 布局偏好，从 'balanced', 'wide', 'dynamic', 'structured', 'compact' 中选择",
  "reasoning": "string // 设计理由，不超过280字的中文说明"
}}
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

        context = {"run_id": state.run_id, "stage": "02_style", "name": "style"}
        try:

            response = self.client.structured_completion(prompt, StyleAnalysisResponse, system=_STYLE_SYSTEM_PROMPT, context=context)

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
