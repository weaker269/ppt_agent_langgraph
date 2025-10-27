import json
from pathlib import Path

import pytest

from src.agent.domain import PresentationOutline, QualityDimension, SlideContent, SlideType
from src.agent.evaluators.quality import QualityEvaluator
from src.agent.models import QualityAssessmentResponse
from src.agent.state import OverallState
from src.agent.utils import snapshot_manager


class _StubQualityClient:
    """模拟质量评估客户端，返回预设响应。"""

    def __init__(self, response: QualityAssessmentResponse) -> None:
        self._response = response
        self.last_prompt = None
        self.last_context = None

    def structured_completion(self, prompt, response_model, system, context):
        self.last_prompt = prompt
        self.last_context = context
        assert response_model is QualityAssessmentResponse  # 保证调用模型正确
        return self._response


@pytest.fixture(autouse=True)
def _reset_snapshot_dir(tmp_path):
    """将快照目录重定向到临时路径，避免污染真实数据。"""
    original_base = snapshot_manager.base_dir
    original_enabled = snapshot_manager.enabled
    snapshot_manager.base_dir = tmp_path / "snapshots"
    snapshot_manager.enabled = True
    yield snapshot_manager.base_dir
    snapshot_manager.base_dir = original_base
    snapshot_manager.enabled = original_enabled


@pytest.fixture
def base_state() -> OverallState:
    state = OverallState()
    state.run_id = "test_quality"
    state.outline = PresentationOutline(
        title="云网融合实践",
        subtitle="",
        target_audience="运维团队",
        estimated_duration=30,
        sections=[],
    )
    return state


def _build_slide(slide_id: int = 1) -> SlideContent:
    return SlideContent(
        slide_id=slide_id,
        section_title="价值概述",
        section_summary="",
        key_point="一体化调度优势",
        template_suggestion="simple_content",
        slide_type=SlideType.CONTENT,
        layout_template="standard_single_column",
        page_title="价值概述",
        slide_html="<div class='slide'>一体化调度优势说明，涵盖数据支撑与案例。</div>",
        charts=[],
        speaker_notes="聚焦真实案例，量化效率提升。",
    )


def _build_response(**overrides) -> QualityAssessmentResponse:
    payload = dict(
        overall_score=88.0,
        logic_score=86.0,
        relevance_score=87.0,
        language_score=90.0,
        layout_score=89.0,
        strengths=["结构完整", "论据清晰"],
        weaknesses=["需要补充数据"],
        suggestions=["补充量化指标"],
        pass_threshold=False,
        issues=[
            {
                "dimension": "logic",
                "description": "论证缺少关键数据支撑",
                "suggestion": "引用证据 E1 与 E2 的数据说明逻辑链路",
                "evidence_refs": ["E1", "E2"],
            }
        ],
    )
    payload.update(overrides)
    return QualityAssessmentResponse(**payload)


def test_quality_feedback_has_evidence_refs(base_state):
    slide = _build_slide()
    base_state.slide_evidence[slide.slide_id] = [
        {"evidence_id": "E1", "snippet": "系统上线后三个月效率提升 32%", "source_path": "docs/case.md"},
        {"evidence_id": "E2", "snippet": "跨域调度时延降低 18%", "source_path": "docs/case.md"},
    ]
    evaluator = QualityEvaluator(_StubQualityClient(_build_response()))

    score, feedback = evaluator.evaluate(base_state, slide, context_slides=[])

    assert score.total_score == pytest.approx(88.0)
    assert feedback and feedback[0].evidence_refs == ["E1", "E2"]


def test_evidence_validation_with_valid_ids(tmp_path, base_state):
    slide = _build_slide()
    base_state.run_id = "run_valid"
    base_state.slide_evidence[slide.slide_id] = [
        {"evidence_id": "E1", "snippet": "上线后月活提升 20%", "source_path": "docs/report.md"}
    ]
    evaluator = QualityEvaluator(_StubQualityClient(_build_response(issues=[
        {
            "dimension": "relevance",
            "description": "需要补充实际成效",
            "suggestion": "在结论段引用 E1 数据",
            "evidence_refs": ["E1"],
        }
    ])))

    evaluator.evaluate(base_state, slide, context_slides=[])

    validation_path = Path(snapshot_manager.base_dir) / base_state.run_id / "04_quality" / "slide_01_evidence_validation.json"
    data = json.loads(validation_path.read_text(encoding="utf-8"))
    assert data["total_refs"] == 1
    assert data["valid_refs"] == 1
    assert data["invalid_refs"] == []


def test_evidence_validation_with_invalid_ids(caplog, base_state):
    slide = _build_slide()
    base_state.run_id = "run_invalid"
    base_state.slide_evidence[slide.slide_id] = [
        {"evidence_id": "E1", "snippet": "成本投入缩减 15%", "source_path": "docs/cost.md"}
    ]
    response = _build_response(issues=[
        {
            "dimension": "logic",
            "description": "论证需要新增事实对比",
            "suggestion": "引用原始报告中的数值对比",
            "evidence_refs": ["E9"],
        }
    ])
    evaluator = QualityEvaluator(_StubQualityClient(response))

    with caplog.at_level("WARNING"):
        evaluator.evaluate(base_state, slide, context_slides=[])

    validation_path = Path(snapshot_manager.base_dir) / base_state.run_id / "04_quality" / "slide_01_evidence_validation.json"
    data = json.loads(validation_path.read_text(encoding="utf-8"))
    assert data["invalid_refs"] == ["E9"]
    warning_messages = [record.message for record in caplog.records if "无效证据 ID" in record.message]
    assert warning_messages, "应记录无效证据 ID 的 warning"


def test_evidence_validation_snapshot_generated(base_state):
    slide = _build_slide()
    base_state.run_id = "run_snapshot"
    base_state.slide_evidence[slide.slide_id] = [
        {"evidence_id": "E1", "snippet": "项目投资回收期缩短到 6 个月", "source_path": "docs/finance.md"}
    ]
    evaluator = QualityEvaluator(_StubQualityClient(_build_response()))

    evaluator.evaluate(base_state, slide, context_slides=[])

    snapshot_dir = Path(snapshot_manager.base_dir) / base_state.run_id / "04_quality"
    assert (snapshot_dir / "slide_01_evidence_validation.json").exists()
    assert (snapshot_dir / "slide_01_prompt.txt").exists()


def test_build_feedback_with_issues_format():
    response = _build_response()
    feedback = QualityEvaluator._build_feedback(response)

    assert len(feedback) == 1
    assert feedback[0].dimension == QualityDimension.LOGIC
    assert feedback[0].priority == "medium"
    assert feedback[0].evidence_refs == ["E1", "E2"]


def test_build_feedback_backward_compatibility(caplog):
    response = _build_response(
        issues=[],
        weaknesses=["需要补充图表"],
        suggestions=["新增对比图展示趋势"],
    )
    with caplog.at_level("WARNING"):
        feedback = QualityEvaluator._build_feedback(response)

    assert feedback[0].evidence_refs == []
    warning_messages = [record.message for record in caplog.records if "旧格式" in record.message]
    assert warning_messages, "向后兼容分支应提示缺少证据引用"


def test_missing_evidence_warning(caplog):
    response = _build_response(issues=[
        {
            "dimension": "logic",
            "description": "关键数据缺失，难以支撑论证",
            "suggestion": "引用前文证据以补全逻辑",
            "evidence_refs": [],
        }
    ])
    with caplog.at_level("WARNING"):
        feedback = QualityEvaluator._build_feedback(response)

    assert feedback[0].priority == "high"
    warning_messages = [record.message for record in caplog.records if "缺少证据引用" in record.message]
    assert warning_messages, "缺少证据引用时应记录 warning"
