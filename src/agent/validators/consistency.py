"""跨页面一致性检查。"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, Iterable, List

from ..ai_client import AIModelClient
from ..domain import ConsistencyIssue, ConsistencyIssueType, ConsistencyReport, SlideContent
from ..models import ConsistencyAnalysisResponse
from ..state import OverallState
from ..utils import logger, snapshot_manager, text_tools

_CONSISTENCY_SYSTEM = """
你是一位演示文稿一致性审查专家，需要指出逻辑断裂、术语不一致、风格冲突等问题。
"""

_CONSISTENCY_PROMPT_TEMPLATE = """
您是一位经验丰富的演示文稿一致性审查专家。您的任务是分析整个幻灯片列表，识别其中的不一致问题，并提供评估报告。

**指令:**
1.  **全面分析**: 检查所有幻灯片之间的逻辑连贯性、术语统一性、风格一致性等。
2.  **一致性评分**: 给出整体的一致性得分 `overall_score` (0-100分)。
3.  **识别问题**:
    * 找出具体的不一致问题，并为每个问题创建一个 `issue` 对象。
    * 每个 `issue` 必须包含问题类型 (`type`)、严重程度 (`severity`)、涉及的幻灯片ID (`slide_ids`)、问题描述 (`description`) 和改进建议 (`suggestion`)。
4.  **总结反馈**: 总结整体的优点 (`strengths`) 和整体改进建议 (`recommendations`)。
5.  **严格格式化输出**: 您的唯一合法输出就是一个严格遵循以下定义的扁平化 JSON 对象。

**输出 JSON 格式定义**:
- **重要规则**: 如果 JSON 字符串的值中包含双引号（"），您必须使用反斜杠进行转义（\\"）。
- **证据引用要求**: 对于涉及事实性、术语、数据冲突的问题，必须标注相关的证据 ID（格式：["E1", "E3"]）。如果是纯粹的风格/结构问题，可以省略此字段。
```json
{{
  "overall_score": "float // 整体一致性得分 (0-100)",
  "issues": [
    {{
      "type": "string // 问题类型，从 [\\"logical_break\\", \\"style_inconsistency\\", \\"terminology_mismatch\\", \\"redundant_content\\", \\"structure_violation\\"] 中选择",
      "severity": "string // 严重程度，从 [\\"low\\", \\"medium\\", \\"high\\", \\"critical\\"] 中选择",
      "slide_ids": "array[integer] // 相关的幻灯片ID列表",
      "description": "string // 对问题的具体描述",
      "suggestion": "string // 具体的改进建议",
      "evidence_refs": "array[string] // 可选，问题相关的证据块 ID 列表，如 [\"E1\", \"E3\"]"
    }}
  ],
  "strengths": "array[string] // 一致性方面的优点列表",
  "recommendations": "array[string] // 整体改进建议列表"
}}

**待分析的演示文稿信息:**
* **主题**: {title}
* **幻灯片总数**: {count}

**幻灯片列表概览:**
---
{slides}
---
"""


class ConsistencyChecker:
    """结合 LLM 与启发式的跨页一致性检查。"""

    def __init__(self, client: AIModelClient) -> None:
        self.client = client

    def check(self, state: OverallState) -> ConsistencyReport:
        prompt = _CONSISTENCY_PROMPT_TEMPLATE.format(
            title=state.outline.title if state.outline else "",
            count=len(state.slides),
            slides=self._format_slides(state.slides, state),
        )
        snapshot_manager.write_text(state.run_id, "04_consistency/prompt", prompt)
        context = {"run_id": state.run_id, "stage": "04_consistency", "name": "consistency"}
        response = self.client.structured_completion(prompt, ConsistencyAnalysisResponse, system=_CONSISTENCY_SYSTEM, context=context)
        snapshot_manager.write_json(state.run_id, "04_consistency/response", response.model_dump())
        report = ConsistencyReport(
            overall_score=response.overall_score,
            issues=[self._convert_issue(item) for item in response.issues],
            strengths=response.strengths,
            recommendations=response.recommendations,
        )
        self._augment_with_heuristics(state.slides, report)
        # 阶段 3.3：启发式证据冲突检测
        self._augment_with_evidence_conflicts(state, report)
        logger.info("一致性得分 %.1f，问题数=%d（含证据引用=%d）",
                    report.overall_score,
                    len(report.issues),
                    sum(1 for issue in report.issues if issue.evidence_refs))
        return report

    @staticmethod
    def _format_slides(slides: Iterable[SlideContent], state: OverallState) -> str:
        lines: List[str] = []
        for slide in slides:
            title = slide.page_title or slide.key_point or slide.section_title or f"幻灯片 {slide.slide_id}"
            notes = slide.speaker_notes or ""
            if not notes:
                notes = ConsistencyChecker._strip_html(slide.slide_html)
            summary = text_tools.summarise_text(notes, 1) if notes else ""
            lines.append(f"- 第{slide.slide_id}页《{title}》: {summary}")
            evidence_items = state.slide_evidence.get(slide.slide_id, [])
            evidence_line = text_tools.format_evidence(evidence_items, bullet=False)
            query = state.evidence_queries.get(slide.slide_id, "")
            if evidence_line:
                suffix = f" | Query: {query}" if query else ""
                lines.append(f"  证据: {evidence_line}{suffix}")
        return "\n".join(lines)




    def _strip_html(html: str) -> str:
        clean = re.sub(r"<[^>]+>", " ", html)
        return " ".join(clean.split())[:160]

    @staticmethod
    def _convert_issue(raw: Dict) -> ConsistencyIssue:
        try:
            issue_type = ConsistencyIssueType(raw.get("type", "logical_break"))
        except ValueError:
            issue_type = ConsistencyIssueType.LOGICAL_BREAK

        # 提取证据引用
        evidence_refs = raw.get("evidence_refs", [])
        if not isinstance(evidence_refs, list):
            evidence_refs = []

        # 检测是否缺少证据引用（对于应该有证据的问题类型）
        description = raw.get("description", "")
        should_have_evidence = any(
            keyword in description
            for keyword in ["数据", "术语", "事实", "证据", "原文", "数值", "统计"]
        )
        if should_have_evidence and not evidence_refs:
            logger.warning("一致性问题缺少证据引用：%s", description[:50])

        return ConsistencyIssue(
            issue_type=issue_type,
            severity=raw.get("severity", "medium"),
            slide_ids=[int(s) for s in raw.get("slide_ids", []) if isinstance(s, (int, str))],
            description=description,
            suggestion=raw.get("suggestion", ""),
            evidence_refs=evidence_refs if evidence_refs else None,
        )

    def _augment_with_evidence_conflicts(self, state: OverallState, report: ConsistencyReport) -> None:
        """启发式证据冲突检测。

        检测跨页面证据块是否存在矛盾（例如：相同主题但数据不一致）。
        """
        from collections import defaultdict

        # 构建证据索引：evidence_id -> {slide_id, content, chunk_id}
        evidence_index: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for slide_id, evidence_items in state.slide_evidence.items():
            for item in evidence_items:
                eid = item.get("evidence_id", "")
                snippet = item.get("snippet", "")
                if eid and snippet:
                    evidence_index[eid].append({
                        "slide_id": slide_id,
                        "snippet": snippet,
                        "chunk_id": item.get("chunk_id", ""),
                    })

        # 检测同一证据在不同页面中的使用（可能的冲突来源）
        for eid, usages in evidence_index.items():
            if len(usages) > 1:
                # 简单启发式：如果同一证据在多页使用，检查是否有明显的数值差异
                # 这里仅作示例，实际应用中可以扩展更复杂的冲突检测逻辑
                slide_ids = [usage["slide_id"] for usage in usages]
                snippets = [usage["snippet"] for usage in usages]

                # 检测是否包含数值（简单正则检测）
                has_numbers = any(re.search(r'\d+', snippet) for snippet in snippets)

                if has_numbers and len(set(snippets)) > 1:
                    # 发现潜在冲突：同一证据 ID 但内容不同
                    report.issues.append(
                        ConsistencyIssue(
                            issue_type=ConsistencyIssueType.TERMINOLOGY,
                            severity="low",
                            slide_ids=slide_ids,
                            description=f"证据 {eid} 在多页中引用但内容存在差异，可能导致信息不一致",
                            suggestion="核对原始证据，确保引用内容的准确性和一致性",
                            evidence_refs=[eid],
                            conflicting_evidence_pairs=None,
                        )
                    )
                    logger.info("检测到潜在证据冲突：%s 在幻灯片 %s 中内容不同", eid, slide_ids)

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
