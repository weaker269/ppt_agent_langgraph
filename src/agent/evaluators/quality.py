"""多维度质量评估与反思建议。"""

from __future__ import annotations

from typing import Iterable, List, Tuple

from ..ai_client import AIModelClient
from ..domain import QualityDimension, QualityFeedback, QualityScore, SlideContent
from ..models import QualityAssessmentResponse
from ..state import OverallState
from ..utils import logger

_QUALITY_SYSTEM_PROMPT = """
你是一位严格的演示文稿质量审查专家，需要从逻辑性、相关性、语言表达和布局四个维度给幻灯片打分（0-100）。
请指出亮点与不足，并给出具体改进建议。
"""

_QUALITY_USER_PROMPT_TEMPLATE = """
演示主题：{title}
目标受众：{audience}

当前幻灯片（第 {index} 页）：
标题：{slide_title}
正文：{body}
要点：{points}
备注：{notes}

上下文摘要：
{context}

请输出 JSON，字段包括 overall_score、logic_score、relevance_score、language_score、layout_score、strengths、weaknesses、suggestions、pass_threshold。
通过阈值为 85 分。
"""


class QualityEvaluator:
    """负责给幻灯片打分并给出反思提示。"""

    def __init__(self, client: AIModelClient) -> None:
        self.client = client

    def evaluate(self, state: OverallState, slide: SlideContent, *, context_slides: Iterable[SlideContent]) -> Tuple[QualityScore, List[QualityFeedback]]:
        outline = state.outline
        prompt = _QUALITY_USER_PROMPT_TEMPLATE.format(
            title=outline.title if outline else "",
            audience=outline.target_audience if outline else "通用听众",
            index=slide.slide_id,
            slide_title=slide.title,
            body=slide.body or "",
            points="; ".join(slide.bullet_points) if slide.bullet_points else "无",
            notes=slide.speaker_notes or "无",
            context=self._format_context(context_slides),
        )

        response = self.client.structured_completion(prompt, QualityAssessmentResponse, system=_QUALITY_SYSTEM_PROMPT)
        score = QualityScore(
            total_score=response.overall_score,
            dimension_scores=response.as_dimension_map(),
            pass_threshold=response.pass_threshold,
            confidence=0.7,
        )
        feedback = self._build_feedback(response)
        logger.debug("幻灯片 %s 质量得分 %.1f", slide.slide_id, score.total_score)
        return score, feedback

    @staticmethod
    def _format_context(slides: Iterable[SlideContent]) -> str:
        snippets = []
        for slide in slides:
            snippets.append(f"第{slide.slide_id}页《{slide.title}》: {slide.body[:120]}")
        return "\n".join(snippets) if snippets else "无"

    @staticmethod
    def _build_feedback(response: QualityAssessmentResponse) -> List[QualityFeedback]:
        feedback: List[QualityFeedback] = []
        weaknesses = response.weaknesses or []
        suggestions = response.suggestions or []
        priorities = ["high", "medium", "medium", "low"]
        for idx, weakness in enumerate(weaknesses[:4]):
            suggestion = suggestions[idx] if idx < len(suggestions) else "请补充更具体的内容"
            feedback.append(
                QualityFeedback(
                    dimension=list(QualityDimension)[idx % len(QualityDimension)],
                    issue_description=weakness,
                    suggestion=suggestion,
                    priority=priorities[idx % len(priorities)],
                )
            )
        return feedback


__all__ = ["QualityEvaluator"]
