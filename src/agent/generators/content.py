
"""幻灯片内容生成器，支持滑动窗口与质量反思。"""

from __future__ import annotations

import json
from pathlib import Path
import textwrap
import time
from typing import Any, Dict, Iterable, List, Tuple

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
* **证据检索 Query**: {evidence_query}
* **参考证据列表**:
{evidence_block}
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
- **重要规则**: 您的唯一合法输出就是下方定义的 JSON 对象。如果 JSON 字符串的值中包含双引号（"），您必须使用反斜杠进行转义（\\"）。
```json
{{
  "slide_html": "<div class=\\"slide-content\\">...</div>",
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
您是一位世界顶级的演示文稿设计师，任务是根据专家的质量反馈来改进当前幻灯片。请继续遵守页面模板与 ECharts 规则。

**原始要点**: {key_point}
**当前布局**: {layout}
**反馈摘要**:
{feedback}

**上下文信息**（前序页面摘要，保持逻辑衔接）:
{context_summary}

**参考证据**（原始幻灯片所依据的证据块）:
{evidence_block}

**当前 HTML 结构**:
{slide_html}

**指令**:
1.  **分析反馈**: 仔细阅读反馈，理解需要改进的核心问题。
2.  **证据一致性要求**（重要！）:
    * **必须基于原始证据**：所有事实性内容必须基于上方"参考证据"部分，不得臆造数据。
    * **保留证据引用**：如果原幻灯片引用了证据 [E1], [E2] 等，改进后的版本仍需保持这些引用。
    * **新增数据说明**：如果改进需要新的数据或事实支撑，请在 `speaker_notes` 中标注 "[需补充证据]" 提示。
3.  **执行修改**:
    * 如果反馈指出需要图表或数据强化，请补充或修改 `charts` 字段及对应的 HTML 容器。
    * 如果反馈强调逻辑或语言，请优化 `slide_html` 中的文本结构和 `speaker_notes`。
4.  **严格格式化输出**: 您的唯一合法输出是一个严格遵循初始生成格式的 JSON 对象。如果 JSON 字符串的值中包含双引号（"），您必须使用反斜杠进行转义（\\"）。

**输出 JSON 格式**:
```json
{{
  "slide_html": "...",
  "charts": [],
  "speaker_notes": "...",
  "page_title": "...",
  "layout_template": "...",
  "template_suggestion": "..."
}}
"""

_DEFAULT_COLORS = ["#2563eb", "#16a34a", "#f59e0b", "#f97316"]
_EVIDENCE_TOP_K = 3
_EVIDENCE_MAX_SNIPPET = 120
_EVIDENCE_PLACEHOLDER = "- (未检索到可靠证据，请谨慎表述，避免臆造数据)"



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

    def _build_evidence_query(self, section, key_point: OutlineKeyPoint) -> str:
        parts: List[str] = []
        if getattr(key_point, "point", ""):
            parts.append(key_point.point.strip())
        summary = getattr(section, "summary", "") or ""
        if summary.strip():
            parts.append(summary.strip())
        title = getattr(section, "title", "") or ""
        if title.strip():
            parts.append(title.strip())
        return " ".join(part for part in parts if part)

    def _retrieve_evidence(self, state: OverallState, query: str, slide_id: int) -> List[Dict[str, Any]]:
        if not query or not getattr(state, "retriever", None):
            return []
        try:
            retriever = state.retriever
            extra = {"slide_id": slide_id, "mode": "content_generation"}
            retrieve_with_metrics = getattr(retriever, "retrieve_with_metrics", None)
            top_k = state.window_config.max_evidence_per_slide
            if callable(retrieve_with_metrics):
                results = retrieve_with_metrics(
                    query,
                    top_k=top_k,
                    match_fn=lambda _item: True,
                    extra=extra,
                )
            else:
                results = retriever.retrieve(query, top_k=top_k)
        except Exception as exc:  # pragma: no cover - 依赖外部模型环境
            message = f"RAG 证据检索失败: {exc}"
            logger.warning(message)
            state.record_warning(message)
            return []

        evidence_items: List[Dict[str, Any]] = []
        for index, item in enumerate(results, start=1):
            snippet = self._compact_snippet(item.chunk.content)
            evidence_items.append(
                {
                    "evidence_id": f"E{index}",
                    "chunk_id": item.chunk.chunk_id,
                    "document_id": item.chunk.document_id,
                    "source_path": item.chunk.source,
                    "section_title": item.chunk.section_title,
                    "snippet": snippet,
                    "score": round(float(item.score), 4),
                    "dense_score": round(float(item.dense_score), 4),
                    "bm25_score": round(float(item.bm25_score), 4),
                }
            )
        if not evidence_items:
            warning = f"slide#{slide_id} 未检索到证据，已回退占位提示，请人工复核。"
            logger.warning(warning)
            state.record_warning(warning)
        return evidence_items

    @staticmethod
    def _compact_snippet(text: str) -> str:
        snippet = " ".join(text.strip().split())
        if len(snippet) > _EVIDENCE_MAX_SNIPPET:
            snippet = snippet[: _EVIDENCE_MAX_SNIPPET].rstrip() + "…"
        return snippet

    def _format_evidence_block(self, evidence_items: List[Dict[str, Any]]) -> str:
        if not evidence_items:
            return _EVIDENCE_PLACEHOLDER
        lines: List[str] = []
        for item in evidence_items:
            evidence_id = item.get("evidence_id", "E0")
            snippet = item.get("snippet", "")
            source_path = item.get("source_path") or ""
            section_title = item.get("section_title") or ""
            source_name = Path(source_path).name if source_path else ""
            segments = [seg for seg in [source_name, section_title] if seg]
            source_desc = " / ".join(segments)
            suffix = f" (来源: {source_desc})" if source_desc else ""
            lines.append(f"- [{evidence_id}] {snippet}{suffix}")
        return "\n".join(lines)

    def _record_evidence(self, state: OverallState, slide_id: int, query: str, evidence_items: List[Dict[str, Any]]) -> None:
        cloned_items = [dict(item) for item in evidence_items]
        state.evidence_queries[slide_id] = query
        state.slide_evidence[slide_id] = cloned_items
        snapshot_manager.write_json(
            state.run_id,
            f"03_content/slide_{slide_id:02d}_evidence",
            {"query": query, "items": cloned_items},
        )

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
            state.window_config.max_prev_slides,
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
        state.add_summary(self._build_summary(slide, []), state.window_config.max_prev_slides)

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
        state.add_summary(self._build_summary(slide, []), state.window_config.max_prev_slides)

    def _create_content_slide(self, state: OverallState, outline: PresentationOutline, section, key_point: OutlineKeyPoint) -> None:
        slide_id = len(state.slides) + 1
        # 使用滑窗摘要而不是原始幻灯片（TODO 2.2）
        context_summaries = state.sliding_summaries[-state.window_config.max_prev_slides :]
        # 同时保留原始幻灯片用于质量评估
        context_slides = state.slides[-state.window_config.max_prev_slides :]
        call_context = {"run_id": state.run_id, "stage": "03_content", "name": f"slide_{slide_id:02d}"}
        context_text = self._format_context_with_summaries(context_summaries)
        chart_colors = state.selected_style.chart_colors or _DEFAULT_COLORS
        evidence_query = self._build_evidence_query(section, key_point)
        evidence_items = self._retrieve_evidence(state, evidence_query, slide_id)
        evidence_block = self._format_evidence_block(evidence_items)
        self._record_evidence(state, slide_id, evidence_query, evidence_items)
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
            evidence_query=evidence_query or "(未生成查询)",
            evidence_block=evidence_block,
            context=context_text or "(暂无历史幻灯片)",
        )

        snapshot_manager.write_text(state.run_id, f"03_content/slide_{slide_id:02d}_prompt", prompt)

        slide, attempts = self._generate_with_reflection(
            state,
            prompt,
            slide_id,
            key_point,
            context_slides,
        )

        slide.metadata.setdefault("evidence_query", evidence_query)
        slide.metadata["evidence_refs"] = [dict(item) for item in evidence_items]
        slide.metadata["evidence_ids"] = [item["evidence_id"] for item in evidence_items]
        state.add_slide(slide)
        # 传递证据 ID 给摘要生成器
        evidence_ids = [item["evidence_id"] for item in evidence_items]
        state.add_summary(self._build_summary(slide, evidence_ids), state.window_config.max_prev_slides)
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
        call_context = {"run_id": state.run_id, "stage": "03_content", "name": f"slide_{slide_id:02d}"}
        logger.info("调用模型生成初稿：slide_id=%s，要点=%s", slide_id, key_point.point)
        response = self._invoke_model(prompt, slide_id, call_context)
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
            slide = self._regenerate(state, slide, feedback, key_point, call_context)
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

    def _invoke_model(self, prompt: str, slide_id: int, context: Dict[str, Any]) -> SlideResponse:
        return self.client.structured_completion(prompt, SlideResponse, system=_GENERATION_SYSTEM_PROMPT, context=context)

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
        context: Dict[str, Any],
    ) -> SlideContent:
        """基于质量反馈重新生成幻灯片。
        
        根据 TODO 2.2 要求，注入上下文摘要和证据信息。
        """
        reflection_context = dict(context)
        reflection_context["name"] = f"{context.get('name', f'slide_{slide.slide_id:02d}')}_reflection"
        
        # 格式化反馈
        feedback_text = "\n".join(
            f"- [{item.dimension.value}] {item.issue_description} => {item.suggestion}" for item in feedback
        )
        
        # 获取上下文摘要（TODO 2.2）
        context_summaries = state.sliding_summaries[-state.window_config.max_prev_slides :]
        context_summary = self._format_context_with_summaries(context_summaries)
        
        # 获取证据信息（从原始幻灯片 metadata）
        evidence_items = slide.metadata.get("evidence_refs", [])
        evidence_block = self._format_evidence_block(evidence_items) if evidence_items else "(无原始证据)"
        
        prompt = _REFLECTION_PROMPT_TEMPLATE.format(
            key_point=key_point.point,
            layout=slide.layout_template,
            feedback=feedback_text,
            context_summary=context_summary,
            evidence_block=evidence_block,
            slide_html=slide.slide_html,
        )
        
        snapshot_manager.write_text(
            state.run_id,
            f"03_content/slide_{slide.slide_id:02d}_reflection_prompt_{slide.reflection_count + 1}",
            prompt,
        )
        logger.info("根据质量反馈重写：slide_id=%s，反馈摘要=%s", slide.slide_id, feedback_text[:160])
        
        response = self.client.structured_completion(
            prompt, SlideResponse, system=_GENERATION_SYSTEM_PROMPT, context=reflection_context
        )
        regenerated = self._convert_slide(response, slide.slide_id, key_point)
        regenerated.reflection_count = slide.reflection_count + 1
        regenerated.metadata.update(slide.metadata)
        regenerated.metadata["reflection_round"] = regenerated.reflection_count

        # 证据一致性校验（阶段 3.2）
        evidence_diff = self._validate_evidence_consistency(slide, regenerated)
        if evidence_diff["has_changes"]:
            logger.warning(
                "反思后证据引用发生变化：slide_id=%s，新增=%s，删除=%s",
                slide.slide_id,
                evidence_diff["added"],
                evidence_diff["removed"]
            )

        # 记录证据变更到快照
        snapshot_manager.write_json(
            state.run_id,
            f"03_content/slide_{slide.slide_id:02d}_reflection_evidence_diff_{regenerated.reflection_count}",
            evidence_diff
        )

        return regenerated

    @staticmethod
    def _validate_evidence_consistency(
        original: SlideContent,
        regenerated: SlideContent
    ) -> Dict[str, Any]:
        """验证反思前后的证据引用一致性。

        Args:
            original: 原始幻灯片
            regenerated: 反思后的幻灯片

        Returns:
            证据变更信息字典
        """
        original_refs = set(original.metadata.get("evidence_ids", []))
        regenerated_refs = set(regenerated.metadata.get("evidence_ids", []))

        added = list(regenerated_refs - original_refs)
        removed = list(original_refs - regenerated_refs)
        retained = list(original_refs & regenerated_refs)

        has_changes = len(added) > 0 or len(removed) > 0

        # 检测是否需要补充证据（通过 speaker_notes 中的标记）
        needs_new_evidence = "[需补充证据]" in (regenerated.speaker_notes or "")

        return {
            "has_changes": has_changes,
            "added": added,
            "removed": removed,
            "retained": retained,
            "needs_new_evidence": needs_new_evidence,
            "original_count": len(original_refs),
            "regenerated_count": len(regenerated_refs)
        }

    def _build_summary(
        self,
        slide: SlideContent,
        evidence_ids: Optional[List[str]] = None
    ) -> SlidingSummary:
        """从幻灯片内容生成滑窗摘要，包含证据引用。
        
        Args:
            slide: 幻灯片内容对象
            evidence_ids: 本页引用的证据块 ID 列表
            
        Returns:
            结构化的滑窗摘要
        """
        # 提取主要信息
        headline = slide.page_title or slide.key_point or slide.section_title
        
        # 生成主旨摘要（保留完整语义，不使用 summarise_text）
        main_message = headline[:150] if headline else ""
        
        # 提取关键概念
        key_concepts = []
        if slide.section_title:
            key_concepts.append(slide.section_title)
        if slide.key_point and slide.key_point != slide.section_title:
            key_concepts.append(slide.key_point)
        # 从 speaker_notes 中提取关键词（可选）
        if slide.speaker_notes:
            # 简单提取前 2 个句子作为关键概念补充
            notes_sentences = slide.speaker_notes.split("。")[:2]
            key_concepts.extend([s.strip() for s in notes_sentences if s.strip()])
        
        # 最多保留 3 个关键概念
        key_concepts = key_concepts[:3]
        
        # 提取证据 ID
        supporting_evidence_ids = evidence_ids or []
        if not supporting_evidence_ids and "evidence_ids" in slide.metadata:
            supporting_evidence_ids = slide.metadata["evidence_ids"]
        
        # 生成过渡提示（基于内容类型）
        transition_hint = ""
        if slide.slide_type == SlideType.SECTION:
            transition_hint = "章节开始，后续展开详细内容"
        elif slide.slide_type == SlideType.CONTENT:
            transition_hint = "继续论述要点"
        elif slide.slide_type == SlideType.SUMMARY:
            transition_hint = "总结前述内容"
        
        return SlidingSummary(
            slide_id=slide.slide_id,
            main_message=main_message,
            key_concepts=key_concepts,
            logical_link="continuation",
            supporting_evidence_ids=supporting_evidence_ids,
            transition_hint=transition_hint,
        )

    # ------------------------------------------------------------------
    # 幻灯片摘要
    # ------------------------------------------------------------------
    @staticmethod
    def _format_context(slides: Iterable[SlideContent]) -> str:
        """将历史幻灯片格式化为简单标题列表（向后兼容）。
        
        Args:
            slides: 历史幻灯片列表
            
        Returns:
            格式化的上下文字符串
        """
        if not slides:
            return "(无)"
        parts = []
        for slide in slides:
            parts.append(f"- #{slide.slide_id} 《{slide.page_title or slide.key_point}》")
        return "\n".join(parts)

    @staticmethod
    def _format_context_with_summaries(summaries: List[SlidingSummary]) -> str:
        """将历史摘要格式化为结构化上下文区块。
        
        根据 TODO 2.2 要求，输出格式为：
        <SlideContext>
          - Slide #2 主旨：...（evidence: DOC_12, DOC_45）
          - Slide #3 主旨：...（evidence: DOC_67）
        </SlideContext>
        
        Args:
            summaries: 滑窗摘要列表
            
        Returns:
            结构化的上下文字符串
        """
        if not summaries:
            return "(暂无历史幻灯片)"
        
        parts = ["<SlideContext>"]
        for summary in summaries:
            # 格式化证据引用
            evidence_str = ""
            if summary.supporting_evidence_ids:
                evidence_refs = ", ".join(summary.supporting_evidence_ids[:3])  # 最多显示 3 个
                evidence_str = f"（evidence: {evidence_refs}）"
            
            # 构建摘要行
            concepts_str = "、".join(summary.key_concepts[:2]) if summary.key_concepts else ""
            main_info = summary.main_message or concepts_str
            
            parts.append(f"  - Slide #{summary.slide_id} 主旨：{main_info}{evidence_str}")
            
            # 可选：添加过渡提示
            if summary.transition_hint:
                parts.append(f"    提示：{summary.transition_hint}")
        
        parts.append("</SlideContext>")
        return "\n".join(parts)

