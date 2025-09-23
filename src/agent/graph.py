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
        """验证输入节点"""
        logger.info("步骤1: 验证输入数据")
        performance_monitor.start_timer("input_validation")

        try:
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
                        return state
                else:
                    error_msg = "缺少输入文本或文件路径"
                    logger.error(error_msg)
                    state.errors.append(error_msg)
                    return state

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

        except Exception as e:
            logger.error(f"输入验证失败: {e}")
            state.errors.append(f"输入验证失败: {str(e)}")
            performance_monitor.end_timer("input_validation")
            return state

    def _generate_outline_node(self, state: OverallState) -> OverallState:
        """生成大纲节点"""
        logger.info("步骤2: 生成演示大纲")

        try:
            # 如果有错误，跳过处理
            if state.errors:
                logger.warning("跳过大纲生成：存在输入错误")
                return state

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
            logger.error(f"大纲生成节点失败: {e}")
            state.errors.append(f"大纲生成失败: {str(e)}")
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
        """生成内容节点（核心节点）"""
        logger.info("步骤4: 生成幻灯片内容（滑动窗口策略）")

        try:
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

            # 调用滑动窗口内容生成器
            state = self.content_generator.generate_all_slides(state)

            # 生成统计信息
            successful_slides = len(state.slides)
            expected_slides = state.outline.total_slides

            logger.info(f"内容生成完成: {successful_slides}/{expected_slides} 页")

            if successful_slides < expected_slides * 0.8:  # 如果成功率低于80%
                warning_msg = f"生成成功率较低: {successful_slides}/{expected_slides}"
                logger.warning(warning_msg)
                state.warnings.append(warning_msg)

            return state

        except Exception as e:
            logger.error(f"内容生成节点失败: {e}")
            state.errors.append(f"内容生成失败: {str(e)}")
            return state

    def _render_html_node(self, state: OverallState) -> OverallState:
        """渲染HTML节点"""
        logger.info("步骤5: 渲染HTML演示文稿")

        try:
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

            # 调用HTML渲染器
            state = self.html_renderer.render_presentation(state)

            if state.html_output:
                logger.info("HTML渲染成功")
            else:
                warning_msg = "HTML渲染完成但内容为空"
                logger.warning(warning_msg)
                state.warnings.append(warning_msg)

            return state

        except Exception as e:
            logger.error(f"HTML渲染节点失败: {e}")
            state.errors.append(f"HTML渲染失败: {str(e)}")
            return state

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