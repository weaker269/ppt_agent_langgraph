import json

from src.agent.ai_client import AIModelClient
from src.agent.models import SlideResponse

def build_sample_payload():
    return {
        "slide_html": "<div class=\"slide-content\"><p>测试</p></div>",
        "charts": [
            {"id": "chart-1", "option": {"title": {"text": "Demo"}}}
        ],
        "speaker_notes": "说明",
        "page_title": "标题",
        "layout_template": "standard_dual_column"
    }


def test_normalize_slide_payload_accepts_aliases():
    data = build_sample_payload()
    normalised = AIModelClient._normalize_slide_payload(dict(data))
    assert normalised["charts"], "应至少保留一个图表"
    chart = normalised["charts"][0]
    assert chart["elementId"] == "chart-1"
    assert chart["options"]["title"]["text"] == "Demo"


def test_strip_js_functions_removes_callbacks():
    text = '{"formatter": function (value) { return value; }, "label": 1}'
    cleaned = AIModelClient._strip_js_functions(text)
    assert '"formatter": null' in cleaned


def test_parse_json_handles_chart_aliases():
    payload = build_sample_payload()
    raw = json.dumps(payload, ensure_ascii=False)
    response = AIModelClient._parse_json(raw, SlideResponse)
    assert response.charts[0].element_id == "chart-1"
