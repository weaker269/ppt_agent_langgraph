import pytest

from src.agent.domain import (
    ConsistencyIssue,
    ConsistencyIssueType,
    ConsistencyReport,
    PresentationOutline,
    SlideContent,
    SlideType,
)
from src.agent.models import ConsistencyAnalysisResponse
from src.agent.state import OverallState
from src.agent.utils import snapshot_manager
from src.agent.validators.consistency import ConsistencyChecker


class _StubConsistencyClient:
    """简化版一致性检查桩对象。"""

    def __init__(self, response: ConsistencyAnalysisResponse) -> None:
        self._response = response
        self.last_prompt = None

    def structured_completion(self, prompt, response_model, system, context):
        self.last_prompt = prompt
        assert response_model is ConsistencyAnalysisResponse
        return self._response


@pytest.fixture(autouse=True)
def _reset_snapshot_dir(tmp_path):
    original_base = snapshot_manager.base_dir
    original_enabled = snapshot_manager.enabled
    snapshot_manager.base_dir = tmp_path / "snapshots"
    snapshot_manager.enabled = True
    yield snapshot_manager.base_dir
    snapshot_manager.base_dir = original_base
    snapshot_manager.enabled = original_enabled


def _build_state() -> OverallState:
    state = OverallState()
    state.run_id = "test_consistency"
    state.outline = PresentationOutline(
        title="云网融合复盘",
        subtitle="",
        target_audience="项目团队",
        estimated_duration=30,
        sections=[],
    )
    slide = SlideContent(
        slide_id=1,
        section_title="亮点总结",
        section_summary="",
        key_point="强调跨域调度优势",
        template_suggestion="simple_content",
        slide_type=SlideType.CONTENT,
        layout_template="standard_single_column",
        page_title="亮点总结",
        slide_html="<div class='slide'>跨域调度延迟降低 30%，需与证据 E1 对齐。</div>",
        charts=[],
        speaker_notes="引用证据 E1 的数据说明延迟改善。",
    )
    state.slides = [slide]
    state.slide_evidence[1] = [
        {"evidence_id": "E1", "snippet": "延迟由 120ms 降至 84ms", "source_path": "docs/perf.md"},
    ]
    return state


def test_consistency_issue_has_evidence_refs():
    issue = ConsistencyIssue(
        issue_type=ConsistencyIssueType.LOGICAL_BREAK,
        severity="medium",
        slide_ids=[1, 2],
        description="跨页逻辑断裂，需要引用证据",
        suggestion="统一参考证据 E1",
        evidence_refs=["E1"],
    )
    assert issue.evidence_refs == ["E1"]


def test_convert_issue_extracts_evidence_refs():
    checker = ConsistencyChecker(_StubConsistencyClient(ConsistencyAnalysisResponse(
        overall_score=90.0,
        issues=[],
        strengths=[],
        recommendations=[],
    )))
    raw = {
        "type": "logical_break",
        "severity": "high",
        "slide_ids": [1, 2],
        "description": "术语使用不一致，请结合证据核对",
        "suggestion": "统一术语并引用证据",
        "evidence_refs": ["E2", "E3"],
    }

    issue = checker._convert_issue(raw)

    assert issue.evidence_refs == ["E2", "E3"]
    assert issue.issue_type == ConsistencyIssueType.LOGICAL_BREAK


def test_missing_evidence_refs_warning(caplog):
    checker = ConsistencyChecker(_StubConsistencyClient(ConsistencyAnalysisResponse(
        overall_score=88.0,
        issues=[],
        strengths=[],
        recommendations=[],
    )))
    raw = {
        "type": "terminology_mismatch",
        "severity": "medium",
        "slide_ids": [1],
        "description": "数据引用不完整，需标注原始证据",
        "suggestion": "补充数据来源说明",
        "evidence_refs": [],
    }

    with caplog.at_level("WARNING"):
        issue = checker._convert_issue(raw)

    assert issue.evidence_refs is None
    warning_messages = [record.message for record in caplog.records if "缺少证据引用" in record.message]
    assert warning_messages, "缺少证据引用时应产生 warning"


def test_augment_with_evidence_conflicts():
    checker = ConsistencyChecker(_StubConsistencyClient(ConsistencyAnalysisResponse(
        overall_score=85.0,
        issues=[],
        strengths=[],
        recommendations=[],
    )))
    state = _build_state()
    state.slide_evidence[2] = [
        {"evidence_id": "E1", "snippet": "延迟由 120ms 降至 90ms", "source_path": "docs/perf.md"},
    ]
    report = ConsistencyReport(overall_score=90.0, issues=[])

    checker._augment_with_evidence_conflicts(state, report)

    assert report.issues, "应识别出证据冲突问题"
    assert report.issues[-1].evidence_refs == ["E1"]


def test_evidence_conflict_detection_same_id_different_content():
    checker = ConsistencyChecker(_StubConsistencyClient(ConsistencyAnalysisResponse(
        overall_score=90.0,
        issues=[],
        strengths=[],
        recommendations=[],
    )))
    state = _build_state()
    state.slide_evidence[2] = [
        {"evidence_id": "E1", "snippet": "延迟由 140ms 降至 100ms", "source_path": "docs/perf.md"},
    ]
    report = ConsistencyReport(overall_score=90.0, issues=[])

    checker._augment_with_evidence_conflicts(state, report)

    descriptions = [issue.description for issue in report.issues]
    assert any("证据 E1" in desc for desc in descriptions)


def test_consistency_check_logs_evidence_stats(caplog):
    response = ConsistencyAnalysisResponse(
        overall_score=87.0,
        issues=[
            {
                "type": "terminology_mismatch",
                "severity": "low",
                "slide_ids": [1],
                "description": "术语“响应时延”与证据 E1 不一致",
                "suggestion": "将术语统一为“调度延迟”",
                "evidence_refs": ["E1"],
            }
        ],
        strengths=["整体结构稳定"],
        recommendations=["继续对齐术语库"],
    )
    checker = ConsistencyChecker(_StubConsistencyClient(response))
    state = _build_state()

    with caplog.at_level("INFO"):
        report = checker.check(state)

    assert report.issues[0].evidence_refs == ["E1"]
    info_messages = [record.message for record in caplog.records if "问题数" in record.message]
    assert info_messages, "应记录包含证据统计的信息日志"
