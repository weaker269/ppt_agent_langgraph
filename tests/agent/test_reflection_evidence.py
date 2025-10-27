import json
from pathlib import Path

import pytest

from src.agent.domain import (
    OutlineKeyPoint,
    PresentationOutline,
    QualityDimension,
    QualityFeedback,
    SlideContent,
    SlideType,
    SlidingSummary,
)
from src.agent.generators.content import SlidingWindowContentGenerator
from src.agent.models import SlideResponse
from src.agent.state import OverallState
from src.agent.utils import snapshot_manager


class _StubReflectionClient:
    """用于捕获反思 Prompt 的简单双向桩对象。"""

    def __init__(self, response: SlideResponse) -> None:
        self._response = response
        self.last_prompt = None
        self.last_context = None

    def structured_completion(self, prompt, response_model, system, context):
        self.last_prompt = prompt
        self.last_context = context
        assert response_model is SlideResponse
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


@pytest.fixture
def base_state() -> OverallState:
    state = OverallState()
    state.run_id = "test_reflection"
    state.outline = PresentationOutline(
        title="销售运营复盘",
        subtitle="",
        target_audience="销售团队",
        estimated_duration=25,
        sections=[],
    )
    state.sliding_summaries = [
        SlidingSummary(
            slide_id=0,
            main_message="复盘导言",
            key_concepts=["背景", "范围"],
            logical_link="introduction",
            supporting_evidence_ids=[],
            transition_hint="引入核心指标",
        )
    ]
    return state


def _build_slide() -> SlideContent:
    return SlideContent(
        slide_id=1,
        section_title="核心指标表现",
        section_summary="",
        key_point="强调季度销售增长 18%",
        template_suggestion="simple_content",
        slide_type=SlideType.CONTENT,
        layout_template="standard_single_column",
        page_title="季度关键指标",
        slide_html="<div class='slide'>当前季度销售额同比增长 18%，重点覆盖华东区域。</div>",
        charts=[],
        speaker_notes="结合证据说明同比增长数据，并提示区域差异。",
        metadata={
            "evidence_refs": [
                {"evidence_id": "E1", "snippet": "Q2 销售额 1.2 亿元", "source_path": "docs/sales.md"},
                {"evidence_id": "E2", "snippet": "华东区域增幅 28%", "source_path": "docs/region.md"},
            ],
            "evidence_ids": ["E1", "E2"],
        },
    )


def _build_response(**overrides) -> SlideResponse:
    payload = dict(
        slide_html="<div class='slide'>优化后的幻灯片内容，保留关键结论与证据引用 [E1][E2]。</div>",
        charts=[],
        speaker_notes="强调证据 E1 与 E2 的支撑逻辑。",
        page_title="季度关键指标（优化版）",
        layout_template="standard_single_column",
        template_suggestion="simple_content",
    )
    payload.update(overrides)
    return SlideResponse(**payload)


def _build_feedback() -> list[QualityFeedback]:
    return [
        QualityFeedback(
            dimension=QualityDimension.LOGIC,
            issue_description="需要明确 E1 数据与结论的联系",
            suggestion="在结论段补充 E1 数据引用",
            priority="medium",
            evidence_refs=["E1"],
        )
    ]


def test_validate_evidence_consistency_no_change():
    original = _build_slide()
    regenerated = _build_slide()
    result = SlidingWindowContentGenerator._validate_evidence_consistency(original, regenerated)

    assert result["has_changes"] is False
    assert sorted(result["retained"]) == ["E1", "E2"]


def test_validate_evidence_consistency_with_added():
    original = _build_slide()
    regenerated = _build_slide()
    regenerated.metadata["evidence_ids"] = ["E1", "E2", "E3"]
    result = SlidingWindowContentGenerator._validate_evidence_consistency(original, regenerated)

    assert result["has_changes"] is True
    assert result["added"] == ["E3"]


def test_validate_evidence_consistency_with_removed():
    original = _build_slide()
    regenerated = _build_slide()
    regenerated.metadata["evidence_ids"] = ["E1"]
    result = SlidingWindowContentGenerator._validate_evidence_consistency(original, regenerated)

    assert result["has_changes"] is True
    assert result["removed"] == ["E2"]


def test_needs_new_evidence_detection():
    original = _build_slide()
    regenerated = _build_slide()
    regenerated.metadata["evidence_ids"] = ["E1", "E2", "E3"]
    regenerated.speaker_notes = "需要新增图表支撑 [需补充证据]"
    result = SlidingWindowContentGenerator._validate_evidence_consistency(original, regenerated)

    assert result["needs_new_evidence"] is True


def test_reflection_prompt_includes_evidence_requirement(base_state):
    client = _StubReflectionClient(_build_response())
    generator = SlidingWindowContentGenerator(client=client)
    original = _build_slide()
    key_point = OutlineKeyPoint(point="季度销售亮点")

    generator._regenerate(
        base_state,
        original,
        _build_feedback(),
        key_point,
        {"run_id": base_state.run_id, "stage": "03_content", "name": "slide_01"},
    )

    assert client.last_prompt is not None
    assert "必须基于原始证据" in client.last_prompt
    assert "保留证据引用" in client.last_prompt


def test_evidence_diff_snapshot_generated(base_state):
    response = _build_response()
    client = _StubReflectionClient(response)
    generator = SlidingWindowContentGenerator(client=client)
    original = _build_slide()
    key_point = OutlineKeyPoint(point="季度销售亮点")

    regenerated = generator._regenerate(
        base_state,
        original,
        _build_feedback(),
        key_point,
        {"run_id": base_state.run_id, "stage": "03_content", "name": "slide_01"},
    )

    diff_path = Path(snapshot_manager.base_dir) / base_state.run_id / "03_content" / "slide_01_reflection_evidence_diff_1.json"
    assert diff_path.exists()
    diff_data = json.loads(diff_path.read_text(encoding="utf-8"))
    assert diff_data["has_changes"] is False
    assert diff_data["regenerated_count"] == 2
    assert regenerated.metadata.get("evidence_ids") == ["E1", "E2"]


def test_reflection_preserves_evidence_metadata(base_state):
    response = _build_response()
    client = _StubReflectionClient(response)
    generator = SlidingWindowContentGenerator(client=client)
    original = _build_slide()
    key_point = OutlineKeyPoint(point="季度销售亮点")

    regenerated = generator._regenerate(
        base_state,
        original,
        _build_feedback(),
        key_point,
        {"run_id": base_state.run_id, "stage": "03_content", "name": "slide_01"},
    )

    assert regenerated.metadata["evidence_refs"] == original.metadata["evidence_refs"]
    assert regenerated.metadata["evidence_ids"] == ["E1", "E2"]
