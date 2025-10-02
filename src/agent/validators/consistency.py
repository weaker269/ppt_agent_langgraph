"""跨页面一致性检查。"""

from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, List

from ..ai_client import AIModelClient
from ..domain import ConsistencyIssue, ConsistencyIssueType, ConsistencyReport, SlideContent
from ..models import ConsistencyAnalysisResponse
from ..state import OverallState
from ..utils import logger, snapshot_manager

_CONSISTENCY_SYSTEM = """
你是一位演示文稿一致性审查专家，需要指出逻辑断裂、术语不一致、风格冲突等问题。
"""

_CONSISTENCY_PROMPT_TEMPLATE = """
您是一位演示文稿一致性审查专家。您的任务是分析整个幻灯片列表，识别其中的不一致问题。

**演示信息:**
* **主题**: {title}
* **幻灯片总数**: {count}

**幻灯片列表概览:**
---
{slides}
---

**指令:**
1.  **全面分析**: 检查所有幻灯片之间的逻辑连贯性、术语统一性、风格一致性等。
2.  **一致性评分**: 给出整体的一致性得分 `overall_score` (0-100分)。
3.  **识别问题**:
    * 找出具体的不一致问题，并为每个问题创建一个 `issue` 对象。
    * 每个 `issue` 必须包含问题类型 (`type`)、严重程度 (`severity`)、涉及的幻灯片ID (`slide_ids`)、问题描述 (`description`) 和改进建议 (`suggestion`)。
4.  **总结反馈**: 总结整体的优点 (`strengths`) 和改进建议 (`recommendations`)。
5.  **格式化输出**: 严格按照下面定义的 JSON 格式输出。

**输出 JSON 格式:**
```json
{{
  "overall_score": "float // 整体一致性得分 (0-100)",
  "issues": [
    {{
      "type": "string // 问题类型，从 [\"logical_break\", \"style_inconsistency\", \"terminology_mismatch\", \"redundant_content\", \"structure_violation\"] 中选择",
      "severity": "string // 严重程度，从 [\"low\", \"medium\", \"high\", \"critical\"] 中选择",
      "slide_ids": [
        "integer // 相关的幻灯片ID"
      ],
      "description": "string // 对问题的具体描述",
      "suggestion": "string // 具体的改进建议"
    }}
  ],
  "strengths": [
    "string // 一致性方面的优点"
  ],
  "recommendations": [
    "string // 整体改进建议"
  ]
}}
"""


class ConsistencyChecker:
    """结合 LLM 与启发式的跨页一致性检查。"""

    def __init__(self, client: AIModelClient) -> None:
        self.client = client

    def check(self, state: OverallState) -> ConsistencyReport:
        prompt = _CONSISTENCY_PROMPT_TEMPLATE.format(
            title=state.outline.title if state.outline else "",
            count=len(state.slides),
            slides=self._format_slides(state.slides),
        )
        snapshot_manager.write_text(state.run_id, "04_consistency/prompt", prompt)
        response = self.client.structured_completion(prompt, ConsistencyAnalysisResponse, system=_CONSISTENCY_SYSTEM)
        snapshot_manager.write_json(state.run_id, "04_consistency/response", response.model_dump())
        report = ConsistencyReport(
            overall_score=response.overall_score,
            issues=[self._convert_issue(item) for item in response.issues],
            strengths=response.strengths,
            recommendations=response.recommendations,
        )
        self._augment_with_heuristics(state.slides, report)
        logger.info("一致性得分 %.1f", report.overall_score)
        return report

    @staticmethod
    def _format_slides(slides: Iterable[SlideContent]) -> str:
        lines = []
        for slide in slides:
            lines.append(f"- 第{slide.slide_id}页《{slide.title}》: {slide.body[:120]} | 要点: {', '.join(slide.bullet_points[:3])}")
        return "\n".join(lines)

    @staticmethod
    def _convert_issue(raw: Dict) -> ConsistencyIssue:
        try:
            issue_type = ConsistencyIssueType(raw.get("type", "logical_break"))
        except ValueError:
            issue_type = ConsistencyIssueType.LOGICAL_BREAK
        return ConsistencyIssue(
            issue_type=issue_type,
            severity=raw.get("severity", "medium"),
            slide_ids=[int(s) for s in raw.get("slide_ids", []) if isinstance(s, (int, str))],
            description=raw.get("description", ""),
            suggestion=raw.get("suggestion", ""),
        )

    def _augment_with_heuristics(self, slides: List[SlideContent], report: ConsistencyReport) -> None:
        # 检查重复标题
        title_counts = Counter((slide.page_title or slide.key_point or "") for slide in slides if (slide.page_title or slide.key_point))
        for title, count in title_counts.items():
            if count > 1:
                slide_ids = [slide.slide_id for slide in slides if (slide.page_title or slide.key_point or "") == title]
                report.issues.append(
                    ConsistencyIssue(
                        issue_type=ConsistencyIssueType.REDUNDANT_CONTENT,
                        severity="low",
                        slide_ids=slide_ids,
                        description=f"标题《{title}》出现 {count} 次，可能重复。",
                        suggestion="合并或调整其中一页的侧重点。",
                    )
                )


__all__ = ["ConsistencyChecker"]
