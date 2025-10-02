
"""HTML 渲染器：负责将结构化幻灯片输出为可交互页面。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader

from ..domain import SlideContent, StyleProfile, StyleTheme
from ..state import OverallState
from ..utils import ensure_directory, logger

_TEMPLATE_DIR = Path(__file__).parent / "templates"
ensure_directory(_TEMPLATE_DIR)

_BASE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
  <head>
    <meta charset="utf-8" />
    <title>{{ title }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      :root {
        color-scheme: light;
      }
      body {
        background: {{ palette.background }};
        color: {{ palette.text }};
        font-family: {{ fonts.body }}, sans-serif;
        margin: 0;
        overflow: hidden;
      }
      header {
        background: {{ palette.primary }};
        color: {{ palette.on_primary }};
        padding: 28px 6%;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      header h1 {
        margin: 0;
        font-family: {{ fonts.title }}, sans-serif;
        font-size: 1.8rem;
      }
      header p {
        margin: 4px 0 0;
        opacity: 0.85;
      }
      .deck {
        position: relative;
        height: calc(100vh - 160px);
        margin: 0 auto;
        width: min(1200px, 94vw);
      }
      .slide {
        display: none;
        position: absolute;
        inset: 0;
        overflow-y: auto;
        padding: 40px 7%;
        box-sizing: border-box;
        background: {{ palette.background }};
        transition: opacity 0.3s ease;
      }
      .slide.active {
        display: block;
      }
      .slide-content {
        background: rgba(255, 255, 255, 0.9);
        border-radius: 18px;
        padding: 32px 40px;
        box-shadow: 0 18px 38px rgba(15, 23, 42, 0.12);
      }
      .slide-transition {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        justify-content: center;
        height: 100%;
        background: linear-gradient(135deg, {{ palette.primary }}, {{ palette.accent }});
        color: {{ palette.on_primary }};
        padding: 60px 10%;
        border-radius: 24px;
        box-shadow: 0 18px 48px rgba(15, 23, 42, 0.2);
      }
      .slide-transition h1, .slide-transition h2 {
        margin: 0 0 12px;
        font-family: {{ fonts.title }}, sans-serif;
      }
      .page-header h2 {
        margin: 0 0 16px;
        font-size: 1.6rem;
        font-family: {{ fonts.title }}, sans-serif;
        color: {{ palette.primary }};
      }
      .content-grid {
        display: grid;
        gap: 24px;
      }
      .grid-2-cols {
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      }
      .grid-1-cols {
        grid-template-columns: 1fr;
      }
      .card {
        background: rgba(255, 255, 255, 0.95);
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 12px 24px rgba(15, 23, 42, 0.08);
      }
      .card h3 {
        margin-top: 0;
        font-family: {{ fonts.title }}, sans-serif;
        color: {{ palette.primary }};
      }
      ul {
        padding-left: 1.4em;
      }
      li + li {
        margin-top: 0.4em;
      }
      .styled-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.95rem;
      }
      .styled-table th, .styled-table td {
        border: 1px solid {{ palette.border }};
        padding: 12px 14px;
        text-align: left;
      }
      .styled-table th {
        background: {{ palette.accent }}15;
      }
      .speaker-notes {
        margin-top: 24px;
        font-size: 0.9rem;
        color: {{ palette.text_muted }};
      }
      .speaker-notes summary {
        cursor: pointer;
      }
      .nav-controls {
        position: fixed;
        bottom: 36px;
        left: 50%;
        transform: translateX(-50%);
        display: flex;
        align-items: center;
        gap: 16px;
        background: rgba(15, 23, 42, 0.75);
        color: #fff;
        padding: 10px 18px;
        border-radius: 999px;
        box-shadow: 0 12px 24px rgba(15, 23, 42, 0.2);
        font-size: 0.95rem;
      }
      .nav-controls button {
        background: transparent;
        border: none;
        color: inherit;
        font-size: 1.05rem;
        cursor: pointer;
        padding: 6px 10px;
      }
      .nav-controls button:hover {
        color: {{ palette.accent }};
      }
      footer {
        padding: 18px 6%;
        font-size: 0.85rem;
        color: {{ palette.text_muted }};
      }
      .intro-slide .intro-meta {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 18px;
        margin-top: 24px;
      }
      .intro-slide .meta-item {
        background: rgba(255, 255, 255, 0.85);
        border-radius: 14px;
        padding: 18px 22px;
        box-shadow: 0 12px 24px rgba(15, 23, 42, 0.08);
      }
      .intro-slide .meta-item span {
        display: block;
        font-size: 0.85rem;
        color: {{ palette.text_muted }};
      }
      .intro-slide .meta-item strong {
        display: block;
        margin-top: 6px;
        font-size: 1.1rem;
        color: {{ palette.primary }};
      }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js" defer></script>
  </head>
  <body>
    <header>
      <div>
        <h1>{{ title }}</h1>
        <p>{{ subtitle }} · 预计 {{ duration }} 分钟 · 共 {{ slide_count }} 页</p>
      </div>
      <div>
        <small>主题：{{ style.theme.value }}</small>
      </div>
    </header>
    {% if quality_summary %}
    <div class="quality" style="margin: 18px 6%; background: {{ palette.accent }}18; border-left: 4px solid {{ palette.accent }}; padding: 14px 18px; border-radius: 12px;">
      <strong>质量概览</strong>
      <p>平均分 {{ '%.1f'|format(quality_summary.average) }}，低于阈值的页码：{{ quality_summary.below_threshold|join(', ') if quality_summary.below_threshold else '无' }}</p>
    </div>
    {% endif %}
    {% if consistency %}
    <div class="quality" style="margin: 18px 6%; background: {{ palette.accent }}12; border-left: 4px solid {{ palette.accent }}; padding: 14px 18px; border-radius: 12px;">
      <strong>一致性评分</strong>：{{ consistency.score }}
      {% if consistency.issues %}<p>{{ consistency.issues }}</p>{% endif %}
    </div>
    {% endif %}
    <div class="deck">
      {% for slide in slides %}
      <section class="slide{% if loop.first %} active{% endif %}" data-slide-index="{{ loop.index0 }}">
        <div class="slide-inner">
          {{ slide.html | safe }}
          {% if slide.notes %}
          <details class="speaker-notes">
            <summary>讲者备注</summary>
            <p>{{ slide.notes }}</p>
          </details>
          {% endif %}
        </div>
      </section>
      {% endfor %}
    </div>
    <div class="nav-controls">
      <button type="button" data-action="prev">← 上一页</button>
      <span id="slide-indicator">1 / {{ slide_count }}</span>
      <button type="button" data-action="next">下一页 →</button>
    </div>
    <footer>由 PPT Agent 自动生成 · {{ style.reasoning }}</footer>
    <script>
      const slidesData = {{ slides_json | safe }};
      const slides = Array.from(document.querySelectorAll('.slide'));
      const indicator = document.getElementById('slide-indicator');
      const chartCache = new Map();
      let current = 0;

      function renderCharts(index) {
        const slideData = slidesData[index];
        if (!slideData || !slideData.charts || !window.echarts) return;
        slideData.charts.forEach(chart => {
          const element = document.getElementById(chart.elementId);
          if (!element) return;
          if (chartCache.has(chart.elementId)) {
            const instance = chartCache.get(chart.elementId);
            instance.resize();
            return;
          }
          const instance = echarts.init(element);
          instance.setOption(chart.options);
          chartCache.set(chart.elementId, instance);
        });
      }

      function showSlide(index) {
        if (index < 0 || index >= slides.length) return;
        slides[current].classList.remove('active');
        current = index;
        slides[current].classList.add('active');
        indicator.textContent = `${current + 1} / ${slides.length}`;
        renderCharts(current);
      }

      function nextSlide() {
        const target = current + 1 >= slides.length ? slides.length - 1 : current + 1;
        showSlide(target);
      }

      function prevSlide() {
        const target = current - 1 <= 0 ? 0 : current - 1;
        showSlide(target);
      }

      document.querySelector('[data-action="next"]').addEventListener('click', nextSlide);
      document.querySelector('[data-action="prev"]').addEventListener('click', prevSlide);

      document.addEventListener('keydown', event => {
        if (event.key === 'ArrowRight' || event.key === 'PageDown') {
          nextSlide();
        }
        if (event.key === 'ArrowLeft' || event.key === 'PageUp') {
          prevSlide();
        }
      });

      showSlide(0);
      window.addEventListener('resize', () => renderCharts(current));
    </script>
  </body>
</html>
"""

_ENV = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
_TEMPLATE_PATH = _TEMPLATE_DIR / "base.html"
if not _TEMPLATE_PATH.exists():
    _TEMPLATE_PATH.write_text(_BASE_TEMPLATE, encoding="utf-8")


class HTMLRenderer:
    """将状态中的幻灯片渲染为交互式 HTML。"""

    def __init__(self) -> None:
        self.template = _ENV.get_template("base.html")

    def render_presentation(self, state: OverallState) -> OverallState:
        if not state.slides:
            state.record_error("缺少幻灯片数据，无法渲染 HTML")
            return state

        base_profile = state.selected_style or StyleProfile(theme=StyleTheme.PROFESSIONAL)
        palette = self._build_palette(base_profile)
        fonts = {
            "title": base_profile.font_pairing.get("title", "Roboto"),
            "body": base_profile.font_pairing.get("body", "Source Sans"),
        }
        slides_payload = [
            {
                "id": slide.slide_id,
                "html": slide.slide_html,
                "notes": slide.speaker_notes,
                "charts": [chart.model_dump(by_alias=True) for chart in slide.charts],
                "title": slide.page_title or slide.key_point,
            }
            for slide in state.slides
        ]
        quality_summary = self._summarise_quality(state)
        consistency = self._summarise_consistency(state)
        html = self.template.render(
            title=state.outline.title if state.outline else "演示文稿",
            subtitle=state.outline.subtitle if state.outline else "",
            duration=state.outline.estimated_duration if state.outline else 15,
            slide_count=len(state.slides),
            slides=slides_payload,
            slides_json=json.dumps(slides_payload, ensure_ascii=False),
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
