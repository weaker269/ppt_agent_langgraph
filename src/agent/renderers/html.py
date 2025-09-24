"""基于 Jinja 的极简 HTML 渲染器。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment

from ..domain import SlideContent, StyleTheme
from ..state import OverallState

_BASE_TEMPLATE = """<!DOCTYPE html>
<html lang=\"zh\">
<head>
  <meta charset=\"utf-8\"/>
  <title>{{ title }}</title>
  <style>
    body { font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif; margin: 0; background: {{ palette.background }}; color: {{ palette.text }}; }
    header { background: {{ palette.primary }}; color: {{ palette.on_primary }}; padding: 24px; }
    section.slide { padding: 32px 8%; border-bottom: 1px solid {{ palette.border }}; }
    section.slide h2 { margin-top: 0; }
    ul { padding-left: 1.4em; }
    footer { padding: 24px 8%; background: {{ palette.surface }}; color: {{ palette.text_muted }}; font-size: 0.9rem; }
  </style>
</head>
<body>
  <header>
    <h1>{{ title }}</h1>
    <p>预计 {{ duration }} 分钟 · 总页数 {{ slide_count }}</p>
  </header>
  {% for slide in slides %}
  <section class=\"slide\">
    <h2>{{ slide.title }}</h2>
    {% if slide.body %}<p>{{ slide.body }}</p>{% endif %}
    {% if slide.bullet_points %}
    <ul>
      {% for item in slide.bullet_points %}<li>{{ item }}</li>{% endfor %}
    </ul>
    {% endif %}
    {% if slide.notes %}<p><em>{{ slide.notes }}</em></p>{% endif %}
  </section>
  {% endfor %}
  <footer>由 PPT Agent 轻量流程在本地生成</footer>
</body>
</html>
"""

_THEME_PALETTES: Dict[StyleTheme, Dict[str, str]] = {
    StyleTheme.PROFESSIONAL: {
        "primary": "#1f2937",
        "on_primary": "#ffffff",
        "background": "#f9fafb",
        "surface": "#e5e7eb",
        "border": "#d1d5db",
        "text": "#111827",
        "text_muted": "#4b5563",
    },
    StyleTheme.MODERN: {
        "primary": "#0f766e",
        "on_primary": "#ffffff",
        "background": "#f0fdfa",
        "surface": "#ccfbf1",
        "border": "#99f6e4",
        "text": "#0f172a",
        "text_muted": "#334155",
    },
    StyleTheme.CREATIVE: {
        "primary": "#7c3aed",
        "on_primary": "#f5f3ff",
        "background": "#fdf4ff",
        "surface": "#ede9fe",
        "border": "#ddd6fe",
        "text": "#2e1065",
        "text_muted": "#4c1d95",
    },
}


def _get_palette(theme: StyleTheme) -> Dict[str, str]:
    return _THEME_PALETTES.get(theme, _THEME_PALETTES[StyleTheme.PROFESSIONAL])


class HTMLRenderer:
    """负责把状态中的幻灯片列表渲染为 HTML。"""

    def __init__(self) -> None:
        self.env = Environment(autoescape=True)
        self.template = self.env.from_string(_BASE_TEMPLATE)

    def render_presentation(self, state: OverallState) -> OverallState:
        if not state.slides:
            state.record_error("缺少幻灯片内容，无法渲染 HTML")
            return state

        render_context = {
            "title": state.outline.title if state.outline else "演示文稿",
            "duration": state.outline.estimated_duration if state.outline else 10,
            "slide_count": len(state.slides),
            "slides": [slide.as_dict() for slide in state.slides],
            "palette": _get_palette(state.selected_theme),
        }

        state.html_output = self.template.render(render_context)
        return state


__all__ = ["HTMLRenderer"]
