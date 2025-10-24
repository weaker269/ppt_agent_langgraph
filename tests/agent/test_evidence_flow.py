import json
from pathlib import Path

import pytest

from src.agent.domain import PresentationOutline, SlideContent, SlideType
from src.agent.evaluators.quality import QualityEvaluator
from src.agent.generators.content import SlidingWindowContentGenerator
from src.agent.state import OverallState
from src.agent.utils import text_tools
from src.agent.validators.consistency import ConsistencyChecker
from src.agent.models import QualityAssessmentResponse, ConsistencyAnalysisResponse


class StubClient:
    def __init__(self, response):
        self.response = response
        self.last_prompt = None
        self.last_system = None
        self.last_context = None

    def structured_completion(self, prompt, response_model, system, context):
        self.last_prompt = prompt
        self.last_system = system
        self.last_context = context
        return self.response


@pytest.fixture
def sample_state():
    state = OverallState()
    state.outline = PresentationOutline(title="云网融合实践", subtitle="", target_audience="运营团队", estimated_duration=20, sections=[])
    return state


def test_format_evidence_block_generates_bullets():
    generator = SlidingWindowContentGenerator(client=None, quality_evaluator=None)
    evidence_items = [
        {
            "evidence_id": "E1",
            "snippet": "多云协同可以降低调度延迟",
            "source_path": "docs/input.md",
            "section_title": "优势概述",
            "score": 0.92,
            "dense_score": 0.81,
            "bm25_score": 7.3,
        },
        {
            "evidence_id": "E2",
            "snippet": "统一编排提升跨区域资源利用率",
            "source_path": "docs/input.md",
            "section_title": "应用场景",
        },
    ]
    block = generator._format_evidence_block(evidence_items)
    assert "[E1]" in block
    assert "优势概述" in block
    assert block.count("-") == 2


def test_quality_evaluator_prompt_contains_evidence(sample_state):
    response = QualityAssessmentResponse(
        overall_score=90,
        logic_score=88,
        relevance_score=89,
        language_score=90,
        layout_score=85,
        strengths=["结构清晰"],
        weaknesses=["数据支撑略少"],
        suggestions=["补充量化指标"],
        pass_threshold=True,
    )
    client = StubClient(response)
    evaluator = QualityEvaluator(client)

    slide = SlideContent(
        slide_id=1,
        section_title="云网融合价值",
        section_summary="",
        key_point="一体化调度",
        template_suggestion="standard_dual_column",
        slide_type=SlideType.CONTENT,
        layout_template="standard_single_column",
        page_title="云网协同价值",
        slide_html="<div class='slide-content'>示例</div>",
        charts=[],
        speaker_notes="强调资源协同带来的效率提升",
    )

    sample_state.slide_evidence[1] = [
        {
            "evidence_id": "E1",
            "snippet": "调度效率提升 30%",
            "source_path": "docs/input.md",
        }
    ]
    sample_state.evidence_queries[1] = "云网 调度 效率"

    score, feedback = evaluator.evaluate(sample_state, slide, context_slides=[])

    assert client.last_prompt is not None
    assert "[E1]" in client.last_prompt
    assert "证据检索 Query" in client.last_prompt
    assert isinstance(score.total_score, float)
    assert feedback


def test_consistency_checker_prompt_includes_evidence(sample_state):
    response = ConsistencyAnalysisResponse(
        overall_score=92,
        issues=[],
        strengths=["结构连贯"],
        recommendations=["保持术语一致"],
    )
    client = StubClient(response)
    checker = ConsistencyChecker(client)

    slide = SlideContent(
        slide_id=2,
        section_title="实施路线",
        section_summary="",
        key_point="三阶段演进",
        template_suggestion="text_only",
        slide_type=SlideType.CONTENT,
        layout_template="standard_single_column",
        page_title="实施路线",
        slide_html="<div>实施路线</div>",
        speaker_notes="阶段1 注重基础设施；阶段2 开放生态",
    )
    sample_state.slides = [slide]
    sample_state.slide_evidence[2] = [
        {
            "evidence_id": "E1",
            "snippet": "阶段化推进可以降低迁移风险",
            "source_path": "docs/routes.md",
            "section_title": "实施建议",
        }
    ]
    sample_state.evidence_queries[2] = "实施路线 阶段 风险"

    checker.check(sample_state)

    assert "证据:" in client.last_prompt
    assert "Query" in client.last_prompt
