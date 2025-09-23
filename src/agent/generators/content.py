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
    """
    滑动窗口内容生成器
    
    使用滑动窗口策略串行生成每页内容，维护上下文连贯性。
    支持质量评估和反思优化机制。
    """
    
    def __init__(self, model_provider: str = "openai"):
        """初始化内容生成器"""
        self.model_provider = model_provider
        self.model_name = None
        self.llm = None
        self._initialize_model()
        
        # 新增：质量评估器
        from ..evaluators.quality import QualityEvaluator
        self.quality_evaluator = QualityEvaluator(model_provider)
        
        # 配置参数
        config = ConfigManager()
        self.enable_reflection = config.get("ENABLE_QUALITY_REFLECTION", "true").lower() == "true"
        
        logger.info(f"滑动窗口内容生成器初始化完成，质量反思: {'启用' if self.enable_reflection else '禁用'}")

    def _initialize_model(self):
        """初始化AI模型"""
        config = ConfigManager()
        try:
            if self.model_provider == "openai":
                self.model_name = config.get("OPENAI_MODEL", "gpt-3.5-turbo")
                self.llm = ChatOpenAI(
                    model=self.model_name,
                    temperature=float(config.get("GENERATION_TEMPERATURE", "0.7")),
                    max_tokens=int(config.get("MAX_TOKENS", "2000")),
                    timeout=int(config.get("MODEL_TIMEOUT", "60"))
                )
            elif self.model_provider == "google":
                self.model_name = config.get("GOOGLE_MODEL", "gemini-pro")
                self.llm = ChatGoogleGenerativeAI(
                    model=self.model_name,
                    temperature=float(config.get("GENERATION_TEMPERATURE", "0.7")),
                    max_tokens=int(config.get("MAX_TOKENS", "2000")),
                    timeout=int(config.get("MODEL_TIMEOUT", "60"))
                )
            else:
                raise ValueError(f"不支持的模型提供商: {self.model_provider}")
                
            logger.info(f"模型初始化成功: {self.model_provider} - {self.model_name}")
        except Exception as e:
            logger.error(f"模型初始化失败: {e}")
            raise

    def generate_all_slides(self, state: OverallState) -> OverallState:
        """
        生成所有幻灯片内容（支持质量反思机制）
        
        Args:
            state: 包含演示大纲的状态
            
        Returns:
            更新后的状态，包含生成的幻灯片
        """
        if not state.outline or not state.outline.sections:
            logger.error("生成幻灯片前需要先生成大纲")
            state.errors.append("缺少演示大纲，无法生成幻灯片")
            return state

        logger.info(f"开始生成幻灯片，总计 {len(state.outline.sections)} 个章节")
        
        slides = []
        slide_id = 1
        
        # 生成标题页
        title_slide = self._generate_title_slide(state.outline, slide_id)
        slides.append(title_slide)
        slide_id += 1
        
        # 逐个章节生成内容
        for section_idx, section in enumerate(state.outline.sections):
            logger.info(f"生成第 {section_idx + 1} 章节: {section.title}")
            
            # 章节标题页
            if section.title:
                section_title_slide = self._generate_section_title_slide(
                    section, slide_id, state.outline
                )
                slides.append(section_title_slide)
                slide_id += 1
            
            # 章节内容页面
            for point_idx, key_point in enumerate(section.key_points):
                logger.info(f"生成内容页 {slide_id}: {key_point[:50]}...")
                
                # 生成幻灯片（支持质量反思）
                content_slide = self._generate_single_slide_with_reflection(
                    state, slides, slide_id, section, key_point
                )
                
                if content_slide:
                    slides.append(content_slide)
                    
                    # 创建并添加滑动摘要
                    sliding_summary = self._create_sliding_summary(content_slide, slides)
                    self._add_sliding_summary(state, sliding_summary)
                    
                slide_id += 1
        
        # 生成结束页
        if len(slides) > 1:
            conclusion_slide = self._generate_conclusion_slide(state.outline, slide_id)
            slides.append(conclusion_slide)
        
        # 更新状态
        state.slides = slides
        state.generation_completed = True
        
        logger.info(f"幻灯片生成完成，共生成 {len(slides)} 页")
        return state

    def _generate_single_slide_with_reflection(
        self, 
        state: OverallState, 
        existing_slides: List[SlideContent], 
        slide_id: int, 
        section: Any, 
        key_point: str
    ) -> Optional[SlideContent]:
        """
        生成单张幻灯片（支持质量反思机制）
        
        Args:
            state: 当前状态
            existing_slides: 已生成的幻灯片列表
            slide_id: 幻灯片ID
            section: 当前章节
            key_point: 当前要点
            
        Returns:
            生成的幻灯片内容
        """
        # 首次生成（初始模式）
        slide = self._generate_single_slide(state, existing_slides, slide_id, section, key_point)
        
        if not slide or not self.enable_reflection:
            return slide
            
        # 质量评估和反思优化
        retry_count = 0
        max_retries = self.quality_evaluator.max_retry_count
        
        while retry_count < max_retries:
            try:
                # 质量评估
                quality_score, suggestions = self.quality_evaluator.evaluate_slide(
                    slide=slide,
                    outline=state.outline,
                    context_slides=existing_slides[-3:] if existing_slides else None
                )
                
                # 记录评估结果
                logger.info(f"幻灯片 {slide_id} 质量评分: {quality_score.total_score:.1f}")
                
                # 判断是否需要重新生成
                if not self.quality_evaluator.should_regenerate(quality_score, retry_count):
                    # 达到质量要求或超过重试次数，接受当前结果
                    if quality_score.pass_threshold:
                        logger.info(f"幻灯片 {slide_id} 质量达标，接受结果")
                    else:
                        logger.warning(f"幻灯片 {slide_id} 质量未达标但已达最大重试次数，接受当前结果")
                        state.warnings.append(f"第{slide_id}页质量评分 {quality_score.total_score:.1f} 低于阈值")
                    break
                
                # 需要重新生成
                retry_count += 1
                logger.info(f"开始第 {retry_count} 次质量优化重试")
                
                # 格式化反馈信息
                feedback = self.quality_evaluator.format_feedback_for_regeneration(
                    quality_score, suggestions
                )
                
                # 基于反馈重新生成（优化模式）
                optimized_slide = self._regenerate_slide_with_quality_feedback(
                    slide=slide,
                    feedback=feedback,
                    state=state,
                    existing_slides=existing_slides,
                    section=section,
                    key_point=key_point
                )
                
                if optimized_slide:
                    slide = optimized_slide
                else:
                    logger.warning(f"第 {retry_count} 次重新生成失败，保持原内容")
                    break
                    
            except Exception as e:
                logger.error(f"质量评估过程出错: {e}")
                break
        
        return slide

    def _generate_single_slide(
        self, 
        state: OverallState, 
        existing_slides: List[SlideContent], 
        slide_id: int, 
        section: Any, 
        key_point: str
    ) -> Optional[SlideContent]:
        """
        生成单张幻灯片（原始方法，初始生成模式）
        
        Args:
            state: 当前状态  
            existing_slides: 已生成的幻灯片列表
            slide_id: 幻灯片ID
            section: 当前章节
            key_point: 当前要点
            
        Returns:
            生成的幻灯片内容
        """
        try:
            # 获取滑动窗口上下文
            temp_state = OverallState(
                outline=state.outline,
                slides=existing_slides,
                sliding_summaries=state.sliding_summaries
            )
            context_info = self._get_sliding_window_context(temp_state)
            
            # 构建生成提示词
            prompt = PromptBuilder.build_content_generation_prompt(
                outline=state.outline,
                section=section,
                key_point=key_point,
                slide_id=slide_id,
                context_info=context_info
            )
            
            # 调用模型生成内容
            response = self._call_model_for_content(prompt)
            
            # 解析响应
            slide_data = self._parse_slide_response(response, slide_id)
            
            # 创建幻灯片对象
            slide = self._create_slide_object(slide_data)
            
            logger.info(f"幻灯片 {slide_id} 初始生成完成")
            return slide
            
        except Exception as e:
            logger.error(f"生成幻灯片 {slide_id} 失败: {e}")
            return self._create_fallback_slide_data(slide_id, key_point)

    def _regenerate_slide_with_quality_feedback(
        self,
        slide: SlideContent,
        feedback: str,
        state: OverallState,
        existing_slides: List[SlideContent],
        section: Any,
        key_point: str
    ) -> Optional[SlideContent]:
        """
        基于质量反馈重新生成幻灯片（优化模式）
        
        Args:
            slide: 原始幻灯片
            feedback: 质量反馈信息
            state: 当前状态
            existing_slides: 已生成的幻灯片列表
            section: 当前章节
            key_point: 当前要点
            
        Returns:
            优化后的幻灯片内容
        """
        try:
            # 获取上下文信息
            temp_state = OverallState(
                outline=state.outline,
                slides=existing_slides,
                sliding_summaries=state.sliding_summaries
            )
            context_info = self._get_sliding_window_context(temp_state)
            
            # 构建优化提示词
            prompt = self._build_optimization_prompt(
                original_slide=slide,
                feedback=feedback,
                outline=state.outline,
                section=section,
                key_point=key_point,
                context_info=context_info
            )
            
            # 调用模型重新生成
            response = self._call_model_for_content(prompt)
            
            # 解析新内容
            slide_data = self._parse_slide_response(response, slide.slide_id)
            
            # 创建优化后的幻灯片对象
            optimized_slide = self._create_slide_object(slide_data)
            
            logger.info(f"幻灯片 {slide.slide_id} 质量优化完成")
            return optimized_slide
            
        except Exception as e:
            logger.error(f"质量优化重新生成失败: {e}")
            return None

    def _build_optimization_prompt(
        self,
        original_slide: SlideContent,
        feedback: str,
        outline: Any,
        section: Any,
        key_point: str,
        context_info: str
    ) -> str:
        """构建优化模式的提示词"""
        
        prompt = f"""
你是专业的PPT内容优化专家。请根据质量反馈优化以下幻灯片内容。

**演示大纲信息:**
- 主题: {outline.title}
- 目标: {outline.objective if hasattr(outline, 'objective') else '信息传达'}

**当前章节:** {section.title}
**核心要点:** {key_point}

**原始幻灯片内容:**
- 标题: {original_slide.title}
- 类型: {original_slide.slide_type.value}
- 主要内容: {original_slide.main_content}
- 要点: {', '.join(original_slide.bullet_points) if original_slide.bullet_points else '无'}
- 演讲注释: {original_slide.speaker_notes if original_slide.speaker_notes else '无'}

{context_info}

**质量反馈和优化要求:**
{feedback}

**优化指导原则:**
1. 优先解决高优先级问题
2. 保持与原始内容的连贯性
3. 确保与演示主题和章节目标的一致性
4. 优化语言表达的清晰度和专业性
5. 合理控制信息密度和层次结构

请根据反馈重新生成优化后的幻灯片内容，确保解决指出的质量问题。

**输出格式要求:**
请严格按照以下JSON格式输出：

```json
{{
    "title": "优化后的幻灯片标题",
    "slide_type": "content",
    "main_content": "优化后的主要内容描述",
    "bullet_points": ["要点1", "要点2", "要点3"],
    "speaker_notes": "优化后的演讲者注释",
    "design_suggestions": "视觉设计建议"
}}
```
"""
        return prompt

    def _get_sliding_window_context(self, state: OverallState) -> str:
        """
        获取滑动窗口上下文信息
        
        Args:
            state: 当前状态
            
        Returns:
            上下文信息字符串
        """
        from ..utils import ConfigManager
        config = ConfigManager()
        window_size = int(config.get("SLIDING_WINDOW_SIZE", "3"))
        
        if not state.sliding_summaries:
            return "**上下文信息:** 这是演示的开始部分。"
        
        # 获取最近的摘要
        recent_summaries = state.sliding_summaries[-window_size:]
        
        context_lines = ["**滑动窗口上下文:**"]
        for i, summary in enumerate(recent_summaries):
            context_lines.append(f"第{summary.slide_id}页摘要: {summary.main_message}")
            if summary.key_concepts:
                context_lines.append(f"  关键概念: {', '.join(summary.key_concepts)}")
        
        context_lines.append("\n**连贯性要求:** 新内容应与以上上下文保持逻辑连贯。")
        
        return "\n".join(context_lines)

    def _call_model_for_content(self, prompt: str) -> str:
        """调用AI模型生成内容"""
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return response.content
        except Exception as e:
            logger.error(f"模型调用失败: {e}")
            raise

    def _parse_slide_response(self, response: str, slide_id: int) -> Dict:
        """解析模型响应"""
        try:
            import json
            import re
            
            # 提取JSON部分
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 尝试直接解析
                json_str = response.strip()
            
            slide_data = json.loads(json_str)
            slide_data["slide_id"] = slide_id
            
            return slide_data
            
        except Exception as e:
            logger.error(f"解析幻灯片响应失败: {e}")
            logger.debug(f"原始响应: {response}")
            
            # 返回基本的降级数据
            return self._create_fallback_slide_data(slide_id, "解析失败的内容")

    def _create_fallback_slide_data(self, slide_id: int, content: str) -> Dict:
        """创建降级幻灯片数据"""
        return {
            "slide_id": slide_id,
            "title": f"幻灯片 {slide_id}",
            "slide_type": "content",
            "main_content": content,
            "bullet_points": ["内容生成遇到技术问题", "请手动检查和完善此页内容"],
            "speaker_notes": "此页面需要手动完善内容",
            "design_suggestions": "使用简洁的布局"
        }

    def _create_slide_object(self, slide_data: Dict) -> SlideContent:
        """创建幻灯片对象"""
        from ..state import SlideContent, SlideType
        
        # 确保slide_type是有效的枚举值
        slide_type_str = slide_data.get("slide_type", "content")
        try:
            slide_type = SlideType(slide_type_str)
        except ValueError:
            slide_type = SlideType.CONTENT
        
        return SlideContent(
            slide_id=slide_data["slide_id"],
            title=slide_data.get("title", ""),
            slide_type=slide_type,
            main_content=slide_data.get("main_content", ""),
            bullet_points=slide_data.get("bullet_points", []),
            speaker_notes=slide_data.get("speaker_notes", ""),
            design_suggestions=slide_data.get("design_suggestions", "")
        )

    def _generate_title_slide(self, outline: Any, slide_id: int) -> SlideContent:
        """生成标题页"""
        from ..state import SlideContent, SlideType
        
        return SlideContent(
            slide_id=slide_id,
            title=outline.title,
            slide_type=SlideType.TITLE,
            main_content=f"主题: {outline.title}",
            bullet_points=[],
            speaker_notes=f"欢迎参加关于{outline.title}的演示",
            design_suggestions="使用大字体标题，简洁的布局"
        )

    def _generate_section_title_slide(self, section: Any, slide_id: int, outline: Any) -> SlideContent:
        """生成章节标题页"""
        from ..state import SlideContent, SlideType
        
        return SlideContent(
            slide_id=slide_id,
            title=section.title,
            slide_type=SlideType.SECTION_TITLE,
            main_content=f"章节: {section.title}",
            bullet_points=[],
            speaker_notes=f"现在我们来讨论{section.title}",
            design_suggestions="突出章节标题，可添加章节图标"
        )

    def _generate_conclusion_slide(self, outline: Any, slide_id: int) -> SlideContent:
        """生成结束页"""
        from ..state import SlideContent, SlideType
        
        return SlideContent(
            slide_id=slide_id,
            title="总结",
            slide_type=SlideType.CONCLUSION,
            main_content=f"关于{outline.title}的演示到此结束",
            bullet_points=["感谢您的聆听", "期待与您的交流"],
            speaker_notes="总结要点，感谢听众",
            design_suggestions="简洁的感谢页面设计"
        )

    def _create_sliding_summary(self, slide: SlideContent, existing_slides: List[SlideContent]) -> Any:
        """创建滑动摘要"""
        from ..state import SlidingSummary
        
        # 确定逻辑连接
        logical_connection = self._determine_logical_connection(slide, existing_slides)
        
        return SlidingSummary(
            slide_id=slide.slide_id,
            main_message=slide.main_content[:100] + "..." if len(slide.main_content) > 100 else slide.main_content,
            key_concepts=slide.bullet_points[:3] if slide.bullet_points else [],
            logical_connection=logical_connection
        )

    def _determine_logical_connection(self, slide: SlideContent, existing_slides: List[SlideContent]) -> str:
        """确定逻辑连接关系"""
        if not existing_slides:
            return "introduction"
        
        # 简单的逻辑关系判断
        if "总结" in slide.title or "结论" in slide.title:
            return "conclusion"
        elif "例如" in slide.main_content or "示例" in slide.main_content:
            return "example"
        elif "因此" in slide.main_content or "所以" in slide.main_content:
            return "consequence"
        else:
            return "continuation"

    def _add_sliding_summary(self, state: OverallState, summary: Any):
        """添加滑动摘要到状态"""
        if not hasattr(state, 'sliding_summaries') or state.sliding_summaries is None:
            state.sliding_summaries = []
        state.sliding_summaries.append(summary)

    # 保留原有的regenerate_slide_with_quality_feedback方法用于向后兼容
    def regenerate_slide_with_quality_feedback(
        self,
        state: OverallState,
        slide_id: int,
        quality_issues: List[str],
        max_retries: int = 2
    ) -> Optional[SlideContent]:
        """
        基于质量反馈重新生成幻灯片（向后兼容方法）
        
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