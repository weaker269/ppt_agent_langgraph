from src.agent.domain import SlideContent, SlideType, StyleProfile, StyleTheme
from src.agent.renderers import HTMLRenderer
from src.agent.state import OverallState


def test_renderer_outputs_slide_html_snippet():
    state = OverallState()
    state.slides.append(
        SlideContent(
            slide_id=1,
            slide_type=SlideType.CONTENT,
            page_title="Test Page",
            slide_html='<div class="slide-content"><p>Demo body</p></div>',
            speaker_notes="Keep it concise",
        )
    )

    renderer = HTMLRenderer()
    updated_state = renderer.render_presentation(state)

    assert updated_state.html_output, "渲染后应生成 HTML 内容"
    assert '<div class="slide-content">' in updated_state.html_output, "应包含幻灯片 HTML 片段"
    assert 'Demo body' in updated_state.html_output, "应展示幻灯片正文"
    assert 'const slidesData =' in updated_state.html_output, "应包含幻灯片数据脚本"
    assert 'font-family: "Source Han Sans SC"' in updated_state.html_output, "应自动带上中文兜底字体"


def test_renderer_quotes_custom_font_stack():
    state = OverallState()
    state.selected_style = StyleProfile(
        theme=StyleTheme.PROFESSIONAL,
        font_pairing={"title": "Alibaba PuHuiTi 2.0", "body": "PingFang SC"},
    )
    state.slides.append(
        SlideContent(
            slide_id=2,
            slide_type=SlideType.CONTENT,
            page_title="Font Demo",
            slide_html='<div class="slide-content"><h2>Font Demo</h2></div>',
        )
    )

    renderer = HTMLRenderer()
    html_output = renderer.render_presentation(state).html_output

    assert 'font-family: "Alibaba PuHuiTi 2.0"' in html_output, "应为含空格的字体名加引号"
    assert 'font-family: "PingFang SC", "Source Han Sans SC"' in html_output, "应保留中文兜底字体"
