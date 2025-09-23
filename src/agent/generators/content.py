"""
滑动窗口内容生成器模块

这是项目的核心创新模块，实现了滑动窗口策略的串行内容生成。
通过维护上下文摘要，确保PPT内容的逻辑连贯性，避免内容割裂问题。
"""

import json
import re
from typing import Dict, Any, Optional, List, Tuple
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage, SystemMessage

from ..state import (
    OverallState, SlideContent, SlidingSummary,
    SlideType, SlideLayout, QualityMetrics, GenerationMetadata
)
from ..prompts import PromptBuilder, SYSTEM_MESSAGES
from ..utils import logger, performance_monitor, hash_generator


class SlidingWindowContentGenerator:
    """滑动窗口内容生成器"""

    def __init__(self, model_provider: str = "openai", model_name: str = "gpt-3.5-turbo"):
        """
        初始化滑动窗口内容生成器

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
                    max_tokens=1500
                )
            elif self.model_provider.lower() == "google":
                return ChatGoogleGenerativeAI(
                    model=self.model_name,
                    temperature=0.7,
                    max_output_tokens=1500
                )
            else:
                raise ValueError(f"不支持的模型提供商: {self.model_provider}")

        except Exception as e:
            logger.error(f"内容生成模型初始化失败: {e}")
            raise

    def generate_all_slides(self, state: OverallState) -> OverallState:
        """
        生成所有幻灯片内容

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        if not state.outline:
            logger.error("无法生成内容：缺少演示大纲")
            state.errors.append("无法生成内容：缺少演示大纲")
            return state

        logger.info(f"开始生成演示内容，预计{state.outline.total_slides}页")
        performance_monitor.start_timer("all_slides_generation")

        try:
            slide_id = 1

            # 遍历每个章节
            for section in state.outline.sections:
                logger.info(f"开始生成章节: {section.title}")

                # 为每个章节生成幻灯片
                for section_slide_index in range(section.estimated_slides):
                    try:
                        # 生成单页内容
                        slide = self._generate_single_slide(
                            state, section, slide_id, section_slide_index
                        )

                        if slide:
                            # 添加到状态中
                            state.slides.append(slide)

                            # 创建并添加滑动窗口摘要
                            summary = self._create_sliding_summary(slide)
                            self._add_sliding_summary(state, summary)

                            logger.info(f"第{slide_id}页生成完成: {slide.title}")
                        else:
                            logger.warning(f"第{slide_id}页生成失败")

                        slide_id += 1

                        # 更新当前幻灯片索引
                        state.current_slide_index = slide_id - 1

                    except Exception as e:
                        logger.error(f"第{slide_id}页生成出现错误: {e}")
                        state.errors.append(f"第{slide_id}页生成失败: {str(e)}")
                        slide_id += 1

            duration = performance_monitor.end_timer("all_slides_generation")
            logger.info(f"所有幻灯片生成完成，共{len(state.slides)}页，耗时: {duration:.2f}s")

            return state

        except Exception as e:
            logger.error(f"幻灯片生成过程出现严重错误: {e}")
            state.errors.append(f"幻灯片生成失败: {str(e)}")
            performance_monitor.end_timer("all_slides_generation")
            return state

    def _generate_single_slide(
        self,
        state: OverallState,
        section,
        slide_id: int,
        section_slide_index: int
    ) -> Optional[SlideContent]:
        """
        生成单个幻灯片内容

        Args:
            state: 当前状态
            section: 当前章节
            slide_id: 幻灯片ID
            section_slide_index: 章节内幻灯片索引

        Returns:
            生成的幻灯片内容
        """
        logger.debug(f"生成第{slide_id}页内容")
        performance_monitor.start_timer(f"slide_{slide_id}_generation")

        try:
            # 获取滑动窗口上下文
            context_history = self._get_sliding_window_context(state)

            # 构建提示词
            prompt = PromptBuilder.build_slide_content_prompt(
                outline=state.outline.dict(),
                section_title=section.title,
                section_points=section.key_points,
                current_slide=slide_id,
                total_slides=state.outline.total_slides,
                context_history=context_history
            )

            # 调用AI模型
            response = self._call_model_for_content(prompt)

            # 解析响应
            slide_data = self._parse_slide_response(response, slide_id)

            # 创建幻灯片对象
            slide = self._create_slide_object(slide_data)

            # 记录生成元数据
            metadata = GenerationMetadata(
                model_used=f"{self.model_provider}:{self.model_name}",
                generation_time=performance_monitor.end_timer(f"slide_{slide_id}_generation"),
                retry_count=0
            )
            state.generation_metadata.append(metadata)

            return slide

        except Exception as e:
            logger.error(f"第{slide_id}页生成失败: {e}")
            performance_monitor.end_timer(f"slide_{slide_id}_generation")
            return None

    def _get_sliding_window_context(self, state: OverallState) -> str:
        """
        获取滑动窗口上下文

        这是滑动窗口策略的核心实现，通过维护最近几页的摘要，
        为当前页面生成提供上下文信息。

        Args:
            state: 当前状态

        Returns:
            上下文字符串
        """
        if not state.sliding_summaries:
            return "这是演示的第一页，请设计一个引人注目的开场。"

        # 获取最近的摘要（滑动窗口）
        window_size = min(state.sliding_window_size, len(state.sliding_summaries))
        recent_summaries = state.sliding_summaries[-window_size:]

        context_parts = ["前面幻灯片的内容摘要："]

        for summary in recent_summaries:
            context_parts.append(
                f"第{summary.slide_id}页: {summary.main_message}"
            )
            if summary.key_concepts:
                context_parts.append(f"  关键概念: {', '.join(summary.key_concepts)}")

        context_parts.append("\n请确保当前页面与前面内容保持逻辑连贯，避免重复，并自然承接。")

        return "\n".join(context_parts)

    def _call_model_for_content(self, prompt: str) -> str:
        """调用AI模型生成内容"""
        try:
            messages = [
                SystemMessage(content=SYSTEM_MESSAGES["ppt_expert"]),
                HumanMessage(content=prompt)
            ]

            response = self.llm.invoke(messages)
            return response.content

        except Exception as e:
            logger.error(f"内容生成AI调用失败: {e}")
            raise

    def _parse_slide_response(self, response: str, slide_id: int) -> Dict[str, Any]:
        """解析幻灯片响应"""
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
            slide_data = json.loads(json_str)

            # 确保必要字段存在
            slide_data.setdefault("slide_id", slide_id)
            slide_data.setdefault("slide_type", "content")
            slide_data.setdefault("layout", "title_content")
            slide_data.setdefault("title", f"幻灯片 {slide_id}")
            slide_data.setdefault("content", [])
            slide_data.setdefault("bullet_points", [])
            slide_data.setdefault("images", [])
            slide_data.setdefault("notes", "")
            slide_data.setdefault("keywords", [])
            slide_data.setdefault("estimated_duration", 60)

            return slide_data

        except json.JSONDecodeError as e:
            logger.error(f"幻灯片JSON解析错误: {e}")
            return self._create_fallback_slide_data(slide_id)

        except Exception as e:
            logger.error(f"幻灯片解析失败: {e}")
            return self._create_fallback_slide_data(slide_id)

    def _create_fallback_slide_data(self, slide_id: int) -> Dict[str, Any]:
        """创建备用幻灯片数据"""
        return {
            "slide_id": slide_id,
            "slide_type": "content",
            "layout": "title_content",
            "title": f"幻灯片 {slide_id}",
            "content": ["内容生成失败，请手动编辑"],
            "bullet_points": ["要点1", "要点2"],
            "images": [],
            "notes": "此页面内容生成失败，需要手动编辑",
            "keywords": ["关键词"],
            "estimated_duration": 60
        }

    def _create_slide_object(self, slide_data: Dict[str, Any]) -> SlideContent:
        """创建幻灯片对象"""
        try:
            # 验证和转换枚举类型
            slide_type = SlideType(slide_data.get("slide_type", "content"))
            layout = SlideLayout(slide_data.get("layout", "title_content"))

            slide = SlideContent(
                slide_id=slide_data["slide_id"],
                slide_type=slide_type,
                layout=layout,
                title=slide_data["title"],
                content=slide_data.get("content", []),
                bullet_points=slide_data.get("bullet_points", []),
                images=slide_data.get("images", []),
                notes=slide_data.get("notes", ""),
                keywords=slide_data.get("keywords", []),
                estimated_duration=slide_data.get("estimated_duration", 60)
            )

            return slide

        except Exception as e:
            logger.error(f"幻灯片对象创建失败: {e}")
            # 创建最小可用的幻灯片对象
            return SlideContent(
                slide_id=slide_data["slide_id"],
                slide_type=SlideType.CONTENT,
                layout=SlideLayout.TITLE_CONTENT,
                title=slide_data.get("title", f"幻灯片 {slide_data['slide_id']}"),
                content=["内容创建失败"],
                bullet_points=["要点1"],
                notes="此页面创建时出现错误"
            )

    def _create_sliding_summary(self, slide: SlideContent) -> SlidingSummary:
        """
        创建滑动窗口摘要

        这是滑动窗口策略的关键部分，为每页内容创建简洁的摘要，
        用于后续页面生成时的上下文参考。

        Args:
            slide: 幻灯片内容

        Returns:
            滑动窗口摘要
        """
        # 提取主要信息
        main_message = slide.title

        # 如果有内容，添加第一句作为主要信息
        if slide.content:
            first_content = slide.content[0][:50]  # 截取前50字符
            main_message += f": {first_content}"

        # 提取关键概念
        key_concepts = slide.keywords[:3]  # 最多3个关键概念

        # 如果没有关键词，从要点中提取
        if not key_concepts and slide.bullet_points:
            key_concepts = [point[:10] for point in slide.bullet_points[:3]]

        # 创建逻辑连接描述
        logical_connection = self._determine_logical_connection(slide)

        summary = SlidingSummary(
            slide_id=slide.slide_id,
            main_message=main_message,
            key_concepts=key_concepts,
            logical_connection=logical_connection
        )

        logger.debug(f"为第{slide.slide_id}页创建摘要: {main_message[:30]}...")
        return summary

    def _determine_logical_connection(self, slide: SlideContent) -> str:
        """确定逻辑连接类型"""
        # 根据幻灯片类型和内容推断逻辑连接
        if slide.slide_type == SlideType.TITLE:
            return "开场介绍"
        elif slide.slide_type == SlideType.SECTION:
            return "章节过渡"
        elif slide.slide_type == SlideType.SUMMARY:
            return "总结归纳"
        elif slide.slide_type == SlideType.COMPARISON:
            return "对比分析"
        elif slide.slide_type == SlideType.DATA:
            return "数据支撑"
        else:
            return "内容展开"

    def _add_sliding_summary(self, state: OverallState, summary: SlidingSummary):
        """
        添加滑动窗口摘要

        维护滑动窗口大小，确保不会无限增长

        Args:
            state: 当前状态
            summary: 新的摘要
        """
        state.sliding_summaries.append(summary)

        # 维护滑动窗口大小
        if len(state.sliding_summaries) > state.sliding_window_size:
            # 移除最旧的摘要
            removed_summary = state.sliding_summaries.pop(0)
            logger.debug(f"移除旧摘要: 第{removed_summary.slide_id}页")

        logger.debug(f"滑动窗口摘要数量: {len(state.sliding_summaries)}")

    def regenerate_slide_with_quality_feedback(
        self,
        state: OverallState,
        slide_id: int,
        quality_issues: List[str],
        max_retries: int = 2
    ) -> Optional[SlideContent]:
        """
        基于质量反馈重新生成幻灯片

        Args:
            state: 当前状态
            slide_id: 要重新生成的幻灯片ID
            quality_issues: 质量问题列表
            max_retries: 最大重试次数

        Returns:
            重新生成的幻灯片内容
        """
        logger.info(f"开始重新生成第{slide_id}页，质量问题: {len(quality_issues)}个")

        # 找到原始幻灯片
        original_slide = None
        for slide in state.slides:
            if slide.slide_id == slide_id:
                original_slide = slide
                break

        if not original_slide:
            logger.error(f"未找到第{slide_id}页的原始内容")
            return None

        # 构建改进要求
        improvement_requirements = [
            "提升内容质量和专业性",
            "确保逻辑清晰和连贯性",
            "优化信息密度和可读性"
        ]

        # 获取上下文信息
        context_info = self._get_sliding_window_context(state)

        try:
            # 构建重新生成提示词
            prompt = PromptBuilder.build_regeneration_prompt(
                original_content=original_slide.dict(),
                quality_issues=quality_issues,
                improvement_requirements=improvement_requirements,
                context_info=context_info
            )

            # 调用模型重新生成
            response = self._call_model_for_content(prompt)

            # 解析新内容
            slide_data = self._parse_slide_response(response, slide_id)

            # 创建新的幻灯片对象
            new_slide = self._create_slide_object(slide_data)

            logger.info(f"第{slide_id}页重新生成完成")
            return new_slide

        except Exception as e:
            logger.error(f"第{slide_id}页重新生成失败: {e}")
            return None