"""HTML 渲染器：输出带主题的演示文稿。"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from jinja2 import Environment, FileSystemLoader

from ..domain import SlideContent, StyleProfile, StyleTheme
from ..state import OverallState
from ..utils import ensure_directory, logger

_TEMPLATE_DIR = Path(__file__).parent / "templates"
ensure_directory(_TEMPLATE_DIR)

_BASE_TEMPLATE = """<!DOCTYPE html>
<html lang=\"zh\">
  <head>
    <meta charset=\"utf-8\" />
    <title>{{ title }}</title>
    <style>
      body { background: {{ palette.background }}; color: {{ palette.text }}; font-family: {{ fonts.body }}, sans-serif; margin: 0; }
      header { background: {{ palette.primary }}; color: {{ palette.on_primary }}; padding: 28px 8%; }
      header h1 { margin: 0; font-family: {{ fonts.title }}, sans-serif; }
      header p { margin-top: 8px; opacity: 0.85; }
      section.slide { padding: 32px 10%; border-bottom: 1px solid {{ palette.border }}; }
      section.slide h2 { margin-top: 0; font-family: {{ fonts.title }}, sans-serif; }
      ul { padding-left: 1.4em; }
      .meta { font-size: 0.9rem; color: {{ palette.text_muted }}; }
      .quality { background: {{ palette.accent }}22; border-left: 4px solid {{ palette.accent }}; padding: 12px 16px; margin: 24px 10%; font-size: 0.95rem; }
      footer { padding: 24px 10%; font-size: 0.85rem; color: {{ palette.text_muted }}; }
    </style>
  </head>
  <body>
    <header>
      <h1>{{ title }}</h1>
      <p>{{ subtitle }} · 预计 {{ duration }} 分钟 · 共 {{ slide_count }} 页</p>
    </header>
    {% if quality_summary %}
    <div class=\"quality\">
      <strong>质量评估概览：</strong>
      <p>平均分 {{ quality_summary.average }} 分，低于阈值的幻灯片：{{ quality_summary.below_threshold|join(', ') if quality_summary.below_threshold else '无' }}</p>
    </div>
    {% endif %}
    {% if consistency %}
    <div class=\"quality\">
      <strong>一致性得分：</strong> {{ consistency.score }} 分
      {% if consistency.issues %}
      <p>问题：{{ consistency.issues }}</p>
      {% endif %}
    </div>
    {% endif %}
    {% for slide in slides %}
    <section class=\"slide\">
      <h2>{{ slide.title }}</h2>
      {% if slide.body %}<p>{{ slide.body }}</p>{% endif %}
      {% if slide.bullet_points %}
      <ul>
        {% for item in slide.bullet_points %}<li>{{ item }}</li>{% endfor %}
      </ul>
      {% endif %}
      {% if slide.speaker_notes %}<p class=\"meta\">讲者备注：{{ slide.speaker_notes }}</p>{% endif %}
      {% if slide.quality_score %}<p class=\"meta\">质量得分：{{ '%.1f'|format(slide.quality_score) }}</p>{% endif %}
    </section>
    {% endfor %}
    <footer>由 PPT Agent 自动生成 · 模式：{{ style.reasoning }}</footer>
  </body>
</html>
"""

_ENV = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
_TEMPLATE_PATH = _TEMPLATE_DIR / "base.html"
if not _TEMPLATE_PATH.exists():
    _TEMPLATE_PATH.write_text(_BASE_TEMPLATE, encoding="utf-8")


class HTMLRenderer:
    """基于模板的渲染器。"""

    def __init__(self) -> None:
        self.template = _ENV.get_template("base.html")

    def render_presentation(self, state: OverallState) -> OverallState:
        if not state.slides:
            state.record_error("缺少幻灯片内容，无法渲染 HTML")
            return state

        base_profile = state.selected_style or StyleProfile(theme=StyleTheme.PROFESSIONAL)
        palette = self._build_palette(base_profile)
        fonts = {
            "title": base_profile.font_pairing.get("title", "Roboto"),
            "body": base_profile.font_pairing.get("body", "Source Sans"),
        }
        quality_summary = self._summarise_quality(state)
        consistency = self._summarise_consistency(state)
        html = self.template.render(
            title=state.outline.title if state.outline else "演示文稿",
            subtitle=state.outline.subtitle if state.outline else "",
            duration=state.outline.estimated_duration if state.outline else 15,
            slide_count=len(state.slides),
            slides=[slide.as_dict() for slide in state.slides],
            palette=palette,
            fonts=fonts,
            style=base_profile,
            quality_summary=quality_summary,
            consistency=consistency,
        )
        state.html_output = html
        logger.info("HTML 渲染完成")
        return state

    @staticmethod
    def _build_palette(style: StyleProfile) -> Dict[str, str]:
        defaults = {
            "primary": "#1f2937",
            "on_primary": "#ffffff",
            "background": "#f9fafb",
            "text": "#111827",
            "text_muted": "#4b5563",
            "border": "#d1d5db",
            "accent": "#2563eb",
        }
        defaults.update(style.color_palette or {})
        if "on_primary" not in defaults:
            defaults["on_primary"] = "#ffffff"
        return defaults

    @staticmethod
    def _summarise_quality(state: OverallState) -> Dict[str, object] | None:
        if not state.slide_quality:
            return None
        scores = [score.total_score for score in state.slide_quality.values()]
        below = [str(slide_id) for slide_id, score in state.slide_quality.items() if score.total_score < state.quality_threshold]
        return {"average": sum(scores) / len(scores), "below_threshold": below}

    @staticmethod
    def _summarise_consistency(state: OverallState) -> Dict[str, object] | None:
        if not state.consistency_report:
            return None
        issues = "; ".join(issue.description for issue in state.consistency_report.issues[:3])
        return {"score": state.consistency_report.overall_score, "issues": issues}


__all__ = ["HTMLRenderer"]
