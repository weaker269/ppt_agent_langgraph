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
您是一位严格的演示文稿质量审查专家。您的任务是分析给定的幻灯片内容，并进行多维度评估。

**演示背景:**
* **主题**: {title}
* **目标受众**: {audience}
* **上下文摘要 (相邻幻灯片)**:
{context}

**待评估幻灯片 (第 {index} 页):**
* **标题**: {slide_title}
* **正文**: {body}
* **要点**: {points}
* **备注**: {notes}

**指令:**
1.  **多维度评分 (0-100分)**:
    * `logic_score`: 逻辑性。内容是否连贯，论证是否有力。
    * `relevance_score`: 相关性。内容是否紧扣演示主题和当前章节要点。
    * `language_score`: 语言表达。语言是否专业、精炼、无错误。
    * `layout_score`: 布局建议。内容的组织结构是否清晰，是否易于理解。
2.  **计算总分**:
    * `overall_score`: 综合总分，根据各维度表现给出的整体评价。
3.  **决策与反馈**:
    * `pass_threshold`: 判断幻灯片质量是否通过阈值 (85分)。如果 `overall_score >= 85`，则为 `true`，否则为 `false`。
    * `strengths`: 列出该幻灯片的优点 (1-2个)。
    * `weaknesses`: 列出主要的缺点 (1-3个)。
    * `suggestions`: 针对缺点，提供具体、可操作的改进建议。
4.  **格式化输出**: 严格按照下面的 JSON 格式提供您的评估结果。

**输出 JSON 格式:**
```json
{{
  "overall_score": "float // 综合总分 (0-100)",
  "logic_score": "float // 逻辑性得分",
  "relevance_score": "float // 相关性得分",
  "language_score": "float // 语言表达得分",
  "layout_score": "float // 布局建议得分",
  "strengths": [
    "string // 优点1"
  ],
  "weaknesses": [
    "string // 缺点1"
  ],
  "suggestions": [
    "string // 针对缺点的改进建议1"
  ],
  "pass_threshold": "boolean // 质量是否达标 (true/false)"
}}
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
