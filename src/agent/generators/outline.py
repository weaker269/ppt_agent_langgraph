
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
您是一位顶级的演示文稿（PPT）策划专家，任务是为后续的视觉设计与内容生成，制定一份高质量、结构化的大纲。

**指令:**
1.  **分析输入**: 请深入理解下方提供的“输入文本”，精准把握其主题、核心论点、目标受众和整体基调。
2.  **生成顶层信息**: 设计演示文稿的主标题、副标题，并明确目标受众和预计的演示时长。
3.  **构建核心章节**: 将内容拆解为逻辑清晰的章节（不超过 6 个）。为每个章节撰写标题 (title) 和简明扼要的摘要 (summary)。
4.  **提炼关键要点**: 在每个章节下，提炼 3-5 个核心要点 (key_points)，每个要点都应言之有物。
5.  **推荐页面模板**: 针对每一个“要点”，从下方允许的模板列表中选择最合适的 `template_suggestion`。
6.  **估算页面数量**: 估算每个章节大致需要的幻灯片页数。
7.  **严格格式化输出**: 您的输出必须是一个格式正确的、扁平化的 JSON 对象，绝对不能包含任何额外的解释性文本、注释或 markdown 标记。

**页面模板允许列表**:
- `simple_content`: 简单内容展示
- `text_with_chart`: 带图表的文本
- `text_with_table`: 带表格的文本
- `full_width_image`: 全宽图片
- `standard_single_column`: 标准单列布局
- `standard_dual_column`: 标准双列布局
- `title_section`: 章节标题页

**输出 JSON 格式定义**:
- **重要规则**: 如果 JSON 字符串的值中包含双引号（"），您必须使用反斜杠进行转义（\\"）。
```json
{{
  "title": "string // 演示文稿的主标题，长度 1-120 字符",
  "subtitle": "string // 副标题，可选，长度 0-160 字符",
  "target_audience": "string // 目标受众描述，长度 1-120 字符",
  "estimated_duration": "integer // 预计演示时长（分钟），5-180 之间",
  "sections": [
    {{
      "section_id": "integer // 章节序号，从 1 开始",
      "title": "string // 章节标题，长度 1-80 字符",
      "summary": "string // 章节摘要，长度 0-300 字符",
      "key_points": [
        {{
          "point": "string // 核心要点内容，长度 1-200 字符",
          "template_suggestion": "string // 从允许列表中选择的模板名称，必填"
        }}
      ],
      "estimated_slides": "integer // 估算章节页数，1-10 之间"
    }}
  ]
}}

**输入文本**:
{content}
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

        context = {"run_id": state.run_id, "stage": "01_outline", "name": "outline"}
        try:
            response = self.client.structured_completion(prompt, OutlineResponse, system=_OUTLINE_SYSTEM_PROMPT, context=context)
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
