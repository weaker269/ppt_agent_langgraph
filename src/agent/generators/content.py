"""滑动窗口内容生成与反思优化。"""

from __future__ import annotations

import time
from typing import Iterable, List, Tuple

from ..ai_client import AIConfig, AIModelClient
from ..domain import PresentationOutline, SlideContent, SlideLayout, SlideType, SlidingSummary
from ..evaluators import QualityEvaluator
from ..models import SlideResponse
from ..state import GenerationMetadata, OverallState
from ..utils import logger, text_tools

_GENERATION_SYSTEM_PROMPT = """
你是一位专业的演示文稿内容生成专家，需要根据章节要点编写结构化幻灯片。
输出 JSON，字段包括 title, body, bullet_points, speaker_notes, slide_type, layout。
"""

_GENERATION_PROMPT_TEMPLATE = """
请为一页幻灯片生成内容。

**演示背景:**
* **主题**: {title}
* **目标受众**: {audience}
* **当前章节**: {section_title} ({section_summary})

**当前任务:**
* **幻灯片编号**: {slide_id}
* **核心要点**: {key_point}
* **上下文 (最近几页幻灯片)**:
{context}

**指令:**
1.  **生成内容**: 围绕“核心要点”创作幻灯片内容，确保内容精炼、逻辑清晰。
2.  **结构化要点**: 将核心信息组织成 3-5 个项目符号（bullet_points）。
3.  **编写备注**: 为讲者提供一些提示或补充信息（speaker_notes）。
4.  **定义类型与布局**: 从提供的枚举值中选择最合适的 `slide_type` 和 `layout`。
5.  **格式化输出**: 严格按照下面定义的 JSON 格式输出。

**输出 JSON 格式:**
```json
{{
  "title": "string // 幻灯片标题，突出本页核心观点",
  "body": "string // 幻灯片正文，对标题的补充说明，可选",
  "bullet_points": [
    "string // 要点1",
    "string // 要点2",
    "string // 要点3"
  ],
  "speaker_notes": "string // 给演讲者的备注信息",
  "slide_type": "string // 幻灯片类型，从 [\"title\", \"intro\", \"section\", \"content\", \"comparison\", \"data\", \"summary\", \"conclusion\"] 中选择",
  "layout": "string // 幻灯片布局，从 [\"title\", \"standard\", \"two_column\", \"image_text\", \"bullet\", \"data_table\"] 中选择"
}}
"""

_REFLECTION_PROMPT_TEMPLATE = """
您需要根据提供的质量反馈来优化一页幻灯片。

**原始幻灯片内容:**
* **标题**: {title}
* **正文**: {body}
* **要点**: {points}

**质量反馈:**
---
{feedback}
---

**指令:**
1.  **分析反馈**: 理解每一条反馈的改进要求。
2.  **优化内容**: 在保留核心信息的前提下，修改幻灯片的内容以解决反馈中指出的问题。
3.  **重新生成**: 严格按照指定的 JSON 格式，重新生成完整的幻灯片内容。

**输出 JSON 格式:**
```json
{{
  "title": "string // 优化后的幻灯片标题",
  "body": "string // 优化后的正文内容",
  "bullet_points": [
    "string // 优化后的要点1",
    "string // 优化后的要点2"
  ],
  "speaker_notes": "string // 优化后的讲者备注",
  "slide_type": "string // 幻灯片类型 (从 [\"title\", \"intro\", \"section\", \"content\", ...])",
  "layout": "string // 幻灯片布局 (从 [\"title\", \"standard\", \"two_column\", ...])"
}}
"""


class SlidingWindowContentGenerator:
    """串行生成幻灯片内容，并按需进行反思优化。"""

    def __init__(self, client: AIModelClient | None = None, quality_evaluator: QualityEvaluator | None = None, window_size: int = 3) -> None:
        self.client = client or AIModelClient(AIConfig(enable_stub=True))
        self.quality_evaluator = quality_evaluator or QualityEvaluator(self.client)
        self.window_size = window_size

    def generate_all_slides(self, state: OverallState) -> OverallState:
        outline = state.outline
        if not outline or not outline.sections:
            state.record_error("缺少有效大纲，无法生成幻灯片")
            return state

        start_time = time.time()
        state.slides = []
        self._create_intro_slide(state, outline)

        for section in outline.sections:
            self._create_section_slide(state, section)
            for key_point in section.key_points:
                self._create_content_slide(state, outline, section, key_point)

        self._create_summary_slide(state, outline)
        logger.info("内容生成完成，共 %s 页，耗时 %.2fs", len(state.slides), time.time() - start_time)
        return state

    # ------------------------------------------------------------------
    # 幻灯片生成
    # ------------------------------------------------------------------

    def _create_intro_slide(self, state: OverallState, outline: PresentationOutline) -> None:
        slide = SlideContent(
            slide_id=1,
            title=outline.title,
            body=outline.subtitle or "概述演示目标与结构",
            bullet_points=[section.title for section in outline.sections[:4]],
            speaker_notes="简要介绍议程，突出听众收益",
            slide_type=SlideType.TITLE,
            layout=SlideLayout.TITLE,
        )
        state.add_slide(slide)
        state.add_summary(self._build_summary(slide), self.window_size)

    def _create_section_slide(self, state: OverallState, section) -> None:
        slide_id = len(state.slides) + 1
        slide = SlideContent(
            slide_id=slide_id,
            title=section.title,
            body=section.summary,
            bullet_points=[],
            speaker_notes="引入本章节背景",
            slide_type=SlideType.SECTION,
            layout=SlideLayout.TITLE,
        )
        state.add_slide(slide)
        state.add_summary(self._build_summary(slide), self.window_size)

    def _create_content_slide(self, state: OverallState, outline: PresentationOutline, section, key_point: str) -> None:
        slide_id = len(state.slides) + 1
        context_slides = state.slides[-self.window_size :]
        prompt = _GENERATION_PROMPT_TEMPLATE.format(
            title=outline.title,
            audience=outline.target_audience,
            section_title=section.title,
            section_summary=section.summary,
            key_point=key_point,
            slide_id=slide_id,
            context=self._format_context(context_slides),
        )
        slide, attempts = self._generate_with_reflection(state, prompt, slide_id, key_point, context_slides)
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

    def _create_summary_slide(self, state: OverallState, outline: PresentationOutline) -> None:
        slide_id = len(state.slides) + 1
        highlights = [f"{section.title}: {section.key_points[0]}" for section in outline.sections if section.key_points]
        slide = SlideContent(
            slide_id=slide_id,
            title="总结与下一步",
            body="回顾核心洞见，明确下一步行动",
            bullet_points=highlights[:5] or ["回顾主要结论", "提出行动建议"],
            speaker_notes="强调成果与行动号召",
            slide_type=SlideType.CONCLUSION,
            layout=SlideLayout.STANDARD,
        )
        state.add_slide(slide)

    # ------------------------------------------------------------------
    # 反思优化
    # ------------------------------------------------------------------

    def _generate_with_reflection(
        self,
        state: OverallState,
        prompt: str,
        slide_id: int,
        key_point: str,
        context_slides: Iterable[SlideContent],
    ) -> Tuple[SlideContent, Dict[str, float]]:
        retries = 0
        start = time.time()
        slide = self._invoke_model(prompt, slide_id)

        while state.enable_quality_reflection and retries < state.max_reflection_attempts:
            score, feedback = self.quality_evaluator.evaluate(state, slide, context_slides=context_slides)
            state.slide_quality[slide.slide_id] = score
            if score.pass_threshold and score.total_score >= state.quality_threshold:
                slide.quality_score = score.total_score
                break
            retries += 1
            state.quality_feedback[slide.slide_id] = feedback
            logger.info(
                "幻灯片 %s 得分 %.1f，低于 %.1f，触发第 %s 次重试",
                slide.slide_id,
                score.total_score,
                state.quality_threshold,
                retries,
            )
            slide = self._regenerate(slide, feedback)
        else:
            if slide.slide_id not in state.slide_quality:
                score, feedback = self.quality_evaluator.evaluate(state, slide, context_slides=context_slides)
                state.slide_quality[slide.slide_id] = score
                state.quality_feedback[slide.slide_id] = feedback
                slide.quality_score = score.total_score

        return slide, {"retry": retries, "duration": time.time() - start}

    def _invoke_model(self, prompt: str, slide_id: int) -> SlideContent:
        response = self.client.structured_completion(prompt, SlideResponse, system=_GENERATION_SYSTEM_PROMPT)
        return self._convert_slide(response, slide_id)

    def _regenerate(self, slide: SlideContent, feedback: List) -> SlideContent:
        feedback_text = "\n".join(f"- {item.issue_description} => {item.suggestion}" for item in feedback)
        prompt = _REFLECTION_PROMPT_TEMPLATE.format(
            title=slide.title,
            body=slide.body,
            points="; ".join(slide.bullet_points),
            feedback=feedback_text,
        )
        response = self.client.structured_completion(prompt, SlideResponse, system=_GENERATION_SYSTEM_PROMPT)
        regenerated = self._convert_slide(response, slide.slide_id)
        regenerated.reflection_count = slide.reflection_count + 1
        return regenerated

    @staticmethod
    def _convert_slide(response: SlideResponse, slide_id: int) -> SlideContent:
        slide_type = SlideType(response.slide_type) if response.slide_type in SlideType._value2member_map_ else SlideType.CONTENT
        layout = SlideLayout(response.layout) if response.layout in SlideLayout._value2member_map_ else SlideLayout.STANDARD
        return SlideContent(
            slide_id=slide_id,
            title=response.title,
            body=response.body,
            bullet_points=response.bullet_points,
            speaker_notes=response.speaker_notes,
            slide_type=slide_type,
            layout=layout,
        )

    def _build_summary(self, slide: SlideContent) -> SlidingSummary:
        message = slide.body.split("\n")[0] if slide.body else slide.title
        return SlidingSummary(
            slide_id=slide.slide_id,
            main_message=message[:120],
            key_concepts=slide.bullet_points[:3],
            logical_link="continuation",
        )

    @staticmethod
    def _format_context(slides: Iterable[SlideContent]) -> str:
        if not slides:
            return "无"
        parts = []
        for slide in slides:
            parts.append(f"第{slide.slide_id}页《{slide.title}》：{slide.body[:80]}")
        return "\n".join(parts)


__all__ = ["SlidingWindowContentGenerator"]
