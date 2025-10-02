
"""大纲生成器：结合 LLM 与启发式策略。"""

from __future__ import annotations

from typing import List

from ..ai_client import AIConfig, AIModelClient
from ..domain import OutlineKeyPoint, OutlineSection, PresentationOutline
from ..models import OutlineResponse
from ..state import OverallState
from ..utils import logger, snapshot_manager, text_tools

_OUTLINE_SYSTEM_PROMPT = """
你是一名资深演示文稿策划专家，需要为后续的视觉设计与内容生成制定高质量的大纲。
请始终输出结构化 JSON，并为每个要点提供页面模板建议。允许的模板建议包括：
- simple_content
- text_with_chart
- text_with_table
- full_width_image
- standard_single_column
- standard_dual_column
- title_section
"""

_OUTLINE_USER_PROMPT_TEMPLATE = """
请根据以下输入文本为演示文稿生成一个结构化的大纲。

**输入文本:**
---
{content}
---

**指令:**
1. **分析文本与定位**：理解文本主题、目标受众和整体语气，为后续提供指导。
2. **生成顶层信息**：给出主标题（title）、副标题（subtitle）、目标受众（target_audience）以及预计演示时长（estimated_duration，单位分钟）。
3. **划分核心章节**：拆解为不超过 6 个章节，为每个章节提供概要 summary 和 3-5 个核心要点。
4. **页面模板建议**：针对每个要点评估其最适合的页面呈现方式，填入 `template_suggestion` 字段，取值见上方允许列表。
5. **估算页数**：估算每个章节需要的幻灯片数量（estimated_slides，1-6 之间）。
6. **严格输出**：必须严格按照下方 JSON 模板输出，不要添加额外文本。

**输出 JSON 格式:**
```json
{{
  "title": "string",
  "subtitle": "string",
  "target_audience": "string",
  "estimated_duration": 25,
  "sections": [
    {{
      "section_id": 1,
      "title": "string",
      "summary": "string",
      "key_points": [
        {{
          "point": "string",
          "template_suggestion": "text_with_chart"
        }}
      ],
      "estimated_slides": 3
    }}
  ]
}}
```
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
        snapshot_manager.write_text(state.run_id, "01_outline/prompt", prompt)

        try:
            response = self.client.structured_completion(prompt, OutlineResponse, system=_OUTLINE_SYSTEM_PROMPT)
            snapshot_manager.write_json(state.run_id, "01_outline/response", response.model_dump())
            state.outline = self._convert_outline(response)
            logger.info("生成大纲成功：章节数 %s", len(state.outline.sections))
        except Exception as exc:  # pragma: no cover - 异常路径
            logger.error("生成大纲失败，回退到启发式: %s", exc)
            state.outline = self._heuristic_outline(state.input_text)
            snapshot_manager.write_json(state.run_id, "01_outline/heuristic", state.outline.model_dump())
            state.record_warning("大纲生成使用了启发式回退，建议检查文本质量")

        return state

    # ------------------------------------------------------------------
    # 辅助逻辑
    # ------------------------------------------------------------------

    def _convert_outline(self, response: OutlineResponse) -> PresentationOutline:
        sections: List[OutlineSection] = []
        for raw in response.sections:
            points = [
                OutlineKeyPoint(point=kp.point, template_suggestion=kp.template_suggestion)
                for kp in raw.key_points
            ]
            sections.append(
                OutlineSection(
                    index=raw.section_id,
                    title=raw.title,
                    summary=raw.summary,
                    key_points=points,
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
            key_points = [
                OutlineKeyPoint(point=item, template_suggestion="simple_content")
                for item in text_tools.extract_key_points(para, 4)
            ]
            if not key_points:
                key_points.append(OutlineKeyPoint(point="补充更多细节", template_suggestion="simple_content"))
            sections.append(
                OutlineSection(
                    index=idx,
                    title=text_tools.derive_section_title(para, f"章节 {idx}"),
                    summary=text_tools.summarise_text(para, 2),
                    key_points=key_points,
                    estimated_slides=max(1, len(para) // 400 + 1),
                )
            )
        if not sections:
            sections.append(
                OutlineSection(
                    index=1,
                    title="核心内容",
                    summary="提供更多输入以生成细节",
                    key_points=[OutlineKeyPoint(point="目标", template_suggestion="simple_content")],
                    estimated_slides=3,
                )
            )
        return PresentationOutline(title=text_tools.derive_title(text), sections=sections)


__all__ = ["OutlineGenerator"]
