"""
PPT智能体提示词定义模块

包含与AI模型交互的所有提示词模板，采用结构化的提示词设计，
确保生成高质量、连贯的PPT内容。
"""

from typing import List, Dict, Any
from string import Template


class PromptTemplates:
    """提示词模板类"""

    # 大纲生成提示词
    OUTLINE_GENERATION = """
你是一个专业的PPT制作专家。请根据以下文本内容，生成一个结构化的演示大纲。

**输入文本：**
{input_text}

**要求：**
1. 分析文本的核心主题和关键信息
2. 设计逻辑清晰的章节结构
3. 估算每个章节的幻灯片数量（建议每章节3-8页）
4. 总幻灯片数控制在15-30页之间
5. 为每个章节提供简洁的内容摘要

**输出格式（JSON）：**
```json
{
  "title": "演示标题",
  "subtitle": "演示副标题（可选）",
  "total_slides": 预计总幻灯片数,
  "estimated_duration": 预计演示时长(分钟),
  "target_audience": "目标受众",
  "main_objectives": ["主要目标1", "主要目标2"],
  "sections": [
    {
      "section_id": 1,
      "title": "章节标题",
      "subtitle": "章节副标题（可选）",
      "key_points": ["要点1", "要点2", "要点3"],
      "estimated_slides": 预计幻灯片数,
      "content_summary": "章节内容摘要"
    }
  ]
}
```

请确保大纲结构合理，逻辑清晰，适合演示呈现。
"""

    # 单页内容生成提示词
    SLIDE_CONTENT_GENERATION = """
你是一个专业的PPT内容制作专家。请根据以下信息，生成单页幻灯片的详细内容。

**演示大纲：**
{outline}

**当前章节信息：**
- 章节标题：{section_title}
- 章节要点：{section_points}
- 当前页码：{current_slide}/{total_slides}

**上下文信息（前几页内容摘要）：**
{context_history}

**生成要求：**
1. 根据章节内容和当前页码，确定本页的具体主题
2. 选择合适的幻灯片类型和布局
3. 内容要与前面的页面保持逻辑连贯性
4. 避免与之前页面的重复
5. 信息密度适中，便于演示阅读
6. 包含2-5个关键要点
7. 提供简洁有力的标题

**可选幻灯片类型：**
- title: 标题页
- content: 内容页
- section: 章节分割页
- summary: 总结页
- comparison: 对比页
- data: 数据展示页

**可选布局类型：**
- single_column: 单列布局
- two_column: 双列布局
- title_content: 标题+内容
- list_layout: 列表布局
- image_text: 图文混排

**输出格式（JSON）：**
```json
{
  "slide_id": {current_slide},
  "slide_type": "选择的类型",
  "layout": "选择的布局",
  "title": "幻灯片标题",
  "content": ["内容段落1", "内容段落2"],
  "bullet_points": ["要点1", "要点2", "要点3"],
  "images": ["图片描述1", "图片描述2"],
  "notes": "演讲者备注",
  "keywords": ["关键词1", "关键词2"],
  "estimated_duration": 展示时长秒数
}
```

请确保内容专业、准确、有吸引力。
"""

    # 样式选择提示词
    STYLE_SELECTION = """
你是一个专业的视觉设计师。请根据PPT的内容主题和目标受众，选择最合适的视觉样式。

**演示信息：**
- 标题：{title}
- 目标受众：{target_audience}
- 主要目标：{main_objectives}

**当前幻灯片内容：**
{slide_content}

**可选主题风格：**
1. **professional**: 专业商务风格 - 适合商务汇报、企业演示
2. **modern**: 现代简约风格 - 适合科技产品、创新项目
3. **creative**: 创意设计风格 - 适合艺术设计、创意展示
4. **academic**: 学术研究风格 - 适合学术报告、研究成果
5. **minimal**: 极简主义风格 - 适合产品发布、理念传达

**输出格式（JSON）：**
```json
{
  "selected_theme": "选择的主题",
  "reasoning": "选择理由",
  "color_scheme": {
    "primary": "主色调",
    "secondary": "辅助色",
    "accent": "强调色",
    "background": "背景色",
    "text": "文字色"
  },
  "font_suggestions": {
    "heading": "标题字体建议",
    "body": "正文字体建议"
  },
  "layout_preferences": {
    "spacing": "间距偏好",
    "alignment": "对齐方式",
    "emphasis": "强调方式"
  }
}
```

请选择最适合的样式主题。
"""

    # 内容一致性检查提示词
    CONSISTENCY_CHECK = """
你是一个专业的内容质量分析师。请检查这组PPT内容的逻辑一致性和连贯性。

**演示大纲：**
{outline}

**已生成的幻灯片：**
{slides_content}

**检查要点：**
1. 逻辑结构是否清晰完整
2. 内容之间是否存在逻辑跳跃
3. 信息密度是否适中
4. 是否存在重复或冗余内容
5. 专业术语使用是否一致
6. 风格语调是否统一

**输出格式（JSON）：**
```json
{
  "overall_score": 0.0-1.0的评分,
  "content_relevance": 内容相关性评分,
  "logical_coherence": 逻辑连贯性评分,
  "information_density": 信息密度评分,
  "style_consistency": 风格一致性评分,
  "issues_found": [
    {
      "type": "问题类型",
      "description": "问题描述",
      "affected_slides": [受影响的幻灯片ID],
      "severity": "low/medium/high",
      "suggestion": "改进建议"
    }
  ],
  "improvement_suggestions": ["整体改进建议1", "建议2"],
  "strengths": ["优点1", "优点2"]
}
```

请提供客观、专业的分析。
"""

    # 内容重新生成提示词（用于质量不达标时）
    CONTENT_REGENERATION = """
你是一个专业的PPT优化专家。以下幻灯片的质量评估未达到标准，请进行重新生成。

**原始内容：**
{original_content}

**质量问题：**
{quality_issues}

**改进要求：**
{improvement_requirements}

**上下文信息：**
{context_info}

**重新生成要求：**
1. 解决所有标识的质量问题
2. 保持与上下文的逻辑连贯性
3. 提升内容的专业性和吸引力
4. 确保信息的准确性和完整性
5. 优化视觉呈现效果

**输出格式（JSON）：**
使用与原始生成相同的JSON格式，但内容需要显著改进。

请生成高质量的替代内容。
"""

    # 演示文稿最终润色提示词
    FINAL_POLISH = """
你是一个资深的演示文稿专家。请对整个PPT进行最终的润色和优化。

**完整PPT内容：**
{complete_presentation}

**润色重点：**
1. 整体逻辑流程的优化
2. 章节间过渡的自然性
3. 开头和结尾的完善
4. 关键信息的突出强调
5. 语言表达的精炼和专业性

**特别关注：**
- 确保每页都有明确的价值
- 消除冗余和重复内容
- 加强论点的支撑力度
- 提升整体的说服力

**输出格式（JSON）：**
```json
{
  "polished_slides": [润色后的完整幻灯片列表],
  "major_changes": ["主要修改1", "修改2"],
  "quality_improvements": ["质量提升点1", "提升点2"],
  "presentation_flow": "整体流程优化说明"
}
```

请提供专业的润色建议。
"""


class PromptBuilder:
    """提示词构建器 - 动态生成提示词"""

    @staticmethod
    def build_outline_prompt(input_text: str) -> str:
        """构建大纲生成提示词"""
        template = Template(PromptTemplates.OUTLINE_GENERATION)
        return template.substitute(input_text=input_text)

    @staticmethod
    def build_slide_content_prompt(
        outline: Dict[str, Any],
        section_title: str,
        section_points: List[str],
        current_slide: int,
        total_slides: int,
        context_history: str
    ) -> str:
        """构建单页内容生成提示词"""
        template = Template(PromptTemplates.SLIDE_CONTENT_GENERATION)
        return template.substitute(
            outline=str(outline),
            section_title=section_title,
            section_points=", ".join(section_points),
            current_slide=current_slide,
            total_slides=total_slides,
            context_history=context_history
        )

    @staticmethod
    def build_style_selection_prompt(
        title: str,
        target_audience: str,
        main_objectives: List[str],
        slide_content: Dict[str, Any]
    ) -> str:
        """构建样式选择提示词"""
        template = Template(PromptTemplates.STYLE_SELECTION)
        return template.substitute(
            title=title,
            target_audience=target_audience,
            main_objectives=", ".join(main_objectives),
            slide_content=str(slide_content)
        )

    @staticmethod
    def build_consistency_check_prompt(
        outline: Dict[str, Any],
        slides_content: List[Dict[str, Any]]
    ) -> str:
        """构建一致性检查提示词"""
        template = Template(PromptTemplates.CONSISTENCY_CHECK)
        return template.substitute(
            outline=str(outline),
            slides_content=str(slides_content)
        )

    @staticmethod
    def build_regeneration_prompt(
        original_content: Dict[str, Any],
        quality_issues: List[str],
        improvement_requirements: List[str],
        context_info: str
    ) -> str:
        """构建内容重新生成提示词"""
        template = Template(PromptTemplates.CONTENT_REGENERATION)
        return template.substitute(
            original_content=str(original_content),
            quality_issues=", ".join(quality_issues),
            improvement_requirements=", ".join(improvement_requirements),
            context_info=context_info
        )

    @staticmethod
    def build_final_polish_prompt(complete_presentation: List[Dict[str, Any]]) -> str:
        """构建最终润色提示词"""
        template = Template(PromptTemplates.FINAL_POLISH)
        return template.substitute(complete_presentation=str(complete_presentation))


# 常用的系统消息
SYSTEM_MESSAGES = {
    "ppt_expert": "你是一个专业的PPT制作专家，拥有丰富的演示文稿设计经验。你的任务是创建结构清晰、内容丰富、视觉吸引人的演示文稿。",
    "content_analyst": "你是一个专业的内容分析师，擅长提取文本要点、构建逻辑结构、确保信息的准确性和完整性。",
    "design_expert": "你是一个专业的视觉设计师，精通色彩搭配、版式设计、用户体验，能够为内容选择最适合的视觉呈现方式。",
    "quality_inspector": "你是一个严格的质量检查员，负责评估内容的质量、逻辑的一致性、信息的准确性，确保最终产品达到专业标准。"
}