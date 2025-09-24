"""
LangGraph工作流定义模块

定义PPT生成的完整工作流程，实现简化的状态管理策略。
采用串行处理避免复杂的并发控制，通过滑动窗口策略保持内容连贯性。
"""

from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import OverallState
from .generators import OutlineGenerator, SlidingWindowContentGenerator, StyleSelector
from .renderers import HTMLRenderer
from .utils import logger, performance_monitor, FileHandler, result_saver


class PPTAgentGraph:
    """PPT智能体工作流图"""

    def __init__(self, model_provider: str = "openai", model_name: str = "gpt-3.5-turbo"):
        """
        初始化PPT智能体工作流

        Args:
            model_provider: 模型提供商 ("openai" 或 "google")
            model_name: 模型名称
        """
        self.model_provider = model_provider
        self.model_name = model_name

        # 初始化组件
        self.outline_generator = OutlineGenerator(model_provider, model_name)
        self.content_generator = SlidingWindowContentGenerator(model_provider, model_name)
        self.style_selector = StyleSelector(model_provider, model_name)
        self.html_renderer = HTMLRenderer()

        # 构建工作流图
        self.graph = self._build_graph()

        # 初始化错误恢复管理器
        from .recovery.error_recovery import ErrorRecoveryManager
        self.recovery_manager = ErrorRecoveryManager()
        
        # 为所有组件设置错误恢复管理器
        if hasattr(self.content_generator, 'recovery_manager'):
            self.content_generator.recovery_manager = self.recovery_manager

    def _build_graph(self) -> StateGraph:
        """构建LangGraph工作流图"""
        logger.info("构建PPT生成工作流图")

        # 创建状态图
        workflow = StateGraph(OverallState)

        # 添加节点
        workflow.add_node("validate_input", self._validate_input_node)
        workflow.add_node("generate_outline", self._generate_outline_node)
        workflow.add_node("select_style", self._select_style_node)
        workflow.add_node("generate_content", self._generate_content_node)
        workflow.add_node("render_html", self._render_html_node)
        workflow.add_node("save_results", self._save_results_node)

        # 定义工作流路径
        workflow.set_entry_point("validate_input")

        # 添加边（定义执行顺序）
        workflow.add_edge("validate_input", "generate_outline")
        workflow.add_edge("generate_outline", "select_style")
        workflow.add_edge("select_style", "generate_content")
        workflow.add_edge("generate_content", "render_html")
        workflow.add_edge("render_html", "save_results")
        workflow.add_edge("save_results", END)

        # 编译图
        memory = MemorySaver()
        app = workflow.compile(checkpointer=memory)

        logger.info("工作流图构建完成")
        return app

    def _validate_input_node(self, state: OverallState) -> OverallState:
        """验证输入节点（增强错误恢复版本）"""
        logger.info("步骤1: 验证输入数据")
        performance_monitor.start_timer("input_validation")

        error_context = {
            "operation": "input_validation",
            "node": "validate_input",
            "original_function": lambda: self._validate_input_core(state)
        }

        try:
            return self._validate_input_core(state)
            
        except Exception as e:
            logger.warning(f"输入验证失败，尝试错误恢复: {e}")
            
            try:
                recovery_result = self.recovery_manager.handle_error(e, error_context, state)
                if recovery_result and isinstance(recovery_result, bool):
                    logger.info("输入验证通过错误恢复继续")
                    return state
                else:
                    logger.error("输入验证错误恢复失败")
                    state.errors.append(f"输入验证失败: {str(e)}")
                    return state
                    
            except Exception as recovery_error:
                logger.error(f"输入验证错误恢复也失败: {recovery_error}")
                state.errors.append(f"输入验证失败: {str(e)}")
                performance_monitor.end_timer("input_validation")
                return state

    def _validate_input_core(self, state: OverallState) -> OverallState:
        """输入验证的核心逻辑"""
        # 检查必要的输入
        if not state.input_text.strip():
            if state.input_file_path:
                # 从文件读取
                try:
                    state.input_text = FileHandler.read_text_file(state.input_file_path)
                    logger.info(f"从文件读取内容: {state.input_file_path}")
                except Exception as e:
                    error_msg = f"读取文件失败: {e}"
                    logger.error(error_msg)
                    state.errors.append(error_msg)
                    raise e
            else:
                error_msg = "缺少输入文本或文件路径"
                logger.error(error_msg)
                state.errors.append(error_msg)
                raise ValueError(error_msg)

        # 验证文本长度
        if len(state.input_text.strip()) < 50:
            warning_msg = "输入文本较短，可能影响生成质量"
            logger.warning(warning_msg)
            state.warnings.append(warning_msg)

        # 设置默认配置
        if state.sliding_window_size <= 0:
            state.sliding_window_size = 3

        if state.quality_threshold <= 0:
            state.quality_threshold = 0.8

        duration = performance_monitor.end_timer("input_validation")
        logger.info(f"输入验证完成，耗时: {duration:.2f}s")

        return state

    def _generate_outline_node(self, state: OverallState) -> OverallState:
        """生成大纲节点（增强错误恢复版本）"""
        logger.info("步骤2: 生成演示大纲")

        # 如果有错误，跳过处理
        if state.errors:
            logger.warning("跳过大纲生成：存在输入错误")
            return state

        error_context = {
            "operation": "outline_generation",
            "node": "generate_outline",
            "original_function": lambda: self.outline_generator.generate_outline(state),
            "input_text_length": len(state.input_text)
        }

        try:
            # 调用大纲生成器
            state = self.outline_generator.generate_outline(state)

            # 验证大纲
            if state.outline:
                validation_issues = self.outline_generator.validate_outline(state.outline)
                if validation_issues:
                    logger.warning(f"大纲验证发现问题: {len(validation_issues)}个")
                    for issue in validation_issues:
                        state.warnings.append(f"大纲问题: {issue}")

                    # 尝试优化大纲
                    state.outline = self.outline_generator.optimize_outline(state.outline)
                    logger.info("大纲已优化")

            return state

        except Exception as e:
            logger.warning(f"大纲生成失败，尝试错误恢复: {e}")
            
            try:
                recovery_result = self.recovery_manager.handle_error(e, error_context, state)
                
                # 如果恢复成功，使用恢复的结果
                if recovery_result and hasattr(recovery_result, 'outline'):
                    state.outline = recovery_result.outline
                    logger.info("大纲生成通过错误恢复成功")
                elif isinstance(recovery_result, dict) and 'simplified_outline' in recovery_result:
                    # 使用简化的大纲
                    state = self._apply_simplified_outline(state, recovery_result['simplified_outline'])
                    logger.info("应用简化大纲")
                else:
                    logger.error("大纲生成错误恢复失败")
                    state.errors.append(f"大纲生成失败: {str(e)}")
                    
                return state
                
            except Exception as recovery_error:
                logger.error(f"大纲生成错误恢复也失败: {recovery_error}")
                state.errors.append(f"大纲生成失败: {str(e)}")
                return state

    def _apply_simplified_outline(self, state: OverallState, simplified_outline: Dict[str, Any]) -> OverallState:
        """应用简化的大纲结构"""
        from .state import PresentationOutline, OutlineSection
        
        try:
            # 创建简化的大纲对象
            title = simplified_outline.get('title', '演示文稿')
            sections_data = simplified_outline.get('sections', [])
            
            sections = []
            for i, section_data in enumerate(sections_data, 1):
                section = OutlineSection(
                    section_id=i,
                    title=section_data.get('title', f'第{i}部分'),
                    key_points=section_data.get('key_points', [f'要点{i}']),
                    estimated_slides=section_data.get('slides', 1)
                )
                sections.append(section)
            
            # 如果没有章节，创建默认章节
            if not sections:
                sections = [
                    OutlineSection(
                        section_id=1,
                        title='主要内容',
                        key_points=['核心观点', '重要信息', '总结要点'],
                        estimated_slides=3
                    )
                ]
            
            state.outline = PresentationOutline(
                title=title,
                total_slides=sum(s.estimated_slides for s in sections),
                sections=sections,
                target_audience=simplified_outline.get('audience', '通用听众'),
                estimated_duration=simplified_outline.get('duration', 10)
            )
            
            logger.info(f"成功应用简化大纲，包含{len(sections)}个章节")
            return state
            
        except Exception as e:
            logger.error(f"应用简化大纲失败: {e}")
            state.errors.append(f"应用简化大纲失败: {str(e)}")
            return state

    def _select_style_node(self, state: OverallState) -> OverallState:
        """选择样式节点"""
        logger.info("步骤3: 选择演示样式")

        try:
            # 如果有错误，跳过处理
            if state.errors:
                logger.warning("跳过样式选择：存在错误")
                return state

            # 调用样式选择器
            state = self.style_selector.select_style_theme(state)

            logger.info(f"选择样式主题: {state.selected_theme.value}")
            return state

        except Exception as e:
            logger.error(f"样式选择节点失败: {e}")
            state.errors.append(f"样式选择失败: {str(e)}")
            return state

    def _generate_content_node(self, state: OverallState) -> OverallState:
        """生成内容节点（核心节点 - 增强错误恢复版本）"""
        logger.info("步骤4: 生成幻灯片内容（滑动窗口策略）")

        # 如果有错误，跳过处理
        if state.errors:
            logger.warning("跳过内容生成：存在错误")
            return state

        # 检查是否有大纲
        if not state.outline:
            error_msg = "无法生成内容：缺少演示大纲"
            logger.error(error_msg)
            state.errors.append(error_msg)
            return state

        error_context = {
            "operation": "content_generation",
            "node": "generate_content",
            "outline_sections": len(state.outline.sections),
            "expected_slides": state.outline.total_slides,
            "original_function": lambda: self.content_generator.generate_all_slides(state)
        }

        try:
            # 调用滑动窗口内容生成器
            state = self.content_generator.generate_all_slides(state)

            # 生成统计信息
            successful_slides = len(state.slides)
            expected_slides = state.outline.total_slides

            logger.info(f"内容生成完成: {successful_slides}/{expected_slides} 页")

            # 检查生成成功率
            success_rate = successful_slides / expected_slides if expected_slides > 0 else 0
            if success_rate < 0.8:  # 如果成功率低于80%
                warning_msg = f"生成成功率较低: {successful_slides}/{expected_slides} ({success_rate:.1%})"
                logger.warning(warning_msg)
                state.warnings.append(warning_msg)
                
                # 如果成功率过低，尝试补充内容
                if success_rate < 0.5:
                    logger.info("成功率过低，尝试补充缺失的幻灯片")
                    state = self._supplement_missing_slides(state)

            return state

        except Exception as e:
            logger.warning(f"内容生成失败，尝试错误恢复: {e}")
            
            try:
                recovery_result = self.recovery_manager.handle_error(e, error_context, state)
                
                if recovery_result and hasattr(recovery_result, 'slides'):
                    # 使用恢复的幻灯片内容
                    state.slides = recovery_result.slides
                    logger.info("内容生成通过错误恢复成功")
                elif isinstance(recovery_result, list):
                    # 直接是幻灯片列表
                    state.slides.extend(recovery_result)
                    logger.info(f"通过错误恢复补充了 {len(recovery_result)} 张幻灯片")
                else:
                    # 使用降级方案生成基础内容
                    logger.warning("使用降级方案生成基础内容")
                    state = self._generate_fallback_content(state)
                    
                return state
                
            except Exception as recovery_error:
                logger.error(f"内容生成错误恢复也失败: {recovery_error}")
                # 作为最后手段，生成最基础的内容
                state = self._generate_emergency_content(state)
                state.errors.append(f"内容生成失败，已使用紧急降级: {str(e)}")
                return state

    def _supplement_missing_slides(self, state: OverallState) -> OverallState:
        """补充缺失的幻灯片"""
        if not state.outline:
            return state
            
        current_slide_count = len(state.slides)
        expected_slide_count = state.outline.total_slides
        missing_count = expected_slide_count - current_slide_count
        
        if missing_count <= 0:
            return state
            
        logger.info(f"尝试补充 {missing_count} 张缺失的幻灯片")
        
        # 找出缺失的幻灯片ID
        existing_ids = {slide.slide_id for slide in state.slides}
        missing_ids = []
        
        slide_id = 1
        for section in state.outline.sections:
            for point in section.key_points:
                if slide_id not in existing_ids:
                    missing_ids.append((slide_id, section, point))
                slide_id += 1
                
        # 为缺失的幻灯片生成基础内容
        for slide_id, section, key_point in missing_ids[:missing_count]:
            try:
                fallback_slide = self._create_emergency_slide(slide_id, section.title, key_point)
                state.slides.append(fallback_slide)
                logger.info(f"补充了幻灯片 {slide_id}: {fallback_slide.title}")
            except Exception as e:
                logger.error(f"补充幻灯片 {slide_id} 失败: {e}")
                
        # 按slide_id排序
        state.slides.sort(key=lambda x: x.slide_id)
        
        return state

    def _generate_fallback_content(self, state: OverallState) -> OverallState:
        """生成降级内容"""
        if not state.outline:
            return state
            
        logger.info("生成降级内容")
        
        state.slides = []
        slide_id = 1
        
        # 为每个章节生成基础幻灯片
        for section in state.outline.sections:
            for key_point in section.key_points:
                try:
                    fallback_slide = self._create_emergency_slide(slide_id, section.title, key_point)
                    state.slides.append(fallback_slide)
                    slide_id += 1
                except Exception as e:
                    logger.error(f"生成降级幻灯片 {slide_id} 失败: {e}")
                    slide_id += 1
                    
        logger.info(f"降级内容生成完成，共 {len(state.slides)} 张幻灯片")
        return state

    def _generate_emergency_content(self, state: OverallState) -> OverallState:
        """生成紧急内容（最后的降级方案）"""
        logger.warning("启用紧急内容生成")
        
        from .state import SlideContent, SlideType, SlideLayout
        
        # 创建最基础的幻灯片
        emergency_slides = []
        
        # 标题页
        title_slide = SlideContent(
            slide_id=1,
            title=state.outline.title if state.outline else "演示文稿",
            content="# 演示文稿\n\n本演示文稿由系统自动生成\n\n*请在演示前补充详细内容*",
            key_points=["自动生成内容", "需要人工补充"],
            slide_type=SlideType.TITLE,
            layout=SlideLayout.TITLE,
            speaker_notes="这是紧急生成的标题页"
        )
        emergency_slides.append(title_slide)
        
        # 主要内容页
        if state.outline and state.outline.sections:
            for i, section in enumerate(state.outline.sections, 2):
                content_slide = SlideContent(
                    slide_id=i,
                    title=section.title,
                    content=f"## {section.title}\n\n" + "\n".join([f"• {point}" for point in section.key_points]),
                    key_points=section.key_points,
                    slide_type=SlideType.CONTENT,
                    layout=SlideLayout.STANDARD,
                    speaker_notes=f"第{i}页：{section.title}的演讲备注"
                )
                emergency_slides.append(content_slide)
        else:
            # 如果连大纲都没有，创建通用内容
            content_slide = SlideContent(
                slide_id=2,
                title="主要内容",
                content="## 主要内容\n\n• 内容正在准备中\n• 请参考相关资料\n• 详细信息待补充",
                key_points=["内容准备中", "参考资料", "待补充"],
                slide_type=SlideType.CONTENT,
                layout=SlideLayout.STANDARD,
                speaker_notes="第2页：主要内容的演讲备注"
            )
            emergency_slides.append(content_slide)
        
        state.slides = emergency_slides
        logger.info(f"紧急内容生成完成，共 {len(emergency_slides)} 张幻灯片")
        
        return state

    def _create_emergency_slide(self, slide_id: int, section_title: str, key_point: str) -> 'SlideContent':
        """创建紧急幻灯片"""
        from .state import SlideContent, SlideType, SlideLayout
        
        title = key_point[:50] + "..." if len(key_point) > 50 else key_point
        if not title.strip():
            title = f"{section_title} - 第{slide_id}页"
            
        content = f"## {title}\n\n### 主要内容\n{key_point}\n\n### 补充说明\n• 详细内容待补充\n• 请参考相关资料"
        
        return SlideContent(
            slide_id=slide_id,
            title=title,
            content=content,
            key_points=[key_point, "详细内容待补充"],
            slide_type=SlideType.CONTENT,
            layout=SlideLayout.STANDARD,
            speaker_notes=f"第{slide_id}页演讲备注：{key_point}"
        )

    def _render_html_node(self, state: OverallState) -> OverallState:
        """渲染HTML节点（增强错误恢复版本）"""
        logger.info("步骤5: 渲染HTML演示文稿")

        # 如果有错误，跳过处理
        if state.errors:
            logger.warning("跳过HTML渲染：存在错误")
            return state

        # 检查是否有幻灯片内容
        if not state.slides:
            error_msg = "无法渲染HTML：缺少幻灯片内容"
            logger.error(error_msg)
            state.errors.append(error_msg)
            return state

        error_context = {
            "operation": "html_rendering",
            "node": "render_html",
            "slides_count": len(state.slides),
            "theme": state.selected_theme.value if state.selected_theme else "default",
            "original_function": lambda: self.html_renderer.render_presentation(state)
        }

        try:
            # 调用HTML渲染器
            state = self.html_renderer.render_presentation(state)

            if state.html_output:
                logger.info("HTML渲染成功")
                # 验证HTML内容的基本完整性
                if len(state.html_output) < 1000:  # HTML内容过短可能有问题
                    state.warnings.append("HTML内容较短，请检查渲染结果")
            else:
                warning_msg = "HTML渲染完成但内容为空"
                logger.warning(warning_msg)
                state.warnings.append(warning_msg)

            return state

        except Exception as e:
            logger.warning(f"HTML渲染失败，尝试错误恢复: {e}")
            
            try:
                recovery_result = self.recovery_manager.handle_error(e, error_context, state)
                
                if isinstance(recovery_result, str) and recovery_result:
                    # 使用恢复的HTML内容
                    state.html_output = recovery_result
                    logger.info("HTML渲染通过错误恢复成功")
                    state.warnings.append("HTML渲染使用了降级模式")
                else:
                    # 使用最基础的HTML渲染
                    logger.warning("使用紧急HTML渲染")
                    state.html_output = self._generate_emergency_html(state)
                    state.warnings.append("HTML渲染使用了紧急降级模式")
                    
                return state
                
            except Exception as recovery_error:
                logger.error(f"HTML渲染错误恢复也失败: {recovery_error}")
                # 作为最后手段，生成最基础的HTML
                state.html_output = self._generate_basic_html(state)
                state.errors.append(f"HTML渲染失败，已使用基础降级: {str(e)}")
                return state

    def _generate_emergency_html(self, state: OverallState) -> str:
        """生成紧急HTML输出"""
        logger.info("生成紧急HTML输出")
        
        html_parts = [
            "<!DOCTYPE html>",
            "<html lang='zh-CN'>",
            "<head>",
            "    <meta charset='UTF-8'>",
            "    <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            f"    <title>{state.outline.title if state.outline else '演示文稿'}</title>",
            "    <style>",
            "        body { font-family: 'Microsoft YaHei', Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }",
            "        .presentation { max-width: 1000px; margin: 0 auto; }",
            "        .slide { background: white; margin: 30px 0; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); page-break-after: always; }",
            "        h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; margin-bottom: 20px; }",
            "        h2 { color: #34495e; margin-top: 30px; }",
            "        ul { line-height: 1.8; }",
            "        li { margin: 8px 0; }",
            "        .slide-number { position: absolute; top: 10px; right: 20px; color: #7f8c8d; font-size: 14px; }",
            "        .speaker-notes { margin-top: 30px; padding: 15px; background: #ecf0f1; border-left: 4px solid #95a5a6; font-style: italic; }",
            "        @media print { .slide { page-break-after: always; margin: 0; box-shadow: none; } }",
            "    </style>",
            "</head>",
            "<body>",
            "    <div class='presentation'>"
        ]
        
        # 添加幻灯片内容
        for slide in state.slides:
            html_parts.extend([
                "        <div class='slide'>",
                f"            <div class='slide-number'>第 {slide.slide_id} 页</div>",
                f"            <h1>{slide.title}</h1>",
                f"            <div class='content'>{self._convert_markdown_to_html(slide.content)}</div>"
            ])
            
            # 添加要点列表
            if slide.key_points:
                html_parts.append("            <h2>要点总结</h2>")
                html_parts.append("            <ul>")
                for point in slide.key_points:
                    html_parts.append(f"                <li>{point}</li>")
                html_parts.append("            </ul>")
            
            # 添加演讲备注
            if hasattr(slide, 'speaker_notes') and slide.speaker_notes:
                html_parts.extend([
                    "            <div class='speaker-notes'>",
                    f"                <strong>演讲备注：</strong>{slide.speaker_notes}",
                    "            </div>"
                ])
                
            html_parts.append("        </div>")
        
        html_parts.extend([
            "    </div>",
            "</body>",
            "</html>"
        ])
        
        return "\n".join(html_parts)

    def _generate_basic_html(self, state: OverallState) -> str:
        """生成最基础的HTML输出"""
        logger.warning("生成基础HTML输出")
        
        title = state.outline.title if state.outline else "演示文稿"
        
        html_content = [
            f"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>{title}</title></head><body>",
            f"<h1>{title}</h1>"
        ]
        
        if state.slides:
            for slide in state.slides:
                html_content.extend([
                    f"<div style='margin: 20px 0; padding: 20px; border: 1px solid #ccc;'>",
                    f"<h2>第{slide.slide_id}页: {slide.title}</h2>",
                    f"<p>{slide.content.replace(chr(10), '<br>')}</p>",
                    "</div>"
                ])
        else:
            html_content.append("<p>暂无内容</p>")
            
        html_content.append("</body></html>")
        
        return "".join(html_content)

    def _convert_markdown_to_html(self, content: str) -> str:
        """简单的Markdown到HTML转换"""
        import re
        
        # 基础的Markdown转换
        content = re.sub(r'^### (.*$)', r'<h3>\1</h3>', content, flags=re.MULTILINE)
        content = re.sub(r'^## (.*$)', r'<h2>\1</h2>', content, flags=re.MULTILINE)
        content = re.sub(r'^# (.*$)', r'<h1>\1</h1>', content, flags=re.MULTILINE)
        content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
        content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', content)
        content = re.sub(r'^• (.*$)', r'<li>\1</li>', content, flags=re.MULTILINE)
        content = re.sub(r'^- (.*$)', r'<li>\1</li>', content, flags=re.MULTILINE)
        
        # 处理换行
        content = content.replace('\n\n', '</p><p>')
        content = content.replace('\n', '<br>')
        content = f'<p>{content}</p>'
        
        # 处理连续的li标签，包装在ul中
        content = re.sub(r'(<li>.*?</li>)', r'<ul>\1</ul>', content, flags=re.DOTALL)
        content = re.sub(r'</ul>\s*<ul>', '', content)
        
        return content

    def _print_generation_summary(self, state: OverallState):
        """打印生成摘要（增强版本，包含错误恢复统计）"""
        logger.info("=== PPT生成摘要 ===")

        if state.outline:
            logger.info(f"标题: {state.outline.title}")
            logger.info(f"章节数: {len(state.outline.sections)}")

        logger.info(f"生成幻灯片数: {len(state.slides)}")
        logger.info(f"选择主题: {state.selected_theme.value if state.selected_theme else 'default'}")

        if state.errors:
            logger.info(f"错误数: {len(state.errors)}")
            for i, error in enumerate(state.errors[:3], 1):  # 只显示前3个错误
                logger.info(f"  错误{i}: {error[:100]}...")

        if state.warnings:
            logger.info(f"警告数: {len(state.warnings)}")

        total_time = sum(metadata.generation_time for metadata in state.generation_metadata)
        logger.info(f"总耗时: {total_time:.2f}秒")

        # 错误恢复统计
        if hasattr(self, 'recovery_manager'):
            recovery_stats = self.recovery_manager.get_recovery_statistics()
            if recovery_stats["total_attempts"] > 0:
                logger.info(f"错误恢复尝试: {recovery_stats['total_attempts']} 次")
                logger.info(f"恢复成功率: {recovery_stats['success_rate']:.1%}")

        if state.output_file_path:
            logger.info(f"输出文件: {state.output_file_path}")

        # 质量评估摘要
        if state.slides:
            quality_scores = [getattr(slide, 'quality_score', 0.8) for slide in state.slides]
            avg_quality = sum(quality_scores) / len(quality_scores)
            logger.info(f"平均质量分数: {avg_quality:.2f}")

        logger.info("=================")

    def run(self, input_text: str = "", input_file_path: str = "") -> OverallState:
        """
        运行PPT生成工作流（增强错误恢复版本）

        Args:
            input_text: 输入文本内容
            input_file_path: 输入文件路径

        Returns:
            最终状态
        """
        logger.info("开始运行PPT生成工作流")
        performance_monitor.start_timer("total_generation")

        try:
            # 创建初始状态
            initial_state = OverallState(
                input_text=input_text,
                input_file_path=input_file_path
            )

            # 运行工作流
            final_state = self.graph.invoke(initial_state)

            duration = performance_monitor.end_timer("total_generation")
            logger.info(f"PPT生成工作流完成，总耗时: {duration:.2f}s")

            # 生成最终报告
            self._generate_final_report(final_state, duration)

            return final_state

        except Exception as e:
            logger.error(f"工作流运行失败: {e}")
            performance_monitor.end_timer("total_generation")

            # 尝试错误恢复
            try:
                error_context = {
                    "operation": "workflow_execution", 
                    "node": "main_workflow",
                    "input_text_length": len(input_text),
                    "input_file": input_file_path
                }
                
                recovery_result = self.recovery_manager.handle_error(e, error_context, None)
                if recovery_result:
                    logger.info("工作流级别错误恢复成功")
                    # 返回部分结果
                    partial_state = OverallState(
                        input_text=input_text,
                        input_file_path=input_file_path
                    )
                    partial_state.warnings.append("工作流执行部分失败，已应用错误恢复")
                    return partial_state
                    
            except Exception as recovery_error:
                logger.error(f"工作流级别错误恢复也失败: {recovery_error}")

            # 返回错误状态
            error_state = OverallState(
                input_text=input_text,
                input_file_path=input_file_path
            )
            error_state.errors.append(f"工作流运行失败: {str(e)}")
            return error_state

    def _generate_final_report(self, state: OverallState, execution_time: float):
        """生成最终执行报告"""
        report = {
            "execution_summary": {
                "total_time": execution_time,
                "slides_generated": len(state.slides),
                "errors_count": len(state.errors),
                "warnings_count": len(state.warnings),
                "success": len(state.errors) == 0
            },
            "quality_metrics": self._calculate_quality_metrics(state),
            "recovery_statistics": self.recovery_manager.get_recovery_statistics() if hasattr(self, 'recovery_manager') else {},
            "performance_metrics": self._get_performance_metrics(state)
        }
        
        # 记录详细报告到日志
        logger.info("=== 详细执行报告 ===")
        logger.info(f"执行状态: {'成功' if report['execution_summary']['success'] else '失败'}")
        logger.info(f"生成幻灯片: {report['execution_summary']['slides_generated']} 张")
        logger.info(f"执行时间: {report['execution_summary']['total_time']:.2f} 秒")
        
        if report['quality_metrics']['average_quality'] > 0:
            logger.info(f"平均质量: {report['quality_metrics']['average_quality']:.2f}")
            
        if report['recovery_statistics'].get('total_attempts', 0) > 0:
            logger.info(f"错误恢复: {report['recovery_statistics']['total_attempts']} 次尝试")
            logger.info(f"恢复成功率: {report['recovery_statistics']['success_rate']:.1%}")
            
        logger.info("==================")

    def _calculate_quality_metrics(self, state: OverallState) -> Dict[str, float]:
        """计算质量指标"""
        if not state.slides:
            return {"average_quality": 0.0, "quality_variance": 0.0}
            
        quality_scores = [getattr(slide, 'quality_score', 0.8) for slide in state.slides]
        average_quality = sum(quality_scores) / len(quality_scores)
        
        # 计算质量方差
        variance = sum((score - average_quality) ** 2 for score in quality_scores) / len(quality_scores)
        
        return {
            "average_quality": average_quality,
            "quality_variance": variance,
            "min_quality": min(quality_scores),
            "max_quality": max(quality_scores)
        }

    def _get_performance_metrics(self, state: OverallState) -> Dict[str, float]:
        """获取性能指标"""
        if not state.generation_metadata:
            return {"average_generation_time": 0.0}
            
        generation_times = [metadata.generation_time for metadata in state.generation_metadata]
        
        return {
            "average_generation_time": sum(generation_times) / len(generation_times),
            "total_generation_time": sum(generation_times),
            "slides_per_minute": len(state.slides) / (sum(generation_times) / 60) if sum(generation_times) > 0 else 0
        }

    def get_workflow_status(self) -> Dict[str, Any]:
        """获取工作流状态信息（增强版本）"""
        base_status = {
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "components": {
                "outline_generator": "已初始化",
                "content_generator": "已初始化", 
                "style_selector": "已初始化",
                "html_renderer": "已初始化",
                "recovery_manager": "已初始化" if hasattr(self, 'recovery_manager') else "未初始化"
            },
            "workflow_nodes": [
                "validate_input",
                "generate_outline", 
                "select_style",
                "generate_content",
                "render_html",
                "save_results"
            ]
        }
        
        # 添加错误恢复统计
        if hasattr(self, 'recovery_manager'):
            base_status["recovery_statistics"] = self.recovery_manager.get_recovery_statistics()
            
        return base_status

    def _save_results_node(self, state: OverallState) -> OverallState:
        """保存结果节点"""
        logger.info("步骤6: 保存生成结果")

        try:
            # 准备保存数据
            save_data = {
                "title": state.outline.title if state.outline else "未命名演示",
                "generation_time": sum(metadata.generation_time for metadata in state.generation_metadata),
                "total_slides": len(state.slides),
                "theme": state.selected_theme.value,
                "errors": state.errors,
                "warnings": state.warnings,
                "slides_summary": [
                    {
                        "id": slide.slide_id,
                        "title": slide.title,
                        "type": slide.slide_type.value,
                        "layout": slide.layout.value
                    }
                    for slide in state.slides
                ]
            }

            # 保存演示数据
            if state.slides:
                presentation_data = {
                    "outline": state.outline.dict() if state.outline else {},
                    "slides": [slide.dict() for slide in state.slides],
                    "style": {
                        "theme": state.selected_theme.value,
                        "custom_styles": state.custom_styles
                    },
                    "metadata": save_data
                }

                json_path = result_saver.save_presentation(presentation_data)
                logger.info(f"演示数据已保存: {json_path}")

            # 保存HTML文件
            if state.html_output:
                html_path = result_saver.save_html_output(state.html_output)
                state.output_file_path = str(html_path)
                logger.info(f"HTML文件已保存: {html_path}")

            # 保存生成日志
            log_path = result_saver.save_generation_log(save_data)
            logger.info(f"生成日志已保存: {log_path}")

            # 输出摘要
            self._print_generation_summary(state)

            return state

        except Exception as e:
            logger.error(f"结果保存失败: {e}")
            state.errors.append(f"结果保存失败: {str(e)}")
            return state

    def _print_generation_summary(self, state: OverallState):
        """打印生成摘要"""
        logger.info("=== PPT生成摘要 ===")

        if state.outline:
            logger.info(f"标题: {state.outline.title}")
            logger.info(f"章节数: {len(state.outline.sections)}")

        logger.info(f"生成幻灯片数: {len(state.slides)}")
        logger.info(f"选择主题: {state.selected_theme.value}")

        if state.errors:
            logger.info(f"错误数: {len(state.errors)}")

        if state.warnings:
            logger.info(f"警告数: {len(state.warnings)}")

        total_time = sum(metadata.generation_time for metadata in state.generation_metadata)
        logger.info(f"总耗时: {total_time:.2f}秒")

        if state.output_file_path:
            logger.info(f"输出文件: {state.output_file_path}")

        logger.info("=================")

    def run(self, input_text: str = "", input_file_path: str = "") -> OverallState:
        """
        运行PPT生成工作流

        Args:
            input_text: 输入文本内容
            input_file_path: 输入文件路径

        Returns:
            最终状态
        """
        logger.info("开始运行PPT生成工作流")
        performance_monitor.start_timer("total_generation")

        try:
            # 创建初始状态
            initial_state = OverallState(
                input_text=input_text,
                input_file_path=input_file_path
            )

            # 运行工作流
            final_state = self.graph.invoke(initial_state)

            duration = performance_monitor.end_timer("total_generation")
            logger.info(f"PPT生成工作流完成，总耗时: {duration:.2f}s")

            return final_state

        except Exception as e:
            logger.error(f"工作流运行失败: {e}")
            performance_monitor.end_timer("total_generation")

            # 返回错误状态
            error_state = OverallState(
                input_text=input_text,
                input_file_path=input_file_path
            )
            error_state.errors.append(f"工作流运行失败: {str(e)}")
            return error_state

    def run_async(self, input_text: str = "", input_file_path: str = ""):
        """
        异步运行PPT生成工作流（未来扩展）

        Args:
            input_text: 输入文本内容
            input_file_path: 输入文件路径
        """
        # TODO: 实现异步版本
        logger.info("异步运行模式尚未实现，使用同步模式")
        return self.run(input_text, input_file_path)

    def get_workflow_status(self) -> Dict[str, Any]:
        """获取工作流状态信息"""
        return {
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "components": {
                "outline_generator": "已初始化",
                "content_generator": "已初始化",
                "style_selector": "已初始化",
                "html_renderer": "已初始化"
            },
            "workflow_nodes": [
                "validate_input",
                "generate_outline",
                "select_style",
                "generate_content",
                "render_html",
                "save_results"
            ]
        }


# 便捷函数
def create_ppt_agent(model_provider: str = "openai", model_name: str = "gpt-3.5-turbo") -> PPTAgentGraph:
    """
    创建PPT智能体实例

    Args:
        model_provider: 模型提供商
        model_name: 模型名称

    Returns:
        PPT智能体实例
    """
    return PPTAgentGraph(model_provider, model_name)


def generate_ppt_from_text(text: str, model_provider: str = "openai") -> OverallState:
    """
    从文本生成PPT的便捷函数

    Args:
        text: 输入文本
        model_provider: 模型提供商

    Returns:
        生成结果状态
    """
    agent = create_ppt_agent(model_provider)
    return agent.run(input_text=text)


def generate_ppt_from_file(file_path: str, model_provider: str = "openai") -> OverallState:
    """
    从文件生成PPT的便捷函数

    Args:
        file_path: 输入文件路径
        model_provider: 模型提供商

    Returns:
        生成结果状态
    """
    agent = create_ppt_agent(model_provider)
    return agent.run(input_file_path=file_path)