#!/usr/bin/env python3
"""
PPT Agent 提示词模板

提供系统中使用的各种提示词模板，支持结构化内容生成
"""

from typing import Dict, Any, List


class PromptTemplates:
    """提示词模板类"""

    @staticmethod
    def outline_analysis_prompt(content: str) -> str:
        """大纲分析提示词"""
        return f"""
请分析以下文本内容，生成结构化的PPT大纲。

原始内容：
{content}

要求：
1. 识别主标题和各级子标题
2. 分析内容层次结构
3. 估算每个部分需要的幻灯片数量
4. 保持逻辑清晰，层次分明

请以JSON格式返回分析结果，包含：
- main_title: 主标题
- sections: 各个章节信息
- estimated_total_slides: 预估总幻灯片数
"""

    @staticmethod
    def slide_generation_prompt(section_title: str, section_content: str, context: str) -> str:
        """幻灯片生成提示词"""
        return f"""
基于以下信息生成一页高质量的PPT幻灯片内容：

章节标题：{section_title}
章节内容：{section_content}
全文背景：{context}

要求：
1. 内容要点清晰，层次分明
2. 语言简洁专业，适合演示
3. 突出关键信息
4. 保持与全文主题的一致性

请生成：
- slide_title: 幻灯片标题
- slide_content: 幻灯片主要内容
- content_type: 内容类型(text/list/quote)
"""

    @staticmethod
    def quality_check_prompt(slide_content: str, context: str) -> str:
        """质量检查提示词"""
        return f"""
请评估以下PPT幻灯片的质量：

幻灯片内容：{slide_content}
上下文：{context}

评估维度：
1. 完整性(0-1)：内容是否完整表达了要点
2. 一致性(0-1)：是否与整体主题保持一致
3. 清晰度(0-1)：表达是否清晰易懂

请返回JSON格式的评分和改进建议：
{{
    "completeness_score": 0.8,
    "consistency_score": 0.9,
    "clarity_score": 0.85,
    "suggestions": ["改进建议1", "改进建议2"]
}}
"""

    @staticmethod
    def content_optimization_prompt(original_content: str, feedback: str) -> str:
        """内容优化提示词"""
        return f"""
基于反馈意见优化以下PPT内容：

原始内容：{original_content}
反馈意见：{feedback}

优化要求：
1. 根据反馈意见进行针对性改进
2. 保持原有信息的完整性
3. 提升表达的清晰度和吸引力
4. 确保逻辑结构合理

请返回优化后的内容。
"""


class ContentParser:
    """内容解析器"""

    @staticmethod
    def parse_markdown_structure(content: str) -> Dict[str, Any]:
        """解析Markdown结构"""
        lines = content.split('\n')
        structure = {
            'main_title': '',
            'sections': []
        }

        current_section = None
        section_content = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith('# '):
                # 主标题
                structure['main_title'] = line[2:].strip()

            elif line.startswith('## '):
                # 保存前一个章节
                if current_section:
                    current_section['content'] = '\n'.join(section_content)
                    structure['sections'].append(current_section)

                # 新章节
                current_section = {
                    'title': line[3:].strip(),
                    'content': '',
                    'subsections': []
                }
                section_content = []

            elif line.startswith('### '):
                # 子标题
                section_content.append(f"**{line[4:].strip()}**")

            elif line.startswith('- '):
                # 列表项
                section_content.append(f"• {line[2:].strip()}")

            else:
                # 普通文本
                if line:
                    section_content.append(line)

        # 添加最后一个章节
        if current_section:
            current_section['content'] = '\n'.join(section_content)
            structure['sections'].append(current_section)

        return structure

    @staticmethod
    def estimate_slides_count(sections: List[Dict[str, Any]]) -> int:
        """估算幻灯片数量"""
        total_slides = 1  # 标题页

        for section in sections:
            content = section.get('content', '')
            lines = len(content.split('\n'))

            # 基于内容长度估算
            if lines <= 3:
                slides = 1
            elif lines <= 8:
                slides = 2
            else:
                slides = max(2, min(4, lines // 4))

            total_slides += slides

        return total_slides


class StyleTemplates:
    """样式模板"""

    PROFESSIONAL_THEME = {
        'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'primary_color': '#667eea',
        'text_color': '#333',
        'title_size': '2.5em',
        'content_size': '1.1em'
    }

    SIMPLE_THEME = {
        'background': '#f8f9fa',
        'primary_color': '#007bff',
        'text_color': '#212529',
        'title_size': '2.2em',
        'content_size': '1.0em'
    }

    @staticmethod
    def get_theme(theme_name: str = "professional") -> Dict[str, str]:
        """获取主题样式"""
        themes = {
            'professional': StyleTemplates.PROFESSIONAL_THEME,
            'simple': StyleTemplates.SIMPLE_THEME
        }
        return themes.get(theme_name, StyleTemplates.PROFESSIONAL_THEME)