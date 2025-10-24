
"""幻灯片质量评估器。"""

from __future__ import annotations

import json
from typing import Iterable, List, Tuple

from ..ai_client import AIModelClient
from ..domain import QualityDimension, QualityFeedback, QualityScore, SlideContent
from ..models import QualityAssessmentResponse
from ..state import OverallState
from ..utils import logger, snapshot_manager, text_tools

_QUALITY_SYSTEM_PROMPT = """
你是一位严格的演示文稿质量评估专家，需要从逻辑、相关性、语言和版式四个维度给出评分与改进建议。
请基于提供的 HTML 结构与讲者备注进行判断。
"""

_QUALITY_USER_PROMPT_TEMPLATE = """
您是一位严格、专业的演示文稿质量评估专家。您的任务是分析单页幻灯片的各项信息，并给出量化评估和改进建议。

**指令:**
1.  **全面分析**: 基于下方提供的幻灯片“元信息”、“HTML结构”和“讲者备注”等全部内容，进行综合评估。
2.  **维度评分 (0-100分)**:
    * `logic_score`: 逻辑连贯性，内容组织是否有条理，与上下文是否衔接。
    * `relevance_score`: 内容相关性，是否紧扣核心要点，信息密度是否恰当。
    * `language_score`: 语言表达，文案是否清晰、专业、有吸引力。
    * `layout_score`: 版式与信息设计，布局是否美观，是否有效传达信息。
3.  **给出总分**:
    * `overall_score`: 综合总分，根据各维度表现给出最终分数。
4.  **决策是否通过**:
    * `pass_threshold`: 基于 `overall_score` 判断是否通过质量阈值（通常为85分）。
5.  **总结优缺点与建议**:
    * `strengths`: 明确列出该幻灯片值得称赞的优点 (1-3条)。
    * `weaknesses`: 明确指出该幻灯片存在的具体缺陷 (1-3条)。
    * `suggestions`: 针对每条缺陷，提出具体、可执行的改进建议 (1-3条)。
6.  **严格格式化输出**: 您的唯一合法输出就是一个严格遵循以下定义的扁平化 JSON 对象。

**输出 JSON 格式定义**:
- **重要规则**: 如果 JSON 字符串的值中包含双引号（"），您必须使用反斜杠进行转义（\\"）。
```json
{{
  "overall_score": "float // 综合总分 (0-100)",
  "logic_score": "float // 逻辑维度得分",
  "relevance_score": "float // 相关性维度得分",
  "language_score": "float // 语言维度得分",
  "layout_score": "float // 版式维度得分",
  "pass_threshold": "boolean // 是否达到质量标准 (true/false)",
  "strengths": "array[string] // 优点列表",
  "weaknesses": "array[string] // 缺点列表",
  "suggestions": "array[string] // 改进建议列表"
}}

**待评估的幻灯片信息**
- 演示主题：{title}
- 目标受众：{audience}
- 幻灯片编号：{slide_id}
- 所属章节：{section_title}
- 核心要点：{key_point}

**HTML 结构**
```
{slide_html}
```

**图表配置**
{charts}

**证据检索 Query**: {evidence_query}

**参考证据**
{evidence_block}

**讲者备注**
{speaker_notes}

**上下文摘要（供参考）**
{context}

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
        evidence_items = state.slide_evidence.get(slide.slide_id, [])
        evidence_query = state.evidence_queries.get(slide.slide_id, "")
        evidence_block = text_tools.format_evidence(evidence_items)
        prompt = _QUALITY_USER_PROMPT_TEMPLATE.format(
            title=outline.title if outline else "",
            audience=outline.target_audience if outline else "通用听众",
            slide_id=slide.slide_id,
            section_title=slide.section_title,
            key_point=slide.key_point,
            slide_html=slide.slide_html,
            charts=charts_dump,
            evidence_query=evidence_query or "",
            evidence_block=evidence_block,
            speaker_notes=slide.speaker_notes or "(无)",
            context=self._format_context(context_slides),
        )
        snapshot_manager.write_text(state.run_id, f"04_quality/slide_{slide.slide_id:02d}_prompt", prompt)

        context = {"run_id": state.run_id, "stage": "04_quality", "name": f"slide_{slide.slide_id:02d}"}
        response = self.client.structured_completion(prompt, QualityAssessmentResponse, system=_QUALITY_SYSTEM_PROMPT, context=context)
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
