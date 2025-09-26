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
演示主题：{title}
目标受众：{audience}
章节：{section_title}
章节摘要：{section_summary}
当前要点：{key_point}
期望幻灯片编号：{slide_id}

最近幻灯片摘要：
{context}

请生成内容精炼、逻辑清晰的一页幻灯片，确保标题突出重点，正文不超过 3 段，提供 3-5 个要点。
"""

_REFLECTION_PROMPT_TEMPLATE = """
请根据以下质量反馈改进幻灯片：
原始标题：{title}
原始正文：{body}
原始要点：{points}
反馈：{feedback}

保留主题与要点核心含义，针对问题逐条优化，并重新生成完整 JSON。
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
