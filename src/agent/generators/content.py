
"""幻灯片内容生成器，支持滑动窗口与质量反思。"""

from __future__ import annotations

import json
import textwrap
import time
from typing import Dict, Iterable, List, Tuple

from ..ai_client import AIConfig, AIModelClient
from ..domain import (
    OutlineKeyPoint,
    PresentationOutline,
    SlideContent,
    SlideType,
    SlidingSummary,
)
from ..evaluators import QualityEvaluator
from ..models import SlideResponse
from ..state import GenerationMetadata, OverallState
from ..utils import logger, snapshot_manager, text_tools

_GENERATION_SYSTEM_PROMPT = """
# 角色与目标
你是一位世界顶级的演示文稿设计师与数据可视化叙事专家。请基于所给信息设计单页幻灯片，生成 HTML 结构与 ECharts 配置。

# 核心能力
1. 使用规则化的页面模板与 CSS 类构建幻灯片 HTML。
2. 主动挖掘数据关系并生成合适的 ECharts 图表，保证 JSON 纯净。
3. 输出严格遵守指定字段的 JSON 对象。
"""

_GENERATION_PROMPT_TEMPLATE = """
# 任务：生成幻灯片内容与可视化配置

## 1. 演示文稿整体背景
* **主题**: {title}
* **目标受众**: {audience}
* **整体风格主题**: {theme}
* **推荐图表配色**: {chart_colors}

## 2. 当前幻灯片任务
* **幻灯片编号**: {slide_id}
* **所属章节**: {section_title}（{section_summary}）
* **核心要点**: {key_point}
* **大纲建议模板**: {template_suggestion}
* **上下文（最近幻灯片摘要）**:
{context}

## 3. 设计系统与页面模板（必须遵守）

- **standard_dual_column**: 图文双列，HTML 结构：
  ```html
  <div class="slide-content">
    <div class="page-header"><h2>页面标题</h2></div>
    <div class="content-grid grid-2-cols">
      <div class="card">{{文本描述}}</div>
      <div class="card">{{图表容器或表格}}</div>
    </div>
  </div>
  ```
- **standard_single_column**: 单列叙事。
- **title_section**: 章节过渡页：
  ```html
  <div class="slide slide-transition">
    <h1>章节编号</h1>
    <h1>章节标题</h1>
  </div>
  ```

你必须根据要点内容选择最合适的模板，并使用 `.slide-content`、`.page-header`、`.card`、`.content-grid`、`.chart-container` 等类名。

## 4. 数据可视化策略（必须遵守）
1. 仅当有趋势、对比或占比需要时使用图表；若为表格信息，请使用 `<table class="styled-table">`。
2. 图表容器 ID 必须遵循 `chart-{slide_id}-<序号>`，例如 `chart-{slide_id}-1`。
3. ECharts `options` 必须为 JSON 纯数据，不得包含函数或注释。
4. 系列颜色必须来自 `{chart_colors}`，通过 `itemStyle.color` 指定；所有标签默认显示。

## 5. 输出要求
- 生成 `slide_html`：完整 HTML 字符串，双引号需转义为 `"`。
- 生成 `charts`：若包含图表，提供 `elementId` 与 `options`。
- 生成 `speaker_notes`：为讲述者提供专业口语化提词。
- 可补充 `page_title`、`layout_template`、`template_suggestion` 以反映最终决策。

## 6. 输出 JSON 模板
```json
{{
  "slide_html": "<div class="slide-content">...</div>",
  "charts": [
    {{
      "elementId": "chart-{slide_id}-1",
      "options": {{}}
    }}
  ],
  "speaker_notes": "string",
  "page_title": "string",
  "layout_template": "standard_dual_column",
  "template_suggestion": "text_with_chart"
}}
```
"""

_REFLECTION_PROMPT_TEMPLATE = """
你将基于质量反馈，改进当前幻灯片。请继续遵守页面模板与 ECharts 规则。

**原始要点**: {key_point}
**当前布局**: {layout}
**反馈摘要**:
{feedback}

**当前 HTML 结构**:
{slide_html}

若反馈指出需要图表或数据强化，请补充；若反馈强调逻辑或语言，请优化文本结构与讲者备注。
输出必须严格遵循与初始生成一致的 JSON 格式。
"""

_DEFAULT_COLORS = ["#2563eb", "#16a34a", "#f59e0b", "#f97316"]


class SlidingWindowContentGenerator:
    """负责生成幻灯片内容，并支持质量反思与快照。"""

    def __init__(
        self,
        client: AIModelClient | None = None,
        quality_evaluator: QualityEvaluator | None = None,
        window_size: int = 3,
    ) -> None:
        self.client = client or AIModelClient(AIConfig(enable_stub=True))
        self.quality_evaluator = quality_evaluator or QualityEvaluator(self.client)
        self.window_size = window_size

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------

    def generate_all_slides(self, state: OverallState) -> OverallState:
        outline = state.outline
        if not outline or not outline.sections:
            state.record_error("缺少有效大纲，无法生成幻灯片")
            return state

        total_sections = len(outline.sections)
        total_key_points = sum(len(section.key_points) for section in outline.sections)
        logger.info(
            "开始生成演示文稿：RunId=%s，标题《%s》，章节数=%s，关键要点总数=%s，质量反思=%s，窗口大小=%s",
            state.run_id,
            outline.title,
            total_sections,
            total_key_points,
            "开启" if state.enable_quality_reflection else "关闭",
            self.window_size,
        )
        snapshot_manager.write_json(
            state.run_id,
            "03_content/context",
            {
                "title": outline.title,
                "run_id": state.run_id,
                "sections": [section.title for section in outline.sections],
                "total_key_points": total_key_points,
            },
        )

        start_time = time.time()
        state.slides = []
        self._create_intro_slide(state, outline)

        for index, section in enumerate(outline.sections, start=1):
            logger.info(
                "进入章节 %s/%s：《%s》，关键要点=%s",
                index,
                total_sections,
                section.title,
                len(section.key_points),
            )
            self._create_section_slide(state, section_title=section.title, section_summary=section.summary, section_index=index)
            for point_index, key_point in enumerate(section.key_points, start=1):
                logger.info(
                    "章节《%s》要点 %s/%s：%s",
                    section.title,
                    point_index,
                    len(section.key_points),
                    key_point.point,
                )
                self._create_content_slide(state, outline, section, key_point)

        self._create_summary_slide(state, outline)
        logger.info("全部幻灯片生成完成：共 %s 页，用时 %.2fs", len(state.slides), time.time() - start_time)
        return state

    # ------------------------------------------------------------------
    # 幻灯片构建
    # ------------------------------------------------------------------

    def _create_intro_slide(self, state: OverallState, outline: PresentationOutline) -> None:
        slide_html = textwrap.dedent(
            f"""
            <div class="slide-content intro-slide">
              <div class="page-header">
                <h1>{outline.title}</h1>
                <p>{outline.subtitle or '演示文稿概览'}</p>
              </div>
              <div class="intro-meta">
                <div class="meta-item"><span>目标受众</span><strong>{outline.target_audience}</strong></div>
                <div class="meta-item"><span>预计时长</span><strong>{outline.estimated_duration} 分钟</strong></div>
                <div class="meta-item"><span>章节数量</span><strong>{len(outline.sections)}</strong></div>
              </div>
            </div>
            """
        ).strip()
        slide = SlideContent(
            slide_id=1,
            section_title="封面",
            section_summary="",
            key_point="演示文稿开场",
            template_suggestion="title_section",
            slide_type=SlideType.TITLE,
            layout_template="title_section",
            page_title=outline.title,
            slide_html=slide_html,
            speaker_notes=f"欢迎各位，今天我们分享《{outline.title}》。先介绍议程，再逐步展开章节。",
        )
        state.add_slide(slide)
        state.add_summary(self._build_summary(slide), self.window_size)

    def _create_section_slide(self, state: OverallState, *, section_title: str, section_summary: str, section_index: int) -> None:
        slide_id = len(state.slides) + 1
        slide_html = textwrap.dedent(
            f"""
            <div class="slide slide-transition">
              <h2>{section_index:02d}</h2>
              <h1>{section_title}</h1>
              <p>{section_summary}</p>
            </div>
            """
        ).strip()
        slide = SlideContent(
            slide_id=slide_id,
            section_title=section_title,
            section_summary=section_summary,
            key_point="章节过渡页",
            template_suggestion="title_section",
            slide_type=SlideType.SECTION,
            layout_template="title_section",
            page_title=section_title,
            slide_html=slide_html,
            speaker_notes=f"接下来进入章节《{section_title}》，我们将关注：{section_summary}",
        )
        state.add_slide(slide)
        state.add_summary(self._build_summary(slide), self.window_size)

    def _create_content_slide(self, state: OverallState, outline: PresentationOutline, section, key_point: OutlineKeyPoint) -> None:
        slide_id = len(state.slides) + 1
        context_slides = state.slides[-self.window_size :]
        context_text = self._format_context(context_slides)
        chart_colors = state.selected_style.chart_colors or _DEFAULT_COLORS
        prompt = _GENERATION_PROMPT_TEMPLATE.format(
            title=outline.title,
            audience=outline.target_audience,
            theme=state.selected_style.theme.value,
            chart_colors=json.dumps(chart_colors[:6], ensure_ascii=False),
            slide_id=slide_id,
            section_title=section.title,
            section_summary=section.summary,
            key_point=key_point.point,
            template_suggestion=key_point.template_suggestion,
            context=context_text or "(无上下文)",
        )

        snapshot_manager.write_text(state.run_id, f"03_content/slide_{slide_id:02d}_prompt", prompt)

        slide, attempts = self._generate_with_reflection(
            state,
            prompt,
            slide_id,
            key_point,
            context_slides,
        )

        state.add_slide(slide)
        state.add_summary(self._build_summary(slide), self.window_size)
        state.generation_metadata.append(
            GenerationMetadata(
                slide_id=slide.slide_id,
                model_used=f"{self.client.config.provider}:{self.client.config.model}",
                generation_time=attempts["duration"],
                retry_count=attempts["retry"],
                token_usage=0,
                quality_after_reflection=slide.quality_score,
            )
        )
        metadata = state.generation_metadata[-1].model_dump()
        snapshot_manager.write_json(state.run_id, f"03_content/slide_{slide_id:02d}_metadata", metadata)
        logger.info(
            "内容页生成完成：slide_id=%s，标题《%s》，耗时=%.2fs，反思次数=%s",
            slide.slide_id,
            slide.page_title or slide.key_point,
            attempts["duration"],
            attempts["retry"],
        )

    def _create_summary_slide(self, state: OverallState, outline: PresentationOutline) -> None:
        slide_id = len(state.slides) + 1
        highlights = []
        for section in outline.sections:
            headline = section.title
            if section.key_points:
                headline = f"{section.title}: {section.key_points[0].point}"
            highlights.append(headline)
        slide_html = textwrap.dedent(
            f"""
            <div class="slide-content summary-slide">
              <div class="page-header"><h2>重点回顾</h2></div>
              <div class="content-grid grid-1-cols">
                <div class="card">
                  <ul>
                    {''.join(f'<li>{item}</li>' for item in highlights[:8])}
                  </ul>
                </div>
              </div>
            </div>
            """
        ).strip()
        slide = SlideContent(
            slide_id=slide_id,
            section_title="总结",
            section_summary="",
            key_point="总结回顾",
            template_suggestion="standard_single_column",
            slide_type=SlideType.CONCLUSION,
            layout_template="standard_single_column",
            page_title="总结回顾",
            slide_html=slide_html,
            speaker_notes="我们快速回顾以上要点，并引出下一步行动。",
        )
        state.add_slide(slide)
        logger.info("已生成总结页：slide_id=%s，要点数量=%s", slide.slide_id, len(highlights))

    # ------------------------------------------------------------------
    # 反思与模型调用
    # ------------------------------------------------------------------

    def _generate_with_reflection(
        self,
        state: OverallState,
        prompt: str,
        slide_id: int,
        key_point: OutlineKeyPoint,
        context_slides: Iterable[SlideContent],
    ) -> Tuple[SlideContent, Dict[str, float]]:
        retries = 0
        start = time.time()
        logger.info("调用模型生成初稿：slide_id=%s，要点=%s", slide_id, key_point.point)
        response = self._invoke_model(prompt, slide_id)
        snapshot_manager.write_json(state.run_id, f"03_content/slide_{slide_id:02d}_response_{retries}", response.model_dump(by_alias=True))
        slide = self._convert_slide(response, slide_id, key_point)
        logger.info("模型初稿完成：slide_id=%s，标题《%s》", slide.slide_id, slide.page_title or slide.key_point)

        while state.enable_quality_reflection and retries < state.max_reflection_attempts:
            score, feedback = self.quality_evaluator.evaluate(state, slide, context_slides=context_slides)
            state.slide_quality[slide.slide_id] = score
            passed = score.pass_threshold and score.total_score >= state.quality_threshold
            logger.info(
                "质量评估结果：slide_id=%s，总分=%.1f/%.1f，模型判定=%s，自定义判定=%s，建议数=%s",
                slide.slide_id,
                score.total_score,
                state.quality_threshold,
                "通过" if score.pass_threshold else "未通过",
                "通过" if passed else "未通过",
                len(feedback),
            )
            if passed:
                slide.quality_score = score.total_score
                break
            retries += 1
            state.quality_feedback[slide.slide_id] = feedback
            logger.info("质量未达标，准备触发反思重写：slide_id=%s，第%s次重写", slide.slide_id, retries)
            slide = self._regenerate(state, slide, feedback, key_point)
            snapshot_manager.write_json(state.run_id, f"03_content/slide_{slide_id:02d}_response_{retries}", slide.model_dump(by_alias=True))
        else:
            if slide.slide_id not in state.slide_quality:
                score, feedback = self.quality_evaluator.evaluate(state, slide, context_slides=context_slides)
                state.slide_quality[slide.slide_id] = score
                state.quality_feedback[slide.slide_id] = feedback
                slide.quality_score = score.total_score

        logger.info(
            "最终采用内容页：slide_id=%s，反思次数=%s，总耗时=%.2fs",
            slide.slide_id,
            retries,
            time.time() - start,
        )
        return slide, {"retry": retries, "duration": time.time() - start}

    def _invoke_model(self, prompt: str, slide_id: int) -> SlideResponse:
        response = self.client.structured_completion(prompt, SlideResponse, system=_GENERATION_SYSTEM_PROMPT)
        return response

    def _convert_slide(self, response: SlideResponse, slide_id: int, key_point: OutlineKeyPoint) -> SlideContent:
        return SlideContent(
            slide_id=slide_id,
            section_title=key_point.point,
            section_summary="",
            key_point=key_point.point,
            template_suggestion=response.template_suggestion or key_point.template_suggestion,
            slide_type=SlideType.CONTENT,
            layout_template=response.layout_template or "standard_single_column",
            page_title=response.page_title or key_point.point,
            slide_html=response.slide_html,
            charts=[chart.model_dump(by_alias=True) for chart in response.charts],  # type: ignore[arg-type]
            speaker_notes=response.speaker_notes,
            metadata={"layout_template": response.layout_template, "template_suggestion": response.template_suggestion},
        )

    def _regenerate(
        self,
        state: OverallState,
        slide: SlideContent,
        feedback: List,
        key_point: OutlineKeyPoint,
    ) -> SlideContent:
        feedback_text = "\n".join(
            f"- [{item.dimension.value}] {item.issue_description} => {item.suggestion}" for item in feedback
        )
        prompt = _REFLECTION_PROMPT_TEMPLATE.format(
            key_point=key_point.point,
            layout=slide.layout_template,
            feedback=feedback_text,
            slide_html=slide.slide_html,
        )
        snapshot_manager.write_text(
            state.run_id,
            f"03_content/slide_{slide.slide_id:02d}_reflection_prompt_{slide.reflection_count + 1}",
            prompt,
        )
        logger.info("根据质量反馈重写：slide_id=%s，反馈摘要=%s", slide.slide_id, feedback_text[:160])
        response = self.client.structured_completion(prompt, SlideResponse, system=_GENERATION_SYSTEM_PROMPT)
        regenerated = self._convert_slide(response, slide.slide_id, key_point)
        regenerated.reflection_count = slide.reflection_count + 1
        regenerated.metadata.update(slide.metadata)
        regenerated.metadata["reflection_round"] = regenerated.reflection_count
        return regenerated
    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------

    def generate_all_slides(self, state: OverallState) -> OverallState:
        outline = state.outline
        if not outline or not outline.sections:
            state.record_error("缺少有效大纲，无法生成幻灯片")
            return state

        total_sections = len(outline.sections)
        total_key_points = sum(len(section.key_points) for section in outline.sections)
        logger.info(
            "开始生成演示文稿：RunId=%s，标题《%s》，章节数=%s，关键要点总数=%s，质量反思=%s，窗口大小=%s",
            state.run_id,
            outline.title,
            total_sections,
            total_key_points,
            "开启" if state.enable_quality_reflection else "关闭",
            self.window_size,
        )
        snapshot_manager.write_json(
            state.run_id,
            "03_content/context",
            {
                "title": outline.title,
                "run_id": state.run_id,
                "sections": [section.title for section in outline.sections],
                "total_key_points": total_key_points,
            },
        )

        start_time = time.time()
        state.slides = []
        self._create_intro_slide(state, outline)

        for index, section in enumerate(outline.sections, start=1):
            logger.info(
                "进入章节 %s/%s：《%s》，关键要点=%s",
                index,
                total_sections,
                section.title,
                len(section.key_points),
            )
            self._create_section_slide(state, section_title=section.title, section_summary=section.summary, section_index=index)
            for point_index, key_point in enumerate(section.key_points, start=1):
                logger.info(
                    "章节《%s》要点 %s/%s：%s",
                    section.title,
                    point_index,
                    len(section.key_points),
                    key_point.point,
                )
                self._create_content_slide(state, outline, section, key_point)

        self._create_summary_slide(state, outline)
        logger.info("全部幻灯片生成完成：共 %s 页，用时 %.2fs", len(state.slides), time.time() - start_time)
        return state

    # ------------------------------------------------------------------
    # 幻灯片构建
    # ------------------------------------------------------------------

    def _create_intro_slide(self, state: OverallState, outline: PresentationOutline) -> None:
        slide_html = textwrap.dedent(
            f"""
            <div class="slide-content intro-slide">
              <div class="page-header">
                <h1>{outline.title}</h1>
                <p>{outline.subtitle or '演示文稿概览'}</p>
              </div>
              <div class="intro-meta">
                <div class="meta-item"><span>目标受众</span><strong>{outline.target_audience}</strong></div>
                <div class="meta-item"><span>预计时长</span><strong>{outline.estimated_duration} 分钟</strong></div>
                <div class="meta-item"><span>章节数量</span><strong>{len(outline.sections)}</strong></div>
              </div>
            </div>
            """
        ).strip()
        slide = SlideContent(
            slide_id=1,
            section_title="封面",
            section_summary="",
            key_point="演示文稿开场",
            template_suggestion="title_section",
            slide_type=SlideType.TITLE,
            layout_template="title_section",
            page_title=outline.title,
            slide_html=slide_html,
            speaker_notes=f"欢迎各位，今天我们分享《{outline.title}》。先介绍议程，再逐步展开章节。",
        )
        state.add_slide(slide)
        state.add_summary(self._build_summary(slide), self.window_size)

    def _create_section_slide(self, state: OverallState, *, section_title: str, section_summary: str, section_index: int) -> None:
        slide_id = len(state.slides) + 1
        slide_html = textwrap.dedent(
            f"""
            <div class="slide slide-transition">
              <h2>{section_index:02d}</h2>
              <h1>{section_title}</h1>
              <p>{section_summary}</p>
            </div>
            """
        ).strip()
        slide = SlideContent(
            slide_id=slide_id,
            section_title=section_title,
            section_summary=section_summary,
            key_point="章节过渡页",
            template_suggestion="title_section",
            slide_type=SlideType.SECTION,
            layout_template="title_section",
            page_title=section_title,
            slide_html=slide_html,
            speaker_notes=f"接下来进入章节《{section_title}》，我们将关注：{section_summary}",
        )
        state.add_slide(slide)
        state.add_summary(self._build_summary(slide), self.window_size)

    def _create_content_slide(self, state: OverallState, outline: PresentationOutline, section, key_point: OutlineKeyPoint) -> None:
        slide_id = len(state.slides) + 1
        context_slides = state.slides[-self.window_size :]
        context_text = self._format_context(context_slides)
        chart_colors = state.selected_style.chart_colors or _DEFAULT_COLORS
        prompt = _GENERATION_PROMPT_TEMPLATE.format(
            title=outline.title,
            audience=outline.target_audience,
            theme=state.selected_style.theme.value,
            chart_colors=json.dumps(chart_colors[:6], ensure_ascii=False),
            slide_id=slide_id,
            section_title=section.title,
            section_summary=section.summary,
            key_point=key_point.point,
            template_suggestion=key_point.template_suggestion,
            context=context_text or "(无上下文)",
        )

        snapshot_manager.write_text(state.run_id, f"03_content/slide_{slide_id:02d}_prompt", prompt)

        slide, attempts = self._generate_with_reflection(
            state,
            prompt,
            slide_id,
            key_point,
            context_slides,
        )

        state.add_slide(slide)
        state.add_summary(self._build_summary(slide), self.window_size)
        state.generation_metadata.append(
            GenerationMetadata(
                slide_id=slide.slide_id,
                model_used=f"{self.client.config.provider}:{self.client.config.model}",
                generation_time=attempts["duration"],
                retry_count=attempts["retry"],
                token_usage=0,
                quality_after_reflection=slide.quality_score,
            )
        )
        metadata = state.generation_metadata[-1].model_dump()
        snapshot_manager.write_json(state.run_id, f"03_content/slide_{slide_id:02d}_metadata", metadata)
        logger.info(
            "内容页生成完成：slide_id=%s，标题《%s》，耗时=%.2fs，反思次数=%s",
            slide.slide_id,
            slide.page_title or slide.key_point,
            attempts["duration"],
            attempts["retry"],
        )

    def _create_summary_slide(self, state: OverallState, outline: PresentationOutline) -> None:
        slide_id = len(state.slides) + 1
        highlights = []
        for section in outline.sections:
            headline = section.title
            if section.key_points:
                headline = f"{section.title}: {section.key_points[0].point}"
            highlights.append(headline)
        slide_html = textwrap.dedent(
            f"""
            <div class="slide-content summary-slide">
              <div class="page-header"><h2>重点回顾</h2></div>
              <div class="content-grid grid-1-cols">
                <div class="card">
                  <ul>
                    {''.join(f'<li>{item}</li>' for item in highlights[:8])}
                  </ul>
                </div>
              </div>
            </div>
            """
        ).strip()
        slide = SlideContent(
            slide_id=slide_id,
            section_title="总结",
            section_summary="",
            key_point="总结回顾",
            template_suggestion="standard_single_column",
            slide_type=SlideType.CONCLUSION,
            layout_template="standard_single_column",
            page_title="总结回顾",
            slide_html=slide_html,
            speaker_notes="我们快速回顾以上要点，并引出下一步行动。",
        )
        state.add_slide(slide)
        logger.info("已生成总结页：slide_id=%s，要点数量=%s", slide.slide_id, len(highlights))

    # ------------------------------------------------------------------
    # 反思与模型调用
    # ------------------------------------------------------------------

    def _generate_with_reflection(
        self,
        state: OverallState,
        prompt: str,
        slide_id: int,
        key_point: OutlineKeyPoint,
        context_slides: Iterable[SlideContent],
    ) -> Tuple[SlideContent, Dict[str, float]]:
        retries = 0
        start = time.time()
        logger.info("调用模型生成初稿：slide_id=%s，要点=%s", slide_id, key_point.point)
        response = self._invoke_model(prompt, slide_id)
        snapshot_manager.write_json(state.run_id, f"03_content/slide_{slide_id:02d}_response_{retries}", response.model_dump(by_alias=True))
        slide = self._convert_slide(response, slide_id, key_point)
        logger.info("模型初稿完成：slide_id=%s，标题《%s》", slide.slide_id, slide.page_title or slide.key_point)

        while state.enable_quality_reflection and retries < state.max_reflection_attempts:
            score, feedback = self.quality_evaluator.evaluate(state, slide, context_slides=context_slides)
            state.slide_quality[slide.slide_id] = score
            passed = score.pass_threshold and score.total_score >= state.quality_threshold
            logger.info(
                "质量评估结果：slide_id=%s，总分=%.1f/%.1f，模型判定=%s，自定义判定=%s，建议数=%s",
                slide.slide_id,
                score.total_score,
                state.quality_threshold,
                "通过" if score.pass_threshold else "未通过",
                "通过" if passed else "未通过",
                len(feedback),
            )
            if passed:
                slide.quality_score = score.total_score
                break
            retries += 1
            state.quality_feedback[slide.slide_id] = feedback
            logger.info("质量未达标，准备触发反思重写：slide_id=%s，第%s次重写", slide.slide_id, retries)
            slide = self._regenerate(state, slide, feedback, key_point)
            snapshot_manager.write_json(state.run_id, f"03_content/slide_{slide_id:02d}_response_{retries}", slide.model_dump(by_alias=True))
        else:
            if slide.slide_id not in state.slide_quality:
                score, feedback = self.quality_evaluator.evaluate(state, slide, context_slides=context_slides)
                state.slide_quality[slide.slide_id] = score
                state.quality_feedback[slide.slide_id] = feedback
                slide.quality_score = score.total_score

        logger.info(
            "最终采用内容页：slide_id=%s，反思次数=%s，总耗时=%.2fs",
            slide.slide_id,
            retries,
            time.time() - start,
        )
        return slide, {"retry": retries, "duration": time.time() - start}

    def _invoke_model(self, prompt: str, slide_id: int) -> SlideResponse:
        response = self.client.structured_completion(prompt, SlideResponse, system=_GENERATION_SYSTEM_PROMPT)
        return response

    def _convert_slide(self, response: SlideResponse, slide_id: int, key_point: OutlineKeyPoint) -> SlideContent:
        return SlideContent(
            slide_id=slide_id,
            section_title=key_point.point,
            section_summary="",
            key_point=key_point.point,
            template_suggestion=response.template_suggestion or key_point.template_suggestion,
            slide_type=SlideType.CONTENT,
            layout_template=response.layout_template or "standard_single_column",
            page_title=response.page_title or key_point.point,
            slide_html=response.slide_html,
            charts=[chart.model_dump(by_alias=True) for chart in response.charts],  # type: ignore[arg-type]
            speaker_notes=response.speaker_notes,
            metadata={"layout_template": response.layout_template, "template_suggestion": response.template_suggestion},
        )

    # ------------------------------------------------------------------
    # 辅助逻辑
    # ------------------------------------------------------------------

    def _build_summary(self, slide: SlideContent) -> SlidingSummary:
        headline = slide.page_title or slide.key_point or slide.section_title
        message = text_tools.summarise_text(headline, 1)
        return SlidingSummary(
            slide_id=slide.slide_id,
            main_message=message[:120],
            key_concepts=[slide.section_title, slide.key_point][:3],
            logical_link="continuation",
        )

    @staticmethod
    @staticmethod
    def _format_context(slides: Iterable[SlideContent]) -> str:
        if not slides:
            return "(无)"
        parts = []
        for slide in slides:
            parts.append(f"- #{slide.slide_id} 《{slide.page_title or slide.key_point}》")
        return "\n".join(parts)

