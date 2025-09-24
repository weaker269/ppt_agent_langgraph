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
        """深度分析演示内容特征，支持智能样式选择"""
        analysis = {
            "topic_type": "general",
            "formality_level": "medium", 
            "content_complexity": "medium",
            "visual_elements": "text_heavy",
            "target_domain": "general",
            "emotional_tone": "neutral",
            "data_intensity": "low",
            "interactivity_need": "low",
            "brand_personality": "professional"
        }

        if not state.outline:
            return analysis

        # 分析标题和内容
        title = state.outline.title.lower()
        objectives = " ".join(state.outline.main_objectives).lower() if state.outline.main_objectives else ""
        audience = state.outline.target_audience.lower() if state.outline.target_audience else ""
        
        # 收集所有文本内容进行深度分析
        all_text = f"{title} {objectives} {audience}"
        if state.outline.sections:
            for section in state.outline.sections:
                all_text += f" {section.title.lower()} {section.content_summary.lower()}"
                all_text += " ".join(section.key_points).lower()

        # 增强的主题类型分析
        business_keywords = ["商业", "业务", "企业", "市场", "销售", "营收", "战略", "运营", "客户", "market", "business", "sales", "revenue", "strategy", "customer"]
        tech_keywords = ["技术", "科技", "开发", "编程", "AI", "算法", "数据", "系统", "架构", "tech", "technology", "development", "programming", "algorithm", "data", "system"]
        academic_keywords = ["学术", "研究", "论文", "实验", "理论", "分析", "方法", "结果", "学习", "academic", "research", "study", "experiment", "theory", "analysis", "learning"]
        creative_keywords = ["创意", "设计", "艺术", "创新", "想象", "灵感", "美学", "视觉", "creative", "design", "art", "innovation", "inspiration", "aesthetic", "visual"]
        financial_keywords = ["财务", "金融", "投资", "预算", "成本", "利润", "资金", "finance", "investment", "budget", "cost", "profit", "funding"]

        # 计算关键词匹配度
        topic_scores = {
            "business": sum(1 for kw in business_keywords if kw in all_text),
            "technology": sum(1 for kw in tech_keywords if kw in all_text),
            "academic": sum(1 for kw in academic_keywords if kw in all_text),
            "creative": sum(1 for kw in creative_keywords if kw in all_text),
            "financial": sum(1 for kw in financial_keywords if kw in all_text)
        }
        
        # 选择得分最高的主题类型
        max_score = max(topic_scores.values())
        if max_score > 0:
            analysis["topic_type"] = max(topic_scores, key=topic_scores.get)

        # 正式程度分析（增强版）
        formal_keywords = ["高管", "领导", "投资", "董事", "总监", "执行", "战略", "executive", "director", "investor", "strategic", "formal"]
        casual_keywords = ["同事", "团队", "朋友", "分享", "讨论", "交流", "colleague", "team", "friend", "share", "casual", "informal"]
        
        formal_score = sum(1 for kw in formal_keywords if kw in all_text)
        casual_score = sum(1 for kw in casual_keywords if kw in all_text)
        
        if formal_score > casual_score and formal_score > 2:
            analysis["formality_level"] = "high"
        elif casual_score > formal_score and casual_score > 2:
            analysis["formality_level"] = "low"

        # 情感基调分析
        positive_keywords = ["成功", "增长", "机会", "创新", "优秀", "卓越", "成就", "success", "growth", "opportunity", "innovation", "excellent", "achievement"]
        serious_keywords = ["挑战", "问题", "风险", "困难", "严峻", "关键", "challenge", "problem", "risk", "critical", "serious", "urgent"]
        inspiring_keywords = ["愿景", "梦想", "未来", "可能", "突破", "变革", "vision", "dream", "future", "possibility", "breakthrough", "transformation"]
        
        positive_score = sum(1 for kw in positive_keywords if kw in all_text)
        serious_score = sum(1 for kw in serious_keywords if kw in all_text)
        inspiring_score = sum(1 for kw in inspiring_keywords if kw in all_text)
        
        if inspiring_score >= max(positive_score, serious_score):
            analysis["emotional_tone"] = "inspiring"
        elif positive_score > serious_score:
            analysis["emotional_tone"] = "positive"
        elif serious_score > positive_score:
            analysis["emotional_tone"] = "serious"

        # 数据密集度分析
        data_keywords = ["数据", "统计", "图表", "分析", "报告", "指标", "百分比", "data", "statistics", "chart", "analysis", "report", "metrics", "percentage"]
        data_score = sum(1 for kw in data_keywords if kw in all_text)
        
        if data_score > 5:
            analysis["data_intensity"] = "high"
            analysis["visual_elements"] = "data_heavy"
        elif data_score > 2:
            analysis["data_intensity"] = "medium"
            analysis["visual_elements"] = "mixed"

        # 交互性需求分析
        interactive_keywords = ["讨论", "问答", "互动", "参与", "演示", "体验", "discussion", "Q&A", "interactive", "participate", "demo", "experience"]
        interactive_score = sum(1 for kw in interactive_keywords if kw in all_text)
        
        if interactive_score > 3:
            analysis["interactivity_need"] = "high"
        elif interactive_score > 1:
            analysis["interactivity_need"] = "medium"

        # 品牌个性分析
        professional_keywords = ["专业", "可靠", "稳定", "权威", "professional", "reliable", "stable", "authoritative"]
        modern_keywords = ["现代", "前沿", "创新", "潮流", "modern", "cutting-edge", "innovative", "trendy"]
        friendly_keywords = ["友好", "亲切", "温暖", "人性化", "friendly", "warm", "approachable", "human"]
        
        professional_score = sum(1 for kw in professional_keywords if kw in all_text)
        modern_score = sum(1 for kw in modern_keywords if kw in all_text)
        friendly_score = sum(1 for kw in friendly_keywords if kw in all_text)
        
        if modern_score >= max(professional_score, friendly_score):
            analysis["brand_personality"] = "modern"
        elif friendly_score >= max(professional_score, modern_score):
            analysis["brand_personality"] = "friendly"

        # 复杂度分析（增强版）
        total_slides = state.outline.total_slides
        avg_slides_per_section = total_slides / len(state.outline.sections) if state.outline.sections else 5
        
        # 综合多个因素判断复杂度
        complexity_factors = [
            total_slides > 30,  # 幻灯片数量
            avg_slides_per_section > 8,  # 每章节平均页数
            len(state.outline.sections) > 8,  # 章节数量
            data_score > 5,  # 数据密集度
            max(topic_scores.values()) > 10  # 专业术语密度
        ]
        
        complexity_score = sum(complexity_factors)
        if complexity_score >= 3:
            analysis["content_complexity"] = "high"
        elif complexity_score <= 1:
            analysis["content_complexity"] = "low"

        logger.info(f"深度内容分析完成: {analysis}")
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
        """获取AI智能样式推荐（增强版）"""
        try:
            logger.debug("调用AI进行智能样式分析和推荐")

            # 构建增强的样式选择提示词
            prompt = self._build_enhanced_style_prompt(state, content_analysis)

            # 调用AI模型
            response = self._call_model_for_style(prompt)

            # 解析响应
            style_recommendation = self._parse_style_response(response)
            
            if style_recommendation:
                logger.info(f"AI推荐样式: {style_recommendation.get('selected_theme', 'unknown')}")
                logger.debug(f"推荐理由: {style_recommendation.get('reasoning', 'no reasoning provided')}")

            return style_recommendation

        except Exception as e:
            logger.error(f"AI样式选择失败: {e}")
            return None

    def _build_enhanced_style_prompt(self, state: OverallState, content_analysis: Dict[str, Any]) -> str:
        """构建增强的AI样式选择提示词"""
        
        # 收集演示内容摘要
        sections_summary = ""
        if state.outline and state.outline.sections:
            sections_summary = "\n".join([
                f"- {section.title}: {section.content_summary[:100]}..."
                for section in state.outline.sections[:5]  # 最多显示5个章节
            ])

        prompt = f"""
你是专业的演示设计专家，请根据以下演示内容分析结果，为PPT选择最合适的视觉风格主题。

**演示基本信息:**
- 标题: {state.outline.title if state.outline else '未知'}
- 目标受众: {state.outline.target_audience if state.outline else '通用受众'}
- 总页数: {state.outline.total_slides if state.outline else '未知'}
- 主要目标: {', '.join(state.outline.main_objectives) if state.outline and state.outline.main_objectives else '信息传达'}

**主要章节:**
{sections_summary}

**深度内容分析结果:**
- 主题类型: {content_analysis['topic_type']} ({self._get_topic_description(content_analysis['topic_type'])})
- 正式程度: {content_analysis['formality_level']} ({self._get_formality_description(content_analysis['formality_level'])})
- 内容复杂度: {content_analysis['content_complexity']}
- 情感基调: {content_analysis['emotional_tone']}
- 数据密集度: {content_analysis['data_intensity']}
- 交互性需求: {content_analysis['interactivity_need']}
- 品牌个性: {content_analysis['brand_personality']}
- 视觉元素特点: {content_analysis['visual_elements']}

**可选样式主题:**
1. **professional** - 专业商务风格
   - 适合: 企业汇报、商业计划、正式场合
   - 特点: 简洁大方、权威可信、蓝白配色为主

2. **modern** - 现代简约风格  
   - 适合: 科技产品、创新项目、年轻受众
   - 特点: 几何设计、清新配色、现代感强

3. **creative** - 创意设计风格
   - 适合: 设计展示、创意提案、艺术相关
   - 特点: 活泼色彩、独特布局、视觉冲击

4. **academic** - 学术研究风格
   - 适合: 学术论文、研究报告、教育培训
   - 特点: 严谨布局、清晰层次、经典配色

5. **minimal** - 极简主义风格
   - 适合: 理念传达、品牌展示、高端产品
   - 特点: 大量留白、聚焦重点、优雅简洁

**选择标准:**
1. 与内容主题和受众匹配
2. 支持内容的表达需求（数据展示、情感传达等）
3. 符合使用场景的正式程度
4. 增强演示的整体效果

请综合考虑以上信息，选择最适合的样式主题，并提供详细的选择理由。

**输出格式要求:**
请严格按照以下JSON格式输出：

```json
{{
    "selected_theme": "选择的主题名称",
    "confidence": 评估置信度(0.0-1.0),
    "reasoning": "详细的选择理由说明",
    "style_config": {{
        "primary_color": "主色调建议",
        "secondary_color": "辅助色建议", 
        "font_style": "字体风格建议",
        "layout_emphasis": "布局重点建议"
    }},
    "alternative_themes": ["备选主题1", "备选主题2"],
    "design_recommendations": [
        "具体的设计建议1",
        "具体的设计建议2"
    ]
}}
```

请确保选择的主题能够最好地支持内容表达和受众接受度。
"""
        return prompt

    def _get_topic_description(self, topic_type: str) -> str:
        """获取主题类型描述"""
        descriptions = {
            "business": "商业/企业主题",
            "technology": "科技/技术主题", 
            "academic": "学术/研究主题",
            "creative": "创意/设计主题",
            "financial": "金融/财务主题",
            "general": "通用主题"
        }
        return descriptions.get(topic_type, "未知主题")

    def _get_formality_description(self, formality_level: str) -> str:
        """获取正式程度描述"""
        descriptions = {
            "high": "高度正式，适合高管汇报",
            "medium": "中等正式，适合团队分享", 
            "low": "相对轻松，适合内部讨论"
        }
        return descriptions.get(formality_level, "中等正式")

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
        """基于规则的智能样式选择（增强版）"""
        logger.debug("使用增强规则引擎进行样式选择")

        # 提取分析结果
        topic_type = content_analysis.get("topic_type", "general")
        formality_level = content_analysis.get("formality_level", "medium")
        emotional_tone = content_analysis.get("emotional_tone", "neutral")
        data_intensity = content_analysis.get("data_intensity", "low")
        brand_personality = content_analysis.get("brand_personality", "professional")
        content_complexity = content_analysis.get("content_complexity", "medium")

        # 多因素评分系统
        theme_scores = {
            StyleTheme.PROFESSIONAL: 0,
            StyleTheme.MODERN: 0,
            StyleTheme.CREATIVE: 0,
            StyleTheme.ACADEMIC: 0,
            StyleTheme.MINIMAL: 0
        }

        # 主题类型评分 (权重: 40%)
        topic_weights = {
            "business": {StyleTheme.PROFESSIONAL: 3, StyleTheme.MODERN: 1},
            "technology": {StyleTheme.MODERN: 3, StyleTheme.PROFESSIONAL: 2, StyleTheme.MINIMAL: 1},
            "academic": {StyleTheme.ACADEMIC: 3, StyleTheme.PROFESSIONAL: 2},
            "creative": {StyleTheme.CREATIVE: 3, StyleTheme.MODERN: 2, StyleTheme.MINIMAL: 1},
            "financial": {StyleTheme.PROFESSIONAL: 3, StyleTheme.MINIMAL: 1}
        }
        
        if topic_type in topic_weights:
            for theme, weight in topic_weights[topic_type].items():
                theme_scores[theme] += weight * 0.4

        # 正式程度评分 (权重: 25%)
        formality_weights = {
            "high": {StyleTheme.PROFESSIONAL: 3, StyleTheme.ACADEMIC: 2, StyleTheme.MINIMAL: 1},
            "medium": {StyleTheme.PROFESSIONAL: 2, StyleTheme.MODERN: 2, StyleTheme.ACADEMIC: 1},
            "low": {StyleTheme.MODERN: 2, StyleTheme.CREATIVE: 2, StyleTheme.MINIMAL: 3}
        }
        
        if formality_level in formality_weights:
            for theme, weight in formality_weights[formality_level].items():
                theme_scores[theme] += weight * 0.25

        # 情感基调评分 (权重: 15%)
        emotion_weights = {
            "inspiring": {StyleTheme.MODERN: 2, StyleTheme.CREATIVE: 3, StyleTheme.MINIMAL: 1},
            "positive": {StyleTheme.MODERN: 2, StyleTheme.CREATIVE: 2, StyleTheme.PROFESSIONAL: 1},
            "serious": {StyleTheme.PROFESSIONAL: 3, StyleTheme.ACADEMIC: 2, StyleTheme.MINIMAL: 1},
            "neutral": {StyleTheme.PROFESSIONAL: 1, StyleTheme.MODERN: 1, StyleTheme.ACADEMIC: 1}
        }
        
        if emotional_tone in emotion_weights:
            for theme, weight in emotion_weights[emotional_tone].items():
                theme_scores[theme] += weight * 0.15

        # 数据密集度评分 (权重: 10%)
        data_weights = {
            "high": {StyleTheme.PROFESSIONAL: 2, StyleTheme.ACADEMIC: 3, StyleTheme.MINIMAL: 2},
            "medium": {StyleTheme.PROFESSIONAL: 2, StyleTheme.MODERN: 1, StyleTheme.ACADEMIC: 1},
            "low": {StyleTheme.CREATIVE: 2, StyleTheme.MINIMAL: 2, StyleTheme.MODERN: 1}
        }
        
        if data_intensity in data_weights:
            for theme, weight in data_weights[data_intensity].items():
                theme_scores[theme] += weight * 0.1

        # 品牌个性评分 (权重: 10%)
        brand_weights = {
            "professional": {StyleTheme.PROFESSIONAL: 3, StyleTheme.ACADEMIC: 1},
            "modern": {StyleTheme.MODERN: 3, StyleTheme.MINIMAL: 2},
            "friendly": {StyleTheme.CREATIVE: 2, StyleTheme.MODERN: 2, StyleTheme.MINIMAL: 1}
        }
        
        if brand_personality in brand_weights:
            for theme, weight in brand_weights[brand_personality].items():
                theme_scores[theme] += weight * 0.1

        # 特殊规则调整
        
        # 如果内容复杂度高，偏向简洁风格
        if content_complexity == "high":
            theme_scores[StyleTheme.MINIMAL] += 0.5
            theme_scores[StyleTheme.PROFESSIONAL] += 0.3
        
        # 如果是创意主题但正式程度高，平衡选择
        if topic_type == "creative" and formality_level == "high":
            theme_scores[StyleTheme.MODERN] += 0.5
            theme_scores[StyleTheme.CREATIVE] -= 0.3

        # 如果是学术内容但受众年轻，调整风格
        if topic_type == "academic" and formality_level == "low":
            theme_scores[StyleTheme.MODERN] += 0.4
            theme_scores[StyleTheme.ACADEMIC] -= 0.2

        # 选择得分最高的主题
        selected_theme = max(theme_scores, key=theme_scores.get)
        max_score = theme_scores[selected_theme]
        
        # 记录决策过程
        logger.info(f"规则引擎评分结果: {dict(theme_scores)}")
        logger.info(f"选择主题: {selected_theme.value} (得分: {max_score:.2f})")
        
        # 如果最高得分太低，使用安全的默认选择
        if max_score < 1.0:
            logger.warning("所有主题得分较低，使用默认专业主题")
            return StyleTheme.PROFESSIONAL
            
        return selected_theme  # 默认

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