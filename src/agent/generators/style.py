"""
样式选择器模块

负责根据PPT内容和目标受众，智能选择合适的视觉样式主题。
实现动态样式配置，为HTML渲染提供样式参数。
"""

import json
import re
from typing import Dict, Any, Optional, List
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage, SystemMessage

from ..state import OverallState, StyleTheme
from ..prompts import PromptBuilder, SYSTEM_MESSAGES
from ..utils import logger, performance_monitor


class StyleSelector:
    """样式选择器类"""

    def __init__(self, model_provider: str = "openai", model_name: str = "gpt-3.5-turbo"):
        """
        初始化样式选择器

        Args:
            model_provider: 模型提供商 ("openai" 或 "google")
            model_name: 模型名称
        """
        self.model_provider = model_provider
        self.model_name = model_name
        self.llm = self._initialize_model()

        # 预定义的样式配置
        self.style_configs = self._load_style_configurations()

    def _initialize_model(self):
        """初始化AI模型"""
        try:
            if self.model_provider.lower() == "openai":
                return ChatOpenAI(
                    model=self.model_name,
                    temperature=0.3,  # 样式选择需要较低的随机性
                    max_tokens=800
                )
            elif self.model_provider.lower() == "google":
                return ChatGoogleGenerativeAI(
                    model=self.model_name,
                    temperature=0.3,
                    max_output_tokens=800
                )
            else:
                raise ValueError(f"不支持的模型提供商: {self.model_provider}")

        except Exception as e:
            logger.error(f"样式选择模型初始化失败: {e}")
            raise

    def select_style_theme(self, state: OverallState) -> OverallState:
        """
        选择样式主题

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        logger.info("开始选择演示样式主题")
        performance_monitor.start_timer("style_selection")

        try:
            if not state.outline:
                logger.warning("缺少演示大纲，使用默认样式")
                state.selected_theme = StyleTheme.PROFESSIONAL
                return state

            # 分析演示内容特征
            content_analysis = self._analyze_presentation_content(state)

            # 调用AI模型选择样式
            if self._should_use_ai_selection(state):
                ai_selection = self._get_ai_style_recommendation(state, content_analysis)
                if ai_selection:
                    state.selected_theme = StyleTheme(ai_selection["selected_theme"])
                    state.custom_styles.update(ai_selection.get("style_config", {}))
                else:
                    # AI选择失败，使用规则选择
                    state.selected_theme = self._rule_based_style_selection(content_analysis)
            else:
                # 使用规则基础选择
                state.selected_theme = self._rule_based_style_selection(content_analysis)

            # 应用样式配置
            self._apply_style_configuration(state)

            duration = performance_monitor.end_timer("style_selection")
            logger.info(f"样式选择完成: {state.selected_theme.value}，耗时: {duration:.2f}s")

            return state

        except Exception as e:
            logger.error(f"样式选择失败: {e}")
            state.errors.append(f"样式选择失败: {str(e)}")
            state.selected_theme = StyleTheme.PROFESSIONAL  # 使用默认样式
            performance_monitor.end_timer("style_selection")
            return state

    def _analyze_presentation_content(self, state: OverallState) -> Dict[str, Any]:
        """分析演示内容特征"""
        analysis = {
            "topic_type": "general",
            "formality_level": "medium",
            "content_complexity": "medium",
            "visual_elements": "text_heavy",
            "target_domain": "general"
        }

        if not state.outline:
            return analysis

        # 分析标题和内容
        title = state.outline.title.lower()
        objectives = " ".join(state.outline.main_objectives).lower()
        audience = state.outline.target_audience.lower()

        # 主题类型分析
        if any(keyword in title for keyword in ["商业", "业务", "企业", "market", "business"]):
            analysis["topic_type"] = "business"
        elif any(keyword in title for keyword in ["技术", "科技", "开发", "tech", "technology"]):
            analysis["topic_type"] = "technology"
        elif any(keyword in title for keyword in ["学术", "研究", "论文", "academic", "research"]):
            analysis["topic_type"] = "academic"
        elif any(keyword in title for keyword in ["创意", "设计", "艺术", "creative", "design"]):
            analysis["topic_type"] = "creative"

        # 正式程度分析
        if any(keyword in audience for keyword in ["高管", "领导", "投资", "executive", "investor"]):
            analysis["formality_level"] = "high"
        elif any(keyword in audience for keyword in ["同事", "团队", "朋友", "colleague", "team"]):
            analysis["formality_level"] = "medium"
        elif any(keyword in audience for keyword in ["学生", "年轻", "创新", "student", "young"]):
            analysis["formality_level"] = "low"

        # 复杂度分析
        total_slides = state.outline.total_slides
        avg_slides_per_section = total_slides / len(state.outline.sections) if state.outline.sections else 5

        if total_slides > 30 or avg_slides_per_section > 8:
            analysis["content_complexity"] = "high"
        elif total_slides < 10 or avg_slides_per_section < 3:
            analysis["content_complexity"] = "low"

        logger.debug(f"内容分析结果: {analysis}")
        return analysis

    def _should_use_ai_selection(self, state: OverallState) -> bool:
        """判断是否应该使用AI进行样式选择"""
        # 如果有足够的内容信息，使用AI选择
        return (
            state.outline and
            len(state.outline.sections) > 1 and
            state.outline.target_audience and
            len(state.outline.main_objectives) > 0
        )

    def _get_ai_style_recommendation(self, state: OverallState, content_analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """获取AI样式推荐"""
        try:
            logger.debug("调用AI进行样式选择")

            # 构建样式选择提示词
            prompt = PromptBuilder.build_style_selection_prompt(
                title=state.outline.title,
                target_audience=state.outline.target_audience,
                main_objectives=state.outline.main_objectives,
                slide_content=content_analysis
            )

            # 调用AI模型
            response = self._call_model_for_style(prompt)

            # 解析响应
            style_recommendation = self._parse_style_response(response)

            return style_recommendation

        except Exception as e:
            logger.error(f"AI样式选择失败: {e}")
            return None

    def _call_model_for_style(self, prompt: str) -> str:
        """调用AI模型进行样式选择"""
        try:
            messages = [
                SystemMessage(content=SYSTEM_MESSAGES["design_expert"]),
                HumanMessage(content=prompt)
            ]

            response = self.llm.invoke(messages)
            return response.content

        except Exception as e:
            logger.error(f"样式选择AI调用失败: {e}")
            raise

    def _parse_style_response(self, response: str) -> Dict[str, Any]:
        """解析样式选择响应"""
        try:
            # 尝试提取JSON部分
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    raise ValueError("响应中未找到有效的JSON")

            style_data = json.loads(json_str)

            # 验证必要字段
            if "selected_theme" not in style_data:
                raise ValueError("样式响应缺少selected_theme字段")

            # 验证主题是否有效
            theme = style_data["selected_theme"]
            if theme not in [t.value for t in StyleTheme]:
                logger.warning(f"无效的主题: {theme}，使用默认主题")
                style_data["selected_theme"] = StyleTheme.PROFESSIONAL.value

            return style_data

        except json.JSONDecodeError as e:
            logger.error(f"样式选择JSON解析错误: {e}")
            raise

        except Exception as e:
            logger.error(f"样式选择解析失败: {e}")
            raise

    def _rule_based_style_selection(self, content_analysis: Dict[str, Any]) -> StyleTheme:
        """基于规则的样式选择"""
        logger.debug("使用规则基础进行样式选择")

        topic_type = content_analysis.get("topic_type", "general")
        formality_level = content_analysis.get("formality_level", "medium")

        # 规则映射
        if topic_type == "business" and formality_level == "high":
            return StyleTheme.PROFESSIONAL
        elif topic_type == "technology":
            return StyleTheme.MODERN
        elif topic_type == "academic":
            return StyleTheme.ACADEMIC
        elif topic_type == "creative":
            return StyleTheme.CREATIVE
        elif formality_level == "low":
            return StyleTheme.MINIMAL
        else:
            return StyleTheme.PROFESSIONAL  # 默认

    def _apply_style_configuration(self, state: OverallState):
        """应用样式配置"""
        theme = state.selected_theme
        config = self.style_configs.get(theme.value, self.style_configs["professional"])

        # 更新自定义样式
        state.custom_styles.update(config)

        logger.debug(f"应用样式配置: {theme.value}")

    def _load_style_configurations(self) -> Dict[str, Dict[str, Any]]:
        """加载样式配置"""
        return {
            "professional": {
                "primary_color": "#2C3E50",
                "secondary_color": "#3498DB",
                "accent_color": "#E74C3C",
                "background_color": "#FFFFFF",
                "text_color": "#2C3E50",
                "font_family": "Microsoft YaHei, Arial, sans-serif",
                "heading_font": "Microsoft YaHei Bold, Arial Bold, sans-serif",
                "font_size_base": "16px",
                "font_size_heading": "28px",
                "font_size_subheading": "20px",
                "line_height": "1.6",
                "border_radius": "4px",
                "shadow": "0 2px 10px rgba(0,0,0,0.1)",
                "transition": "all 0.3s ease"
            },
            "modern": {
                "primary_color": "#667EEA",
                "secondary_color": "#764BA2",
                "accent_color": "#F093FB",
                "background_color": "#F8FAFC",
                "text_color": "#1A202C",
                "font_family": "Segoe UI, Roboto, sans-serif",
                "heading_font": "Segoe UI Semibold, Roboto Medium, sans-serif",
                "font_size_base": "16px",
                "font_size_heading": "32px",
                "font_size_subheading": "22px",
                "line_height": "1.7",
                "border_radius": "12px",
                "shadow": "0 4px 20px rgba(102,126,234,0.15)",
                "transition": "all 0.4s cubic-bezier(0.4, 0, 0.2, 1)"
            },
            "creative": {
                "primary_color": "#FF6B6B",
                "secondary_color": "#4ECDC4",
                "accent_color": "#FFE66D",
                "background_color": "#FFFFFF",
                "text_color": "#2D3748",
                "font_family": "Montserrat, Helvetica, sans-serif",
                "heading_font": "Montserrat Bold, Helvetica Bold, sans-serif",
                "font_size_base": "16px",
                "font_size_heading": "36px",
                "font_size_subheading": "24px",
                "line_height": "1.8",
                "border_radius": "20px",
                "shadow": "0 8px 30px rgba(255,107,107,0.2)",
                "transition": "all 0.5s ease-in-out"
            },
            "academic": {
                "primary_color": "#2E4057",
                "secondary_color": "#048A81",
                "accent_color": "#F39C12",
                "background_color": "#FEFEFE",
                "text_color": "#2E4057",
                "font_family": "Times New Roman, Georgia, serif",
                "heading_font": "Times New Roman Bold, Georgia Bold, serif",
                "font_size_base": "16px",
                "font_size_heading": "30px",
                "font_size_subheading": "21px",
                "line_height": "1.8",
                "border_radius": "2px",
                "shadow": "0 1px 3px rgba(0,0,0,0.1)",
                "transition": "all 0.2s ease"
            },
            "minimal": {
                "primary_color": "#000000",
                "secondary_color": "#666666",
                "accent_color": "#007AFF",
                "background_color": "#FFFFFF",
                "text_color": "#000000",
                "font_family": "Helvetica Neue, Helvetica, Arial, sans-serif",
                "heading_font": "Helvetica Neue Light, Helvetica Light, Arial, sans-serif",
                "font_size_base": "16px",
                "font_size_heading": "40px",
                "font_size_subheading": "24px",
                "line_height": "1.5",
                "border_radius": "0px",
                "shadow": "none",
                "transition": "opacity 0.3s ease"
            }
        }

    def get_style_css(self, state: OverallState) -> str:
        """
        生成样式CSS

        Args:
            state: 当前状态

        Returns:
            CSS样式字符串
        """
        styles = state.custom_styles

        css_template = """
        :root {
            --primary-color: %(primary_color)s;
            --secondary-color: %(secondary_color)s;
            --accent-color: %(accent_color)s;
            --background-color: %(background_color)s;
            --text-color: %(text_color)s;
            --font-family: %(font_family)s;
            --heading-font: %(heading_font)s;
            --font-size-base: %(font_size_base)s;
            --font-size-heading: %(font_size_heading)s;
            --font-size-subheading: %(font_size_subheading)s;
            --line-height: %(line_height)s;
            --border-radius: %(border_radius)s;
            --shadow: %(shadow)s;
            --transition: %(transition)s;
        }

        body {
            font-family: var(--font-family);
            font-size: var(--font-size-base);
            line-height: var(--line-height);
            color: var(--text-color);
            background-color: var(--background-color);
        }

        .reveal h1, .reveal h2, .reveal h3 {
            font-family: var(--heading-font);
            color: var(--primary-color);
        }

        .reveal h1 {
            font-size: var(--font-size-heading);
        }

        .reveal h2 {
            font-size: var(--font-size-subheading);
        }

        .reveal .slides section {
            background-color: var(--background-color);
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            transition: var(--transition);
        }

        .reveal .slides section.present {
            transform: scale(1.02);
        }

        .reveal .progress {
            color: var(--accent-color);
        }

        .reveal .controls {
            color: var(--secondary-color);
        }

        .highlight {
            background-color: var(--accent-color);
            color: white;
            padding: 0.2em 0.4em;
            border-radius: calc(var(--border-radius) / 2);
        }

        .slide-number {
            color: var(--secondary-color) !important;
        }

        .bullet-point {
            color: var(--text-color);
            margin: 0.5em 0;
        }

        .bullet-point::before {
            content: "●";
            color: var(--accent-color);
            margin-right: 0.5em;
        }
        """

        return css_template % styles

    def customize_style_for_slide_type(self, slide_type: str, base_styles: Dict[str, Any]) -> Dict[str, Any]:
        """为特定幻灯片类型定制样式"""
        customized = base_styles.copy()

        if slide_type == "title":
            customized.update({
                "text_align": "center",
                "background_gradient": f"linear-gradient(135deg, {base_styles['primary_color']}, {base_styles['secondary_color']})",
                "title_color": "#FFFFFF",
                "subtitle_color": "rgba(255,255,255,0.9)"
            })
        elif slide_type == "section":
            customized.update({
                "background_color": base_styles["secondary_color"],
                "text_color": "#FFFFFF",
                "border_left": f"8px solid {base_styles['accent_color']}"
            })
        elif slide_type == "data":
            customized.update({
                "chart_primary": base_styles["primary_color"],
                "chart_secondary": base_styles["secondary_color"],
                "chart_accent": base_styles["accent_color"],
                "grid_color": "rgba(0,0,0,0.1)"
            })

        return customized