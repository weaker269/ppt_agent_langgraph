
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

_DEFAULT_FONT_STACK = [
    "Source Han Sans SC",
    "Noto Sans SC",
    "Microsoft YaHei",
    "PingFang SC",
    "Heiti SC",
    "sans-serif",
]

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
        font-family: {{ fonts.body }};
        margin: 0;
        line-height: 1.6;
      }
      header {
        background: {{ palette.primary }};
        color: {{ palette.on_primary }};
        padding: 28px 6%;
        display: flex;
        flex-wrap: wrap;
        align-items: baseline;
        justify-content: space-between;
        gap: 16px;
      }
      header h1 {
        margin: 0;
        font-family: {{ fonts.title }};
        font-size: 1.9rem;
        letter-spacing: 0.02em;
      }
      header p {
        margin: 6px 0 0;
        font-size: 0.95rem;
        opacity: 0.9;
      }
      .header-meta {
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 0.9rem;
      }
      .header-meta small {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 12px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.18);
        color: {{ palette.on_primary }};
      }
      .summary-banner {
        margin: 20px auto;
        padding: 16px 20px;
        width: min(1100px, 90vw);
        border-radius: 14px;
        background: {{ palette.accent }}14;
        border-left: 4px solid {{ palette.accent }};
        box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
      }
      .summary-banner strong {
        display: block;
        font-weight: 600;
        margin-bottom: 6px;
        color: {{ palette.primary }};
      }
      .deck {
        position: relative;
        margin: 0 auto 56px;
        width: min(1200px, 92vw);
        min-height: calc(100vh - 240px);
        padding-bottom: 120px;
      }
      .slide {
        display: none;
        position: relative;
        padding: 36px 0;
      }
      .slide.active {
        display: block;
      }
      .slide-inner {
        max-width: 960px;
        margin: 0 auto;
      }
      .slide-content {
        background: rgba(255, 255, 255, 0.94);
        border-radius: 18px;
        padding: 32px 40px;
        box-shadow: 0 18px 38px rgba(15, 23, 42, 0.12);
      }
      .slide-transition {
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: flex-start;
        gap: 16px;
        min-height: 420px;
        background: linear-gradient(135deg, {{ palette.primary }}, {{ palette.accent }});
        color: {{ palette.on_primary }};
        border-radius: 24px;
        padding: 60px 10%;
        box-shadow: 0 18px 48px rgba(15, 23, 42, 0.2);
      }
      .slide-transition h1,
      .slide-transition h2 {
        margin: 0;
        font-family: {{ fonts.title }};
      }
      .page-header h2 {
        margin: 0 0 18px;
        font-size: 1.6rem;
        font-family: {{ fonts.title }};
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
        font-family: {{ fonts.title }};
        color: {{ palette.primary }};
      }

      .chart-container {
        width: 100%;
        min-height: 320px;
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
      .styled-table th,
      .styled-table td {
        border: 1px solid {{ palette.border }};
        padding: 12px 14px;
        text-align: left;
      }
      .styled-table th {
        background: {{ palette.accent }}18;
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
        left: 50%;
        bottom: 32px;
        transform: translateX(-50%);
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 10px 20px;
        border-radius: 999px;
        background: rgba(15, 23, 42, 0.8);
        color: #fff;
        box-shadow: 0 12px 24px rgba(15, 23, 42, 0.25);
        font-size: 0.95rem;
        backdrop-filter: blur(6px);
        z-index: 20;
      }
      .nav-controls button {
        background: transparent;
        border: none;
        color: inherit;
        font-size: 1rem;
        cursor: pointer;
        padding: 6px 12px;
        border-radius: 999px;
        transition: background 0.2s ease;
      }
      .nav-controls button:hover:not(:disabled) {
        background: rgba(255, 255, 255, 0.14);
      }
      .nav-controls button:disabled {
        opacity: 0.35;
        cursor: not-allowed;
      }
      footer {
        margin: 48px auto 32px;
        width: min(960px, 88vw);
        font-size: 0.85rem;
        color: {{ palette.text_muted }};
        text-align: center;
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
      @media (max-width: 768px) {
        header {
          padding: 24px 5%;
        }
        .slide-content {
          padding: 24px;
        }
        .nav-controls {
          width: calc(100% - 32px);
          left: 16px;
          right: 16px;
          transform: none;
          justify-content: space-between;
        }
      }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js" defer></script>
  </head>
  <body>
    <header>
      <div>
        <h1>{{ title }}</h1>
        <p>
          {% if subtitle %}{{ subtitle }} · {% endif %}
          预计 {{ duration }} 分钟 · 共 {{ slide_count }} 页
        </p>
      </div>
      <div class="header-meta">
        <small>主题：{{ style.theme.value }}</small>
      </div>
    </header>
    {% if quality_summary %}
    <section class="summary-banner">
      <strong>质量评估</strong>
      <p>平均分 {{ '%.1f'|format(quality_summary.average) }}。低于阈值的幻灯片：{{ quality_summary.below_threshold|join(', ') if quality_summary.below_threshold else '无' }}</p>
    </section>
    {% endif %}
    {% if consistency %}
    <section class="summary-banner">
      <strong>一致性分析</strong>
      <p>评分 {{ consistency.score }}{% if consistency.issues %} · {{ consistency.issues }}{% endif %}</p>
    </section>
    {% endif %}
    <div class="deck">
      {% for slide in slides %}
      <section class="slide{% if loop.first %} active{% endif %}" data-slide-index="{{ loop.index0 }}">
        <div class="slide-inner">
          {{ slide.html | safe }}
          {% if slide.notes %}
          <details class="speaker-notes">
            <summary>演讲者备注</summary>
            <p>{{ slide.notes }}</p>
          </details>
          {% endif %}
        </div>
      </section>
      {% endfor %}
    </div>
    <div class="nav-controls" role="toolbar" aria-label="幻灯片导航">
      <button type="button" data-action="prev">上一页</button>
      <span id="slide-indicator">1 / {{ slide_count }}</span>
      <button type="button" data-action="next">下一页</button>
    </div>
    <footer>由 PPT Agent 自动生成 · {{ style.reasoning }}</footer>
    <script>
      const slidesData = {{ slides_json | safe }};
      const slides = Array.from(document.querySelectorAll('section.slide[data-slide-index]'));
      const indicator = document.getElementById('slide-indicator');
      const prevButton = document.querySelector('[data-action="prev"]');
      const nextButton = document.querySelector('[data-action="next"]');
      const chartCache = new Map();
      let current = 0;

      function renderCharts(index) {
        const slideData = slidesData[index];
        if (!slideData || !slideData.charts || !window.echarts) return;
        slideData.charts.forEach(chart => {
          const element = document.getElementById(chart.elementId);
          if (!element) return;
          if (chartCache.has(chart.elementId)) {
            chartCache.get(chart.elementId).resize();
            return;
          }
          const instance = echarts.init(element);
          instance.setOption(chart.options);
          chartCache.set(chart.elementId, instance);
        });
      }

      function updateNavState() {
        indicator.textContent = `${current + 1} / ${slides.length}`;
        prevButton.disabled = current === 0;
        nextButton.disabled = current === slides.length - 1;
      }

      function showSlide(index) {
        if (index < 0 || index >= slides.length) return;
        slides[current].classList.remove('active');
        current = index;
        slides[current].classList.add('active');
        renderCharts(current);
        updateNavState();
        slides[current].scrollIntoView({ behavior: 'smooth', block: 'start' });
      }

      prevButton.addEventListener('click', () => {
        if (current > 0) {
          showSlide(current - 1);
        }
      });

      nextButton.addEventListener('click', () => {
        if (current < slides.length - 1) {
          showSlide(current + 1);
        }
      });

      document.addEventListener('keydown', event => {
        if (event.key === 'ArrowRight' || event.key === 'PageDown') {
          nextButton.click();
        }
        if (event.key === 'ArrowLeft' || event.key === 'PageUp') {
          prevButton.click();
        }
        if (event.key === 'Home') {
          showSlide(0);
        }
        if (event.key === 'End') {
          showSlide(slides.length - 1);
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
            "title": self._format_font_stack(base_profile.font_pairing.get("title")),
            "body": self._format_font_stack(base_profile.font_pairing.get("body")),
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

    @classmethod
    def _format_font_stack(cls, font: str | None) -> str:
        candidates: list[str] = []
        if font:
            parts = [part.strip().strip("'") for part in font.split(',') if part.strip()]
            candidates.extend(parts)
        candidates.extend(_DEFAULT_FONT_STACK)

        generic_families = {
            "serif",
            "sans-serif",
            "monospace",
            "cursive",
            "fantasy",
            "system-ui",
            "ui-serif",
            "ui-sans-serif",
            "ui-monospace",
        }
        seen: set[str] = set()
        stack: list[str] = []

        for name in candidates:
            clean = name.strip().strip('"')
            if not clean:
                continue
            key = clean.lower()
            if key in seen:
                continue
            seen.add(key)
            if key in generic_families:
                stack.append(clean)
                continue
            needs_quotes = any(ch.isspace() for ch in clean) or any(ch in clean for ch in '.0123456789')
            if needs_quotes:
                stack.append(f'"{clean}"')
            else:
                stack.append(clean)
        return ", ".join(stack)

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
