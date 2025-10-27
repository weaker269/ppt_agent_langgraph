from pathlib import Path

import pytest

from src.agent.domain import (
    OutlineKeyPoint,
    PresentationOutline,
    SlideContent,
    SlideType,
)
from src.agent.evaluators.quality import QualityEvaluator
from src.agent.generators.content import SlidingWindowContentGenerator
from src.agent.models import ConsistencyAnalysisResponse, QualityAssessmentResponse, SlideResponse
from src.agent.state import OverallState
from src.agent.utils import snapshot_manager
from src.agent.validators.consistency import ConsistencyChecker


class _QualityStubClient:
    def __init__(self, response: QualityAssessmentResponse):
        self._response = response

    def structured_completion(self, prompt, response_model, system, context):
        assert response_model is QualityAssessmentResponse
        return self._response


class _ReflectionStubClient:
    def __init__(self, response: SlideResponse):
        self._response = response

    def structured_completion(self, prompt, response_model, system, context):
        assert response_model is SlideResponse
        return self._response


class _ConsistencyStubClient:
    def __init__(self, response: ConsistencyAnalysisResponse):
        self._response = response

    def structured_completion(self, prompt, response_model, system, context):
        assert response_model is ConsistencyAnalysisResponse
        return self._response


def _prepare_state(tmp_path: Path) -> OverallState:
    original_base = snapshot_manager.base_dir
    original_enabled = snapshot_manager.enabled
    snapshot_manager.base_dir = tmp_path / "snapshots"
    snapshot_manager.enabled = True

    state = OverallState()
    state.run_id = "integration"
    state.outline = PresentationOutline(
        title="季度经营复盘",
        subtitle="",
        target_audience="管理团队",
        estimated_duration=30,
        sections=[],
    )
    slide = SlideContent(
        slide_id=1,
        section_title="经营亮点",
        section_summary="",
        key_point="季度销售额同比提升 18%",
        template_suggestion="simple_content",
        slide_type=SlideType.CONTENT,
        layout_template="standard_single_column",
        page_title="季度亮点",
        slide_html="<div class='slide'>季度销售额同比提升 18%，重点强化华东市场。</div>",
        charts=[],
        speaker_notes="引用证据 E1 与 E2 说明增幅来源。",
        metadata={
            "evidence_refs": [
                {"evidence_id": "E1", "snippet": "Sales Q2 = 1.2B", "source_path": "docs/sales.md"},
                {"evidence_id": "E2", "snippet": "East region grow 28%", "source_path": "docs/region.md"},
            ],
            "evidence_ids": ["E1", "E2"],
        },
    )
    state.slides = [slide]
    state.slide_evidence[1] = slide.metadata["evidence_refs"]
    state.evidence_queries[1] = "季度 销售 增长"
    snapshot_manager.write_json(
        state.run_id,
        "03_content/slide_01_evidence",
        {"query": state.evidence_queries[1], "items": state.slide_evidence[1]},
    )

    def _cleanup():
        snapshot_manager.base_dir = original_base
        snapshot_manager.enabled = original_enabled

    return state, _cleanup


def test_evidence_flow_through_full_workflow(tmp_path):
    state, cleanup = _prepare_state(tmp_path)
    try:
        quality_response = QualityAssessmentResponse(
            overall_score=82.0,
            logic_score=80.0,
            relevance_score=78.0,
            language_score=85.0,
            layout_score=82.0,
            strengths=["结构紧凑"],
            weaknesses=["缺乏量化对比"],
            suggestions=["引用证据 E1 和 E2 的具体数值"],
            pass_threshold=False,
            issues=[
                {
                    "dimension": "logic",
                    "description": "需要强化数据链路说明",
                    "suggestion": "在结论段补充 E1 与 E2 的引用",
                    "evidence_refs": ["E1", "E2"],
                }
            ],
        )
        quality_evaluator = QualityEvaluator(_QualityStubClient(quality_response))
        score, feedback = quality_evaluator.evaluate(state, state.slides[0], context_slides=[])

        assert score.total_score == pytest.approx(82.0)
        assert feedback[0].evidence_refs == ["E1", "E2"]

        reflection_response = SlideResponse(
            slide_html="<div class='slide'>保留证据引用 [E1][E2]，并补充对比描述。</div>",
            charts=[],
            speaker_notes="说明证据 E1 与 E2 的差异化贡献。",
            page_title="季度亮点（优化）",
            layout_template="standard_single_column",
            template_suggestion="simple_content",
        )
        generator = SlidingWindowContentGenerator(client=_ReflectionStubClient(reflection_response))
        regenerated = generator._regenerate(
            state,
            state.slides[0],
            feedback,
            OutlineKeyPoint(point="季度销售亮点"),
            {"run_id": state.run_id, "stage": "03_content", "name": "slide_01"},
        )

        state.slides = [regenerated]

        consistency_response = ConsistencyAnalysisResponse(
            overall_score=90.0,
            issues=[
                {
                    "type": "terminology_mismatch",
                    "severity": "low",
                    "slide_ids": [1],
                    "description": "证据 E1 在复盘与讲解中术语不一致",
                    "suggestion": "统一使用“销售额”表述",
                    "evidence_refs": ["E1"],
                }
            ],
            strengths=["术语大体一致"],
            recommendations=["保持证据命名一致"],
        )
        checker = ConsistencyChecker(_ConsistencyStubClient(consistency_response))
        report = checker.check(state)

        assert report.issues[0].evidence_refs == ["E1"]

        snapshots_root = Path(snapshot_manager.base_dir) / state.run_id
        assert (snapshots_root / "03_content" / "slide_01_evidence.json").exists()
        assert (snapshots_root / "04_quality" / "slide_01_evidence_validation.json").exists()
        diff_files = list((snapshots_root / "03_content").glob("slide_01_reflection_evidence_diff_*.json"))
        assert diff_files, "应生成证据变更快照"
    finally:
        cleanup()
