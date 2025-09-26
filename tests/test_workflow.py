from src.agent import generate_ppt_from_text

SAMPLE_TEXT = """
人工智能平台发布计划

本次发布分为三个部分。首先回顾产品愿景与核心能力，其次拆解平台架构与关键模块，最后明确推广计划与里程碑。

愿景阶段将突出团队成果与客户反馈，强调平台在行业落地中的优势。架构阶段将细化数据处理、模型监控、权限治理三个方面的能力建设。推广阶段规划市场活动、合作伙伴招募以及客户成功支持。
""".strip()


def test_generate_ppt_from_text_creates_slides_with_stub():
    state = generate_ppt_from_text(SAMPLE_TEXT, model_provider="stub", use_stub=True)
    assert not state.errors
    assert state.outline is not None
    assert len(state.slides) >= 5
    assert state.html_output.startswith("<!DOCTYPE html>")
    assert state.slide_quality  # 至少有质量评估信息
    assert state.consistency_report is not None
