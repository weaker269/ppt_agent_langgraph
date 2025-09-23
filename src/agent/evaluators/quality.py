"""
幻灯片质量评估器

实现多维度的幻灯片质量评分，包括内容逻辑性、主题相关性、语言质量和视觉布局。
支持生成详细的缺陷分析和优化建议。
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage

from ..state import SlideContent, PresentationOutline
from ..utils import ConfigManager

logger = logging.getLogger(__name__)


class QualityDimension(Enum):
    """质量评估维度"""
    LOGIC = "logic"  # 内容逻辑性
    RELEVANCE = "relevance"  # 主题相关性
    LANGUAGE = "language"  # 语言表达质量
    LAYOUT = "layout"  # 视觉布局合理性


@dataclass
class QualityScore:
    """质量评分结果"""
    total_score: float  # 总分 (0-100)
    dimension_scores: Dict[str, float]  # 各维度得分
    pass_threshold: bool  # 是否达到及格线
    confidence: float  # 评分置信度


@dataclass
class OptimizationSuggestion:
    """优化建议"""
    dimension: str  # 需要优化的维度
    issue_description: str  # 问题描述
    suggestion: str  # 具体建议
    priority: str  # 优先级 (high/medium/low)


class QualityEvaluator:
    """幻灯片质量评估器"""
    
    def __init__(self, model_provider: str = "openai"):
        """
        初始化质量评估器
        
        Args:
            model_provider: AI模型提供商 ("openai" 或 "google")
        """
        self.config = ConfigManager()
        self.model_provider = model_provider
        self.llm = self._initialize_model()
        
        # 配置参数
        self.quality_threshold = float(self.config.get("QUALITY_THRESHOLD", "85"))
        self.max_retry_count = int(self.config.get("MAX_REFLECTION_RETRY", "3"))
        self.reflection_dimensions = self.config.get(
            "REFLECTION_DIMENSIONS", 
            "logic,relevance,language,layout"
        ).split(",")
        
        # 维度权重配置
        self.dimension_weights = {
            "logic": 0.3,      # 逻辑性权重30%
            "relevance": 0.25, # 相关性权重25%
            "language": 0.25,  # 语言质量权重25%
            "layout": 0.2      # 布局权重20%
        }
        
        logger.info(f"质量评估器初始化完成，阈值: {self.quality_threshold}, 最大重试: {self.max_retry_count}")

    def _initialize_model(self):
        """初始化AI模型"""
        try:
            if self.model_provider == "openai":
                return ChatOpenAI(
                    model=self.config.get("OPENAI_MODEL", "gpt-3.5-turbo"),
                    temperature=0.3,  # 较低的温度以获得更一致的评分
                    timeout=int(self.config.get("MODEL_TIMEOUT", "60"))
                )
            elif self.model_provider == "google":
                return ChatGoogleGenerativeAI(
                    model=self.config.get("GOOGLE_MODEL", "gemini-pro"),
                    temperature=0.3,
                    timeout=int(self.config.get("MODEL_TIMEOUT", "60"))
                )
            else:
                raise ValueError(f"不支持的模型提供商: {self.model_provider}")
        except Exception as e:
            logger.error(f"模型初始化失败: {e}")
            raise

    def evaluate_slide(
        self, 
        slide: SlideContent, 
        outline: PresentationOutline,
        context_slides: Optional[List[SlideContent]] = None
    ) -> Tuple[QualityScore, List[OptimizationSuggestion]]:
        """
        评估单张幻灯片的质量
        
        Args:
            slide: 要评估的幻灯片
            outline: 演示大纲
            context_slides: 上下文幻灯片列表（用于一致性检查）
            
        Returns:
            Tuple[QualityScore, List[OptimizationSuggestion]]: 质量评分和优化建议
        """
        try:
            logger.info(f"开始评估幻灯片: {slide.title}")
            
            # 构建评估提示词
            evaluation_prompt = self._build_evaluation_prompt(slide, outline, context_slides)
            
            # 调用AI模型进行评估
            response = self.llm.invoke([HumanMessage(content=evaluation_prompt)])
            response_text = response.content
            
            # 解析评估结果
            quality_score, suggestions = self._parse_evaluation_response(response_text)
            
            logger.info(f"评估完成，总分: {quality_score.total_score:.1f}")
            return quality_score, suggestions
            
        except Exception as e:
            logger.error(f"幻灯片质量评估失败: {e}")
            # 返回默认的低分评估
            return self._create_fallback_evaluation(slide)

    def _build_evaluation_prompt(
        self, 
        slide: SlideContent, 
        outline: PresentationOutline,
        context_slides: Optional[List[SlideContent]] = None
    ) -> str:
        """构建质量评估提示词"""
        
        context_info = ""
        if context_slides:
            context_info = "\n\n**上下文幻灯片信息:**\n"
            for i, ctx_slide in enumerate(context_slides[-3:]):  # 最多3张上下文幻灯片
                context_info += f"第{i+1}张: {ctx_slide.title} - {ctx_slide.main_content[:100]}...\n"

        prompt = f"""
作为PPT质量评估专家，请对以下幻灯片进行多维度质量评分：

**演示主题:** {outline.title}
**目标受众:** {outline.target_audience if hasattr(outline, 'target_audience') else '通用受众'}

**待评估幻灯片:**
- 标题: {slide.title}
- 类型: {slide.slide_type.value}
- 主要内容: {slide.main_content}
- 要点: {', '.join(slide.bullet_points) if slide.bullet_points else '无'}
- 注释: {slide.speaker_notes if slide.speaker_notes else '无'}
{context_info}

**评估维度和标准:**

1. **内容逻辑性 (30%)**
   - 内容结构是否清晰合理
   - 论点论据是否充分
   - 逻辑推理是否严密

2. **主题相关性 (25%)**
   - 内容是否与演示主题紧密相关
   - 是否偏离主线或过于发散
   - 与上下文的连贯性

3. **语言表达质量 (25%)**
   - 文字表达是否清晰准确
   - 是否简洁有力，避免冗余
   - 专业术语使用是否恰当

4. **视觉布局合理性 (20%)**
   - 信息层次是否分明
   - 要点数量是否适中（建议3-7个）
   - 内容密度是否合适

**输出格式:**
请严格按照以下JSON格式输出评估结果：

```json
{{
    "dimension_scores": {{
        "logic": 分数(0-100),
        "relevance": 分数(0-100), 
        "language": 分数(0-100),
        "layout": 分数(0-100)
    }},
    "confidence": 置信度(0-1),
    "optimization_suggestions": [
        {{
            "dimension": "维度名称",
            "issue_description": "问题描述",
            "suggestion": "具体改进建议",
            "priority": "优先级(high/medium/low)"
        }}
    ]
}}
```

请给出客观、准确的评分和建议。
"""
        return prompt

    def _parse_evaluation_response(self, response_text: str) -> Tuple[QualityScore, List[OptimizationSuggestion]]:
        """解析AI评估响应"""
        try:
            import json
            import re
            
            # 提取JSON部分
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if not json_match:
                # 尝试直接解析整个响应
                json_str = response_text.strip()
            else:
                json_str = json_match.group(1)
            
            eval_data = json.loads(json_str)
            
            # 计算总分
            dimension_scores = eval_data["dimension_scores"]
            total_score = sum(
                score * self.dimension_weights.get(dim, 0.25) 
                for dim, score in dimension_scores.items()
            )
            
            # 创建质量评分对象
            quality_score = QualityScore(
                total_score=round(total_score, 1),
                dimension_scores=dimension_scores,
                pass_threshold=total_score >= self.quality_threshold,
                confidence=eval_data.get("confidence", 0.8)
            )
            
            # 创建优化建议列表
            suggestions = [
                OptimizationSuggestion(
                    dimension=sugg["dimension"],
                    issue_description=sugg["issue_description"],
                    suggestion=sugg["suggestion"],
                    priority=sugg["priority"]
                )
                for sugg in eval_data.get("optimization_suggestions", [])
            ]
            
            return quality_score, suggestions
            
        except Exception as e:
            logger.error(f"解析评估响应失败: {e}")
            logger.debug(f"原始响应: {response_text}")
            raise

    def _create_fallback_evaluation(self, slide: SlideContent) -> Tuple[QualityScore, List[OptimizationSuggestion]]:
        """创建降级评估结果"""
        logger.warning("使用降级评估结果")
        
        quality_score = QualityScore(
            total_score=60.0,  # 低于阈值的分数
            dimension_scores={
                "logic": 60.0,
                "relevance": 60.0,
                "language": 60.0,
                "layout": 60.0
            },
            pass_threshold=False,
            confidence=0.3
        )
        
        suggestions = [
            OptimizationSuggestion(
                dimension="system",
                issue_description="质量评估系统暂时不可用",
                suggestion="请手动检查幻灯片内容的逻辑性、相关性、语言质量和布局合理性",
                priority="medium"
            )
        ]
        
        return quality_score, suggestions

    def should_regenerate(self, quality_score: QualityScore, retry_count: int) -> bool:
        """
        判断是否需要重新生成幻灯片
        
        Args:
            quality_score: 质量评分
            retry_count: 当前重试次数
            
        Returns:
            bool: 是否需要重新生成
        """
        # 如果已达到及格线，不需要重新生成
        if quality_score.pass_threshold:
            return False
            
        # 如果超过最大重试次数，不再重新生成
        if retry_count >= self.max_retry_count:
            logger.warning(f"已达到最大重试次数 {self.max_retry_count}，接受当前结果")
            return False
            
        # 评分过低且还有重试机会，需要重新生成
        logger.info(f"质量评分 {quality_score.total_score:.1f} 低于阈值 {self.quality_threshold}，将进行第 {retry_count + 1} 次重试")
        return True

    def format_feedback_for_regeneration(
        self, 
        quality_score: QualityScore, 
        suggestions: List[OptimizationSuggestion]
    ) -> str:
        """
        格式化反馈信息用于重新生成
        
        Args:
            quality_score: 质量评分
            suggestions: 优化建议
            
        Returns:
            str: 格式化的反馈信息
        """
        feedback = f"**质量评估反馈 (当前得分: {quality_score.total_score:.1f}/{self.quality_threshold})**\n\n"
        
        # 添加各维度得分
        feedback += "**各维度得分:**\n"
        for dim, score in quality_score.dimension_scores.items():
            status = "✅" if score >= self.quality_threshold else "❌"
            feedback += f"- {dim}: {score:.1f}分 {status}\n"
        
        # 添加优化建议
        if suggestions:
            feedback += "\n**优化建议:**\n"
            high_priority = [s for s in suggestions if s.priority == "high"]
            medium_priority = [s for s in suggestions if s.priority == "medium"]
            
            if high_priority:
                feedback += "\n🔴 **高优先级问题:**\n"
                for sugg in high_priority:
                    feedback += f"- {sugg.issue_description}\n  建议: {sugg.suggestion}\n\n"
            
            if medium_priority:
                feedback += "🟡 **中等优先级问题:**\n"
                for sugg in medium_priority:
                    feedback += f"- {sugg.issue_description}\n  建议: {sugg.suggestion}\n\n"
        
        feedback += "\n请根据以上反馈优化幻灯片内容，重点关注得分较低的维度。"
        
        return feedback