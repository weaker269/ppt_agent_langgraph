"""
PPT Agent LangGraph 工作流定义

实现基于LangGraph的PPT生成工作流，包括：
- 全局内容分析
- 大纲生成
- 章节并发处理
- 质量检查和润色
"""

import json
import asyncio
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph import StateGraph, END
from langgraph.graph import Graph

from .state import (
    OverallState, SectionState, SectionInfo, SlideContent,
    ProcessStatus, GlobalContext, StateManager
)
from .prompts import PromptBuilder
from .util import (
    logger, semantic_layer, echarts_generator,
    quality_controller, config_manager
)


class LLMManager:
    """LLM管理器"""

    def __init__(self):
        self.openai_client = None
        self.google_client = None
        self._initialize_clients()

    def _initialize_clients(self):
        """初始化LLM客户端"""
        openai_key = config_manager.get("OPENAI_API_KEY")
        if openai_key:
            try:
                self.openai_client = ChatOpenAI(
                    api_key=openai_key,
                    model="gpt-4o-mini",
                    temperature=0.1
                )
                logger.info("OpenAI客户端初始化成功")
            except Exception as e:
                logger.error("OpenAI客户端初始化失败", error=e)

        google_key = config_manager.get("GOOGLE_API_KEY")
        if google_key:
            try:
                self.google_client = ChatGoogleGenerativeAI(
                    google_api_key=google_key,
                    model="gemini-pro",
                    temperature=0.1
                )
                logger.info("Google GenAI客户端初始化成功")
            except Exception as e:
                logger.error("Google GenAI客户端初始化失败", error=e)

    def get_available_client(self):
        """获取可用的LLM客户端"""
        if self.openai_client:
            return self.openai_client
        elif self.google_client:
            return self.google_client
        else:
            raise Exception("没有可用的LLM客户端，请检查API密钥配置")

    def invoke_with_retry(self, prompt: str, max_retries: int = 3) -> str:
        """带重试的LLM调用"""
        client = self.get_available_client()

        for attempt in range(max_retries):
            try:
                response = client.invoke([{"role": "user", "content": prompt}])
                return response.content.strip()
            except Exception as e:
                logger.error(f"LLM调用失败，尝试 {attempt + 1}/{max_retries}", error=e)
                if attempt == max_retries - 1:
                    raise e


class PPTGraphBuilder:
    """PPT生成图构建器"""

    def __init__(self):
        self.llm_manager = LLMManager()

    def create_graph(self) -> Graph:
        """创建PPT生成工作流图"""
        graph = StateGraph(OverallState)

        # 添加节点
        graph.add_node("global_analyzer", self.global_analysis_node)
        graph.add_node("outline_generator", self.outline_generation_node)
        graph.add_node("section_processor", self.section_processing_node)
        graph.add_node("quality_enhancer", self.quality_enhancement_node)

        # 添加边
        graph.add_edge("global_analyzer", "outline_generator")
        graph.add_edge("outline_generator", "section_processor")
        graph.add_edge("section_processor", "quality_enhancer")
        graph.add_edge("quality_enhancer", END)

        # 设置入口点
        graph.set_entry_point("global_analyzer")

        return graph.compile()

    def global_analysis_node(self, state: OverallState) -> OverallState:
        """全局内容分析节点"""
        logger.info("开始全局内容分析")

        try:
            # 构建分析提示词
            prompt = PromptBuilder.build_global_analysis_prompt(state.source_content)

            # 调用LLM进行分析
            response = self.llm_manager.invoke_with_retry(prompt)

            # 解析响应
            analysis_result = self._parse_json_response(response)

            # 更新全局上下文
            global_context = GlobalContext(
                term_dictionary=analysis_result.get("term_dictionary", {}),
                core_concepts=analysis_result.get("core_concepts", []),
                key_messages=analysis_result.get("key_messages", []),
                content_style=analysis_result.get("content_style", "professional"),
                target_audience=analysis_result.get("target_audience", "general"),
                presentation_tone=analysis_result.get("presentation_tone", "formal"),
                logical_structure=analysis_result.get("logical_structure", "sequential"),
                narrative_flow=analysis_result.get("narrative_flow", [])
            )

            state.global_context = global_context
            state.current_stage = "global_analysis_completed"

            # 记录处理日志
            state.processing_log.append({
                "stage": "global_analysis",
                "timestamp": str(asyncio.get_event_loop().time()),
                "status": "completed",
                "details": f"提取了{len(global_context.term_dictionary)}个术语，{len(global_context.key_messages)}个关键信息"
            })

            logger.info("全局内容分析完成",
                       terms_count=len(global_context.term_dictionary),
                       concepts_count=len(global_context.core_concepts))

        except Exception as e:
            logger.error("全局内容分析失败", error=e)
            state.processing_status = ProcessStatus.FAILED
            state.processing_log.append({
                "stage": "global_analysis",
                "timestamp": str(asyncio.get_event_loop().time()),
                "status": "failed",
                "error": str(e)
            })

        return state

    def outline_generation_node(self, state: OverallState) -> OverallState:
        """大纲生成节点"""
        logger.info("开始生成PPT大纲")

        try:
            # 构建大纲生成提示词
            global_context_dict = {
                "term_dictionary": state.global_context.term_dictionary,
                "key_messages": state.global_context.key_messages,
                "content_style": state.global_context.content_style,
                "target_audience": state.global_context.target_audience,
                "logical_structure": state.global_context.logical_structure
            }

            prompt = PromptBuilder.build_outline_prompt(state.source_content, global_context_dict)

            # 调用LLM生成大纲
            response = self.llm_manager.invoke_with_retry(prompt)

            # 解析大纲响应
            outline_result = self._parse_json_response(response)

            # 创建章节信息
            sections = []
            for section_data in outline_result.get("sections", []):
                section_info = SectionInfo(
                    section_id=section_data.get("section_id"),
                    title=section_data.get("title"),
                    subtitle=section_data.get("subtitle"),
                    order=section_data.get("order"),
                    estimated_slides=section_data.get("estimated_slides", 3),
                    content_outline=section_data.get("content_outline"),
                    key_points=section_data.get("key_points", []),
                    dependencies=section_data.get("dependencies", []),
                    context_requirements=section_data.get("context_requirements", []),
                    semantic_tags=section_data.get("semantic_tags", [])
                )
                sections.append(section_info)

            state.outline = outline_result
            state.sections = sections
            state.current_stage = "outline_generated"

            # 记录处理日志
            state.processing_log.append({
                "stage": "outline_generation",
                "timestamp": str(asyncio.get_event_loop().time()),
                "status": "completed",
                "details": f"生成了{len(sections)}个章节的大纲"
            })

            logger.info("PPT大纲生成完成", sections_count=len(sections))

        except Exception as e:
            logger.error("PPT大纲生成失败", error=e)
            state.processing_status = ProcessStatus.FAILED
            state.processing_log.append({
                "stage": "outline_generation",
                "timestamp": str(asyncio.get_event_loop().time()),
                "status": "failed",
                "error": str(e)
            })

        return state

    def section_processing_node(self, state: OverallState) -> OverallState:
        """章节处理节点（实现大并发，小串行）"""
        logger.info("开始章节并发处理")

        try:
            # 获取并发配置
            max_concurrent = config_manager.get_int("CONCURRENT_SECTIONS", 6)

            # 使用线程池进行并发处理
            with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
                # 为每个章节创建处理任务
                future_to_section = {}
                for section in state.sections:
                    future = executor.submit(self._process_single_section, section, state.global_context, state)
                    future_to_section[future] = section

                # 收集处理结果
                processed_sections = []
                for future in as_completed(future_to_section):
                    section = future_to_section[future]
                    try:
                        processed_section = future.result()
                        processed_sections.append(processed_section)
                        logger.info(f"章节 {section.title} 处理完成")
                    except Exception as e:
                        logger.error(f"章节 {section.title} 处理失败", error=e)
                        section.status = ProcessStatus.FAILED
                        state.failed_sections.append(section.section_id)
                        processed_sections.append(section)

            # 按顺序排序处理后的章节
            processed_sections.sort(key=lambda x: x.order)
            state.sections = processed_sections

            # 收集所有生成的幻灯片
            all_slides = []
            for section in processed_sections:
                all_slides.extend(section.slides)
            state.generated_slides = all_slides

            state.current_stage = "sections_processed"

            # 记录处理日志
            completed_sections = sum(1 for s in processed_sections if s.status == ProcessStatus.COMPLETED)
            state.processing_log.append({
                "stage": "section_processing",
                "timestamp": str(asyncio.get_event_loop().time()),
                "status": "completed",
                "details": f"并发处理了{len(processed_sections)}个章节，成功{completed_sections}个"
            })

            logger.info("章节并发处理完成",
                       total_sections=len(processed_sections),
                       completed_sections=completed_sections,
                       total_slides=len(all_slides))

        except Exception as e:
            logger.error("章节并发处理失败", error=e)
            state.processing_status = ProcessStatus.FAILED
            state.processing_log.append({
                "stage": "section_processing",
                "timestamp": str(asyncio.get_event_loop().time()),
                "status": "failed",
                "error": str(e)
            })

        return state

    def quality_enhancement_node(self, state: OverallState) -> OverallState:
        """质量检查和全局润色节点"""
        logger.info("开始质量检查和全局润色")

        try:
            # 全局润色
            all_sections_data = []
            for section in state.sections:
                section_data = {
                    "section_id": section.section_id,
                    "title": section.title,
                    "slides": [self._slide_to_dict(slide) for slide in section.slides]
                }
                all_sections_data.append(section_data)

            # 构建润色提示词
            global_context_dict = {
                "content_style": state.global_context.content_style,
                "logical_structure": state.global_context.logical_structure
            }

            prompt = PromptBuilder.build_polishing_prompt(
                all_sections_data,
                state.outline.get("title", "演示文稿"),
                global_context_dict
            )

            # 调用LLM进行润色
            response = self.llm_manager.invoke_with_retry(prompt)
            polishing_result = self._parse_json_response(response)

            # 应用润色结果（这里简化处理）
            logger.info("全局润色建议", improvements=polishing_result.get("overall_improvements", []))

            # 计算整体质量评分
            total_score = 0
            slide_count = 0
            for section in state.sections:
                for slide in section.slides:
                    if slide.quality_score:
                        total_score += slide.quality_score
                        slide_count += 1

            if slide_count > 0:
                state.overall_quality_score = total_score / slide_count

            state.current_stage = "quality_enhanced"
            state.processing_status = ProcessStatus.COMPLETED

            # 记录处理日志
            state.processing_log.append({
                "stage": "quality_enhancement",
                "timestamp": str(asyncio.get_event_loop().time()),
                "status": "completed",
                "details": f"整体质量评分: {state.overall_quality_score:.1f}"
            })

            logger.info("质量检查和全局润色完成", overall_score=state.overall_quality_score)

        except Exception as e:
            logger.error("质量检查和全局润色失败", error=e)
            state.processing_log.append({
                "stage": "quality_enhancement",
                "timestamp": str(asyncio.get_event_loop().time()),
                "status": "failed",
                "error": str(e)
            })

        return state

    def _process_single_section(self, section: SectionInfo, global_context: GlobalContext,
                               overall_state: OverallState) -> SectionInfo:
        """处理单个章节（串行生成幻灯片）"""
        logger.info(f"开始处理章节: {section.title}")

        try:
            section.status = ProcessStatus.IN_PROGRESS

            # 获取前面章节的总结
            preceding_summaries = []
            for s in overall_state.sections:
                if s.order < section.order and s.status == ProcessStatus.COMPLETED:
                    for slide in s.slides:
                        if slide.semantic_summary:
                            preceding_summaries.append(slide.semantic_summary)

            # 构建章节处理提示词
            section_dict = {
                "title": section.title,
                "content_outline": section.content_outline,
                "key_points": section.key_points,
                "estimated_slides": section.estimated_slides
            }

            global_context_dict = {
                "term_dictionary": global_context.term_dictionary,
                "content_style": global_context.content_style,
                "presentation_tone": global_context.presentation_tone
            }

            prompt = PromptBuilder.build_section_prompt(
                section_dict, global_context_dict, preceding_summaries
            )

            # 调用LLM生成章节内容
            response = self.llm_manager.invoke_with_retry(prompt)
            section_result = self._parse_json_response(response)

            # 创建幻灯片对象
            slides = []
            for slide_data in section_result.get("slides", []):
                slide = SlideContent(
                    slide_id=slide_data.get("slide_id"),
                    title=slide_data.get("title"),
                    content_type=slide_data.get("content_type", "text"),
                    main_content=slide_data.get("main_content", ""),
                    bullet_points=slide_data.get("bullet_points", []),
                    chart_config=slide_data.get("chart_config"),
                    layout=slide_data.get("layout", {}),
                    semantic_summary=slide_data.get("semantic_summary", ""),
                    key_concepts=slide_data.get("key_concepts", [])
                )

                # 质量评估
                score, evaluation = quality_controller.evaluate_slide(slide, global_context)
                slide.quality_score = score

                # 如果质量不达标，进行重试
                max_retries = config_manager.get_int("MAX_RETRY_COUNT", 3)
                retry_count = 0

                while (not evaluation["passed"] and retry_count < max_retries):
                    retry_count += 1
                    logger.warning(f"幻灯片 {slide.slide_id} 质量不达标，进行第{retry_count}次重试")

                    # 重新生成（这里简化处理）
                    # 实际应该根据评估结果调整提示词
                    response = self.llm_manager.invoke_with_retry(prompt)
                    section_result = self._parse_json_response(response)

                    # 更新幻灯片内容
                    if section_result.get("slides") and len(section_result["slides"]) > 0:
                        new_slide_data = section_result["slides"][0]  # 简化：只取第一个
                        slide.title = new_slide_data.get("title", slide.title)
                        slide.main_content = new_slide_data.get("main_content", slide.main_content)
                        slide.bullet_points = new_slide_data.get("bullet_points", slide.bullet_points)

                        # 重新评估
                        score, evaluation = quality_controller.evaluate_slide(slide, global_context)
                        slide.quality_score = score

                slide.retry_count = retry_count
                slides.append(slide)

            section.slides = slides
            section.status = ProcessStatus.COMPLETED

            logger.info(f"章节 {section.title} 处理完成，生成了{len(slides)}个幻灯片")

        except Exception as e:
            logger.error(f"章节 {section.title} 处理失败", error=e)
            section.status = ProcessStatus.FAILED

        return section

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """解析JSON响应"""
        try:
            # 尝试提取JSON部分
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                json_str = response[start:end].strip()
            else:
                json_str = response.strip()

            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error("JSON解析失败", error=e, response=response[:200])
            return {}

    def _slide_to_dict(self, slide: SlideContent) -> Dict[str, Any]:
        """将幻灯片对象转换为字典"""
        return {
            "slide_id": slide.slide_id,
            "title": slide.title,
            "content_type": slide.content_type,
            "main_content": slide.main_content,
            "bullet_points": slide.bullet_points,
            "chart_config": slide.chart_config,
            "layout": slide.layout,
            "quality_score": slide.quality_score,
            "semantic_summary": slide.semantic_summary
        }


# 创建全局图实例
ppt_graph_builder = PPTGraphBuilder()
ppt_graph = ppt_graph_builder.create_graph()