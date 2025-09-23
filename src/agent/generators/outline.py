"""
大纲生成器模块

负责分析输入文本，生成结构化的PPT演示大纲。
使用AI模型进行智能分析和内容规划。
"""

import json
import re
from typing import Dict, Any, Optional, List
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage, SystemMessage

from ..state import OverallState, PresentationOutline, OutlineSection
from ..prompts import PromptBuilder, SYSTEM_MESSAGES
from ..utils import logger, performance_monitor, text_processor


class OutlineGenerator:
    """大纲生成器类"""

    def __init__(self, model_provider: str = "openai", model_name: str = "gpt-3.5-turbo"):
        """
        初始化大纲生成器

        Args:
            model_provider: 模型提供商 ("openai" 或 "google")
            model_name: 模型名称
        """
        self.model_provider = model_provider
        self.model_name = model_name
        self.llm = self._initialize_model()

    def _initialize_model(self):
        """初始化AI模型"""
        try:
            if self.model_provider.lower() == "openai":
                return ChatOpenAI(
                    model=self.model_name,
                    temperature=0.7,
                    max_tokens=2000
                )
            elif self.model_provider.lower() == "google":
                return ChatGoogleGenerativeAI(
                    model=self.model_name,
                    temperature=0.7,
                    max_output_tokens=2000
                )
            else:
                raise ValueError(f"不支持的模型提供商: {self.model_provider}")

        except Exception as e:
            logger.error(f"模型初始化失败: {e}")
            raise

    def generate_outline(self, state: OverallState) -> OverallState:
        """
        生成演示大纲

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        logger.info("开始生成演示大纲")
        performance_monitor.start_timer("outline_generation")

        try:
            # 预处理输入文本
            processed_text = self._preprocess_text(state.input_text)

            # 构建提示词
            prompt = PromptBuilder.build_outline_prompt(processed_text)

            # 调用AI模型生成大纲
            outline_response = self._call_model(prompt)

            # 解析并验证大纲
            outline_data = self._parse_outline_response(outline_response)

            # 创建大纲对象
            outline = self._create_outline_object(outline_data)

            # 更新状态
            state.outline = outline
            state.outline_generated = True

            duration = performance_monitor.end_timer("outline_generation")
            logger.info(f"大纲生成完成，耗时: {duration:.2f}s")

            return state

        except Exception as e:
            logger.error(f"大纲生成失败: {e}")
            state.errors.append(f"大纲生成失败: {str(e)}")
            performance_monitor.end_timer("outline_generation")
            return state

    def _preprocess_text(self, text: str) -> str:
        """预处理输入文本"""
        logger.debug("预处理输入文本")

        # 清理文本
        cleaned_text = text_processor.clean_text(text)

        # 如果文本太长，进行摘要处理
        if len(cleaned_text) > 5000:
            # 分段处理
            paragraphs = text_processor.split_into_paragraphs(cleaned_text, max_length=500)
            # 保留前1000字符作为摘要（简化处理）
            cleaned_text = cleaned_text[:1000] + "...\n\n" + "\n".join(paragraphs[:3])
            logger.info(f"文本过长，已进行摘要处理")

        return cleaned_text

    def _call_model(self, prompt: str) -> str:
        """调用AI模型"""
        logger.debug("调用AI模型生成大纲")

        try:
            messages = [
                SystemMessage(content=SYSTEM_MESSAGES["content_analyst"]),
                HumanMessage(content=prompt)
            ]

            response = self.llm.invoke(messages)
            return response.content

        except Exception as e:
            logger.error(f"AI模型调用失败: {e}")
            raise

    def _parse_outline_response(self, response: str) -> Dict[str, Any]:
        """解析AI模型响应"""
        logger.debug("解析大纲响应")

        try:
            # 尝试提取JSON部分
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 如果没有代码块，尝试找到JSON对象
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    raise ValueError("响应中未找到有效的JSON")

            # 解析JSON
            outline_data = json.loads(json_str)

            # 验证必要字段
            required_fields = ["title", "total_slides", "sections"]
            for field in required_fields:
                if field not in outline_data:
                    raise ValueError(f"大纲缺少必要字段: {field}")

            return outline_data

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}")
            # 尝试修复常见的JSON错误
            return self._attempt_json_repair(response)

        except Exception as e:
            logger.error(f"大纲解析失败: {e}")
            raise

    def _attempt_json_repair(self, response: str) -> Dict[str, Any]:
        """尝试修复JSON格式错误"""
        logger.warning("尝试修复JSON格式错误")

        # 简化的修复逻辑
        try:
            # 移除多余的逗号
            fixed_response = re.sub(r',\s*}', '}', response)
            fixed_response = re.sub(r',\s*]', ']', fixed_response)

            # 再次尝试解析
            json_match = re.search(r'\{.*\}', fixed_response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))

        except:
            pass

        # 如果修复失败，返回默认结构
        logger.warning("JSON修复失败，使用默认大纲结构")
        return self._create_default_outline()

    def _create_default_outline(self) -> Dict[str, Any]:
        """创建默认大纲结构"""
        return {
            "title": "演示文稿",
            "subtitle": "",
            "total_slides": 10,
            "estimated_duration": 15,
            "target_audience": "一般听众",
            "main_objectives": ["传达主要信息"],
            "sections": [
                {
                    "section_id": 1,
                    "title": "引言",
                    "subtitle": "",
                    "key_points": ["背景介绍", "目标说明"],
                    "estimated_slides": 2,
                    "content_summary": "介绍演示背景和目标"
                },
                {
                    "section_id": 2,
                    "title": "主要内容",
                    "subtitle": "",
                    "key_points": ["核心观点", "关键信息", "论证过程"],
                    "estimated_slides": 6,
                    "content_summary": "展示核心内容和论证"
                },
                {
                    "section_id": 3,
                    "title": "总结",
                    "subtitle": "",
                    "key_points": ["要点回顾", "结论陈述"],
                    "estimated_slides": 2,
                    "content_summary": "总结要点并得出结论"
                }
            ]
        }

    def _create_outline_object(self, outline_data: Dict[str, Any]) -> PresentationOutline:
        """创建大纲对象"""
        logger.debug("创建大纲对象")

        try:
            # 创建章节对象列表
            sections = []
            for section_data in outline_data.get("sections", []):
                section = OutlineSection(
                    section_id=section_data.get("section_id", 0),
                    title=section_data.get("title", ""),
                    subtitle=section_data.get("subtitle", ""),
                    key_points=section_data.get("key_points", []),
                    estimated_slides=section_data.get("estimated_slides", 1),
                    content_summary=section_data.get("content_summary", "")
                )
                sections.append(section)

            # 创建大纲对象
            outline = PresentationOutline(
                title=outline_data.get("title", "演示文稿"),
                subtitle=outline_data.get("subtitle", ""),
                total_slides=outline_data.get("total_slides", 10),
                estimated_duration=outline_data.get("estimated_duration", 15),
                sections=sections,
                target_audience=outline_data.get("target_audience", ""),
                main_objectives=outline_data.get("main_objectives", [])
            )

            logger.info(f"大纲创建成功: {outline.title}, 共{len(sections)}个章节")
            return outline

        except Exception as e:
            logger.error(f"大纲对象创建失败: {e}")
            raise

    def validate_outline(self, outline: PresentationOutline) -> List[str]:
        """验证大纲的有效性"""
        logger.debug("验证大纲有效性")

        issues = []

        # 检查基本信息
        if not outline.title.strip():
            issues.append("缺少演示标题")

        if outline.total_slides < 3:
            issues.append("幻灯片数量过少")

        if outline.total_slides > 50:
            issues.append("幻灯片数量过多，建议控制在50页以内")

        # 检查章节
        if not outline.sections:
            issues.append("缺少章节结构")

        total_estimated_slides = sum(section.estimated_slides for section in outline.sections)
        if abs(total_estimated_slides - outline.total_slides) > 3:
            issues.append(f"章节幻灯片数量总和({total_estimated_slides})与总数({outline.total_slides})不匹配")

        # 检查每个章节
        for i, section in enumerate(outline.sections):
            if not section.title.strip():
                issues.append(f"第{i+1}个章节缺少标题")

            if section.estimated_slides < 1:
                issues.append(f"章节'{section.title}'的幻灯片数量无效")

            if not section.key_points:
                issues.append(f"章节'{section.title}'缺少关键要点")

        if issues:
            logger.warning(f"大纲验证发现{len(issues)}个问题")
            for issue in issues:
                logger.warning(f"大纲问题: {issue}")

        return issues

    def optimize_outline(self, outline: PresentationOutline) -> PresentationOutline:
        """优化大纲结构"""
        logger.debug("优化大纲结构")

        # 调整幻灯片数量分配
        total_slides = outline.total_slides
        num_sections = len(outline.sections)

        if num_sections > 0:
            # 重新分配幻灯片数量
            base_slides_per_section = max(1, total_slides // num_sections)
            remaining_slides = total_slides - (base_slides_per_section * num_sections)

            for i, section in enumerate(outline.sections):
                section.estimated_slides = base_slides_per_section
                if i < remaining_slides:
                    section.estimated_slides += 1

        logger.info("大纲结构优化完成")
        return outline