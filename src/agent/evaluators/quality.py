
"""幻灯片质量评估器。"""

from __future__ import annotations

import json
from typing import Iterable, List, Tuple

from ..ai_client import AIModelClient
from ..domain import QualityDimension, QualityFeedback, QualityScore, SlideContent
from ..models import QualityAssessmentResponse
from ..state import OverallState
from ..utils import logger, snapshot_manager

_QUALITY_SYSTEM_PROMPT = """
你是一位严格的演示文稿质量评估专家，需要从逻辑、相关性、语言和版式四个维度给出评分与改进建议。
请基于提供的 HTML 结构与讲者备注进行判断。
"""

_QUALITY_USER_PROMPT_TEMPLATE = """
请评估以下幻灯片：

**演示信息**
- 标题：{title}
- 目标受众：{audience}
- 幻灯片编号：{slide_id}
- 所属章节：{section_title}
- 核心要点：{key_point}

**当前幻灯片 HTML 结构**
```
{slide_html}
```

**图表配置**
{charts}

**讲者备注**
{speaker_notes}

**上下文摘要（供参考）**
{context}

请从逻辑连贯性、内容相关性、语言表达与版式信息表达四个维度进行评分（0-100），同时指出优点、缺陷和改进建议。输出必须为 JSON。
"""


class QualityEvaluator:
    """对幻灯片进行质量评估并给出改进建议。"""

    def __init__(self, client: AIModelClient) -> None:
        self.client = client

    def evaluate(
        self,
        state: OverallState,
        slide: SlideContent,
        *,
        context_slides: Iterable[SlideContent],
    ) -> Tuple[QualityScore, List[QualityFeedback]]:
        outline = state.outline
        charts_dump = "无图表" if not slide.charts else json.dumps([chart.model_dump(by_alias=True) for chart in slide.charts], ensure_ascii=False, indent=2)
        prompt = _QUALITY_USER_PROMPT_TEMPLATE.format(
            title=outline.title if outline else "",
            audience=outline.target_audience if outline else "通用听众",
            slide_id=slide.slide_id,
            section_title=slide.section_title,
            key_point=slide.key_point,
            slide_html=slide.slide_html,
            charts=charts_dump,
            speaker_notes=slide.speaker_notes or "(无)",
            context=self._format_context(context_slides),
        )
        snapshot_manager.write_text(state.run_id, f"04_quality/slide_{slide.slide_id:02d}_prompt", prompt)

        response = self.client.structured_completion(prompt, QualityAssessmentResponse, system=_QUALITY_SYSTEM_PROMPT)
        snapshot_manager.write_json(state.run_id, f"04_quality/slide_{slide.slide_id:02d}_response", response.model_dump())
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
        snippets = [f"- #{slide.slide_id} 《{slide.page_title or slide.key_point}》" for slide in slides]
        return "\n".join(snippets) if snippets else "(无上下文)"

    @staticmethod
    def _build_feedback(response: QualityAssessmentResponse) -> List[QualityFeedback]:
        feedback: List[QualityFeedback] = []
        weaknesses = response.weaknesses or []
        suggestions = response.suggestions or []
        priorities = ["high", "medium", "medium", "low"]
        for idx, weakness in enumerate(weaknesses[:4]):
            suggestion = suggestions[idx] if idx < len(suggestions) else "请进一步明确改进动作"
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
