from src.agent.ai_client import AIModelClient
from src.agent.domain import StyleProfile, StyleTheme
from src.agent.generators.style import StyleSelector
from src.agent.models import ColorSwatch, FontPairing, StyleAnalysisResponse


def test_style_payload_normalization_supports_structured_items():
    raw = {
        "recommended_theme": "creative",
        "color_palette": [
            {"name": "Primary Background", "hex": "#0D1B2A"},
            {"name": "Primary Text", "hex": "#F8F9FA"},
            {"name": "Primary Accent", "hex": "#43DDE6"},
            {"name": "Secondary Accent", "hex": "#A958A5"},
            {"name": "Neutral/Subtle Text", "hex": "#E0E1DD"},
        ],
        "font_pairing": [
            {"role": "Headings", "font_name": "Montserrat"},
            {"role": "Body Text", "font_name": "Lato"},
        ],
        "layout_preference": "dynamic",
        "reasoning": "说明" * 40,
    }
    normalized = AIModelClient._normalize_style_payload(raw)
    response = StyleAnalysisResponse(**normalized)
    assert len(response.color_palette) == 5
    assert response.color_palette[0].hex == "#0D1B2A"
    assert response.font_pairing[0].font_name == "Montserrat"
    assert response.reasoning.endswith("说明")


def test_style_selector_build_profile_maps_semantic_keys():
    response = StyleAnalysisResponse(
        recommended_theme=StyleTheme.CREATIVE,
        color_palette=[
            ColorSwatch(name="Primary Background", hex="#0D1B2A"),
            ColorSwatch(name="Primary Text", hex="#F8F9FA"),
            ColorSwatch(name="Primary Accent", hex="#43DDE6", usage="accent"),
            ColorSwatch(name="Secondary Accent", hex="#A958A5", usage="accent_secondary"),
            ColorSwatch(name="Neutral/Subtle Text", hex="#E0E1DD"),
        ],
        font_pairing=[
            FontPairing(role="Headings", font_name="Montserrat"),
            FontPairing(role="Body Text", font_name="Lato"),
        ],
        layout_preference="dynamic",
        reasoning="说明" * 40,
    )
    selector = StyleSelector()
    profile = selector._build_profile(response)

    assert isinstance(profile, StyleProfile)
    assert profile.theme == StyleTheme.CREATIVE
    assert profile.color_palette["background"] == "#0D1B2A"
    assert profile.color_palette["text"] == "#F8F9FA"
    assert profile.color_palette["accent"] == "#43DDE6"
    assert profile.color_palette["secondary"] == "#A958A5"
    assert profile.color_palette["text_muted"] == "#E0E1DD"
    assert profile.font_pairing["title"] == "Montserrat"
    assert profile.font_pairing["body"] == "Lato"
