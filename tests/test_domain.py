from src.agent.domain import OutlineSection, PresentationOutline, SlideContent, SlideLayout, SlideType


def test_outline_total_slides_estimation():
    sections = [
        OutlineSection(index=1, title="背景", summary="A", key_points=["a", "b"], estimated_slides=2),
        OutlineSection(index=2, title="方案", summary="B", key_points=["c"], estimated_slides=1),
    ]
    outline = PresentationOutline(title="测试演示", sections=sections)
    assert outline.total_slides == 2 + 1 + 2


def test_slide_content_defaults():
    slide = SlideContent(slide_id=1, title="示例")
    assert slide.slide_type == SlideType.CONTENT
    assert slide.layout == SlideLayout.STANDARD
    assert slide.bullet_points == []
