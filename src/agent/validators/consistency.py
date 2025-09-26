"""跨页面一致性检查。"""

from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, List

from ..ai_client import AIModelClient
from ..domain import ConsistencyIssue, ConsistencyIssueType, ConsistencyReport, SlideContent
from ..models import ConsistencyAnalysisResponse
from ..state import OverallState
from ..utils import logger

_CONSISTENCY_SYSTEM = """
你是一位演示文稿一致性审查专家，需要指出逻辑断裂、术语不一致、风格冲突等问题。
"""

_CONSISTENCY_PROMPT_TEMPLATE = """
请针对以下幻灯片进行一致性分析：

主题：{title}
幻灯片数量：{count}

幻灯片列表：
{slides}

输出 JSON，字段包括 overall_score、issues(数组)、strengths、recommendations。
issue 字段包含 type、severity、slide_ids、description、suggestion。
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
        response = self.client.structured_completion(prompt, ConsistencyAnalysisResponse, system=_CONSISTENCY_SYSTEM)
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
        title_counts = Counter(slide.title for slide in slides)
        for title, count in title_counts.items():
            if count > 1:
                slide_ids = [slide.slide_id for slide in slides if slide.title == title]
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
