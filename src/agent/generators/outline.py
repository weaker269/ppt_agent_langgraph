"""大纲生成器：结合 LLM 与启发式策略。"""

from __future__ import annotations

from typing import List

from ..ai_client import AIConfig, AIModelClient
from ..domain import OutlineSection, PresentationOutline
from ..models import OutlineResponse
from ..state import OverallState
from ..utils import logger, text_tools

_OUTLINE_SYSTEM_PROMPT = """
你是一名资深演示文稿策划专家，善于将原始文本拆解成逻辑清晰的大纲。
你的输出必须是结构化 JSON，包含章节标题、摘要、要点和预计幻灯片数量。
"""

_OUTLINE_USER_PROMPT_TEMPLATE = """
请根据以下输入文本生成演示文稿大纲：

---
{content}
---

输出要求：
1. 不超过 6 个章节，每章节给出摘要和 3-5 个要点。
2. 估算每章节的幻灯片数量 (1-6)。
3. 标题尽量简洁，突出核心行动或观点。
4. JSON 字段：title, subtitle, target_audience, estimated_duration, sections。
"""


class OutlineGenerator:
    """负责生成结构化演示大纲。"""

    def __init__(self, client: AIModelClient | None = None, use_stub: bool | None = None) -> None:
        if client:
            self.client = client
        else:
            self.client = AIModelClient(AIConfig(enable_stub=bool(use_stub)))

    def generate_outline(self, state: OverallState) -> OverallState:
        if not state.input_text.strip():
            state.record_error("缺少输入文本，无法生成大纲")
            return state

        prompt = _OUTLINE_USER_PROMPT_TEMPLATE.format(content=state.input_text.strip())

        try:
            response = self.client.structured_completion(prompt, OutlineResponse, system=_OUTLINE_SYSTEM_PROMPT)
            state.outline = self._convert_outline(response)
            logger.info("生成大纲成功：章节数 %s", len(state.outline.sections))
        except Exception as exc:  # pragma: no cover - 异常路径
            logger.error("生成大纲失败，回退到启发式: %s", exc)
            state.outline = self._heuristic_outline(state.input_text)
            state.record_warning("大纲生成使用了启发式回退，建议检查文本质量")

        return state

    # ------------------------------------------------------------------
    # 辅助逻辑
    # ------------------------------------------------------------------

    def _convert_outline(self, response: OutlineResponse) -> PresentationOutline:
        sections: List[OutlineSection] = []
        for raw in response.sections:
            sections.append(
                OutlineSection(
                    index=raw.section_id,
                    title=raw.title,
                    summary=raw.summary,
                    key_points=raw.key_points,
                    estimated_slides=raw.estimated_slides,
                )
            )
        return PresentationOutline(
            title=response.title,
            subtitle=response.subtitle,
            target_audience=response.target_audience,
            estimated_duration=response.estimated_duration,
            sections=sections,
        )

    def _heuristic_outline(self, text: str) -> PresentationOutline:
        paragraphs = text_tools.segment_paragraphs(text)
        sections: List[OutlineSection] = []
        for idx, para in enumerate(paragraphs[:5], 1):
            sections.append(
                OutlineSection(
                    index=idx,
                    title=text_tools.derive_section_title(para, f"章节 {idx}"),
                    summary=text_tools.summarise_text(para, 2),
                    key_points=text_tools.extract_key_points(para, 4),
                    estimated_slides=max(1, len(para) // 400 + 1),
                )
            )
        if not sections:
            sections.append(
                OutlineSection(
                    index=1,
                    title="核心内容",
                    summary="提供更多输入以生成细节",
                    key_points=["目标", "方案", "行动"],
                    estimated_slides=3,
                )
            )
        return PresentationOutline(title=text_tools.derive_title(text), sections=sections)


__all__ = ["OutlineGenerator"]
