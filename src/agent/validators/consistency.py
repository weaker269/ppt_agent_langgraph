"""
跨页面一致性检查器

实现深度的逻辑连贯性和风格统一性验证，确保整个演示的质量和连贯性。
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage

from ..state import SlideContent, PresentationOutline, OverallState
from ..utils import ConfigManager

logger = logging.getLogger(__name__)


class ConsistencyIssueType(Enum):
    """一致性问题类型"""
    LOGICAL_BREAK = "logical_break"           # 逻辑断裂
    STYLE_INCONSISTENCY = "style_inconsistency"  # 风格不一致
    TERMINOLOGY_MISMATCH = "terminology_mismatch"  # 术语不一致
    TONE_SHIFT = "tone_shift"                 # 语调变化
    STRUCTURE_VIOLATION = "structure_violation"  # 结构违规
    REDUNDANT_CONTENT = "redundant_content"   # 内容重复
    MISSING_TRANSITION = "missing_transition"  # 缺少过渡
    DEPTH_INCONSISTENCY = "depth_inconsistency"  # 深度不一致


class SeverityLevel(Enum):
    """严重程度级别"""
    LOW = "low"        # 轻微问题，建议修复
    MEDIUM = "medium"  # 中等问题，应该修复
    HIGH = "high"      # 严重问题，必须修复
    CRITICAL = "critical"  # 关键问题，影响演示质量


@dataclass
class ConsistencyIssue:
    """一致性问题"""
    issue_type: ConsistencyIssueType
    severity: SeverityLevel
    slide_ids: List[int]  # 涉及的幻灯片ID
    description: str      # 问题描述
    suggestion: str       # 修复建议
    confidence: float     # 检测置信度 (0.0-1.0)


@dataclass
class ConsistencyReport:
    """一致性检查报告"""
    overall_score: float  # 整体一致性得分 (0.0-100.0)
    issues: List[ConsistencyIssue]  # 发现的问题列表
    strengths: List[str]  # 一致性优点
    recommendations: List[str]  # 总体建议
    checked_slides: int   # 检查的幻灯片数量
    check_timestamp: str  # 检查时间戳


class ConsistencyChecker:
    """跨页面一致性检查器"""
    
    def __init__(self, model_provider: str = "openai"):
        """
        初始化一致性检查器
        
        Args:
            model_provider: AI模型提供商 ("openai" 或 "google")
        """
        self.config = ConfigManager()
        self.model_provider = model_provider
        self.llm = self._initialize_model()
        
        # 配置参数
        self.consistency_threshold = float(self.config.get("CONSISTENCY_THRESHOLD", "75"))
        self.enable_ai_check = self.config.get("ENABLE_AI_CONSISTENCY_CHECK", "true").lower() == "true"
        
        logger.info(f"一致性检查器初始化完成，阈值: {self.consistency_threshold}")

    def _initialize_model(self):
        """初始化AI模型"""
        try:
            if self.model_provider == "openai":
                return ChatOpenAI(
                    model=self.config.get("OPENAI_MODEL", "gpt-3.5-turbo"),
                    temperature=0.2,  # 较低温度以获得一致的分析
                    timeout=int(self.config.get("MODEL_TIMEOUT", "60"))
                )
            elif self.model_provider == "google":
                return ChatGoogleGenerativeAI(
                    model=self.config.get("GOOGLE_MODEL", "gemini-pro"),
                    temperature=0.2,
                    timeout=int(self.config.get("MODEL_TIMEOUT", "60"))
                )
            else:
                raise ValueError(f"不支持的模型提供商: {self.model_provider}")
        except Exception as e:
            logger.error(f"模型初始化失败: {e}")
            raise

    def check_presentation_consistency(self, state: OverallState) -> ConsistencyReport:
        """
        检查整个演示的一致性
        
        Args:
            state: 演示状态
            
        Returns:
            ConsistencyReport: 一致性检查报告
        """
        logger.info("开始跨页面一致性检查")
        
        try:
            issues = []
            strengths = []
            
            if not state.slides or len(state.slides) < 2:
                logger.warning("幻灯片数量不足，跳过一致性检查")
                return self._create_minimal_report(len(state.slides) if state.slides else 0)
            
            # 执行各种一致性检查
            logical_issues = self._check_logical_consistency(state.slides, state.outline)
            issues.extend(logical_issues)
            
            style_issues = self._check_style_consistency(state.slides)
            issues.extend(style_issues)
            
            terminology_issues = self._check_terminology_consistency(state.slides)
            issues.extend(terminology_issues)
            
            structure_issues = self._check_structure_consistency(state.slides, state.outline)
            issues.extend(structure_issues)
            
            content_issues = self._check_content_consistency(state.slides)
            issues.extend(content_issues)
            
            # 如果启用了AI检查，进行深度一致性分析
            if self.enable_ai_check and len(state.slides) >= 3:
                ai_issues = self._ai_consistency_analysis(state.slides, state.outline)
                issues.extend(ai_issues)
            
            # 识别优点
            strengths = self._identify_consistency_strengths(state.slides, issues)
            
            # 计算整体得分
            overall_score = self._calculate_consistency_score(issues, len(state.slides))
            
            # 生成总体建议
            recommendations = self._generate_recommendations(issues, overall_score)
            
            # 创建报告
            report = ConsistencyReport(
                overall_score=overall_score,
                issues=issues,
                strengths=strengths,
                recommendations=recommendations,
                checked_slides=len(state.slides),
                check_timestamp=self._get_timestamp()
            )
            
            logger.info(f"一致性检查完成，总分: {overall_score:.1f}, 发现 {len(issues)} 个问题")
            return report
            
        except Exception as e:
            logger.error(f"一致性检查失败: {e}")
            return self._create_error_report(e)

    def _check_logical_consistency(self, slides: List[SlideContent], outline: Optional[PresentationOutline]) -> List[ConsistencyIssue]:
        """检查逻辑一致性"""
        issues = []
        
        # 检查逻辑流向
        for i in range(len(slides) - 1):
            current_slide = slides[i]
            next_slide = slides[i + 1]
            
            # 检查是否缺少逻辑过渡
            if self._has_logical_gap(current_slide, next_slide):
                issues.append(ConsistencyIssue(
                    issue_type=ConsistencyIssueType.MISSING_TRANSITION,
                    severity=SeverityLevel.MEDIUM,
                    slide_ids=[current_slide.slide_id, next_slide.slide_id],
                    description=f"第{current_slide.slide_id}页到第{next_slide.slide_id}页之间缺少逻辑过渡",
                    suggestion="添加过渡性内容或调整幻灯片顺序以改善逻辑流畅性",
                    confidence=0.7
                ))
        
        # 检查与大纲的一致性
        if outline:
            outline_issues = self._check_outline_alignment(slides, outline)
            issues.extend(outline_issues)
        
        return issues

    def _check_style_consistency(self, slides: List[SlideContent]) -> List[ConsistencyIssue]:
        """检查风格一致性"""
        issues = []
        
        # 分析语言风格
        formal_count = 0
        casual_count = 0
        
        for slide in slides:
            text = f"{slide.title} {slide.main_content} {' '.join(slide.bullet_points)}"
            if self._is_formal_language(text):
                formal_count += 1
            else:
                casual_count += 1
        
        # 如果风格混杂严重
        total_slides = len(slides)
        if min(formal_count, casual_count) / total_slides > 0.3:  # 超过30%不一致
            issues.append(ConsistencyIssue(
                issue_type=ConsistencyIssueType.STYLE_INCONSISTENCY,
                severity=SeverityLevel.MEDIUM,
                slide_ids=[slide.slide_id for slide in slides],
                description="演示中语言风格不统一，正式与非正式语言混用",
                suggestion="统一使用正式或非正式语言风格，确保整体tone一致",
                confidence=0.8
            ))
        
        # 检查标题格式一致性
        title_formats = []
        for slide in slides:
            title_format = self._analyze_title_format(slide.title)
            title_formats.append(title_format)
        
        unique_formats = set(title_formats)
        if len(unique_formats) > 2:  # 超过2种格式认为不一致
            issues.append(ConsistencyIssue(
                issue_type=ConsistencyIssueType.STYLE_INCONSISTENCY,
                severity=SeverityLevel.LOW,
                slide_ids=[slide.slide_id for slide in slides],
                description="标题格式不统一，存在多种不同的格式风格",
                suggestion="统一标题格式，如都使用短语式或句子式标题",
                confidence=0.6
            ))
        
        return issues

    def _check_terminology_consistency(self, slides: List[SlideContent]) -> List[ConsistencyIssue]:
        """检查术语一致性"""
        issues = []
        
        # 提取所有术语
        all_terms = []
        for slide in slides:
            text = f"{slide.title} {slide.main_content} {' '.join(slide.bullet_points)}"
            terms = self._extract_technical_terms(text)
            all_terms.extend(terms)
        
        # 检查术语变体
        term_variants = self._find_term_variants(all_terms)
        
        for base_term, variants in term_variants.items():
            if len(variants) > 1:
                issues.append(ConsistencyIssue(
                    issue_type=ConsistencyIssueType.TERMINOLOGY_MISMATCH,
                    severity=SeverityLevel.MEDIUM,
                    slide_ids=[slide.slide_id for slide in slides],  # 简化处理
                    description=f"术语 '{base_term}' 存在多种表达方式: {', '.join(variants)}",
                    suggestion=f"统一使用一种术语表达，建议使用: {variants[0]}",
                    confidence=0.7
                ))
        
        return issues

    def _check_structure_consistency(self, slides: List[SlideContent], outline: Optional[PresentationOutline]) -> List[ConsistencyIssue]:
        """检查结构一致性"""
        issues = []
        
        # 检查幻灯片长度一致性
        slide_lengths = []
        for slide in slides:
            content_length = len(slide.main_content) + sum(len(bp) for bp in slide.bullet_points)
            slide_lengths.append(content_length)
        
        if slide_lengths:
            avg_length = sum(slide_lengths) / len(slide_lengths)
            outliers = []
            
            for i, length in enumerate(slide_lengths):
                if length > avg_length * 2 or length < avg_length * 0.3:  # 异常长短
                    outliers.append(slides[i].slide_id)
            
            if outliers:
                issues.append(ConsistencyIssue(
                    issue_type=ConsistencyIssueType.DEPTH_INCONSISTENCY,
                    severity=SeverityLevel.LOW,
                    slide_ids=outliers,
                    description="部分幻灯片内容密度与整体不一致",
                    suggestion="调整异常幻灯片的内容量，保持适当的信息密度",
                    confidence=0.6
                ))
        
        return issues

    def _check_content_consistency(self, slides: List[SlideContent]) -> List[ConsistencyIssue]:
        """检查内容一致性"""
        issues = []
        
        # 检查重复内容
        content_hashes = {}
        for slide in slides:
            content_key = f"{slide.title}_{slide.main_content[:100]}"
            content_hash = hash(content_key.lower().replace(" ", ""))
            
            if content_hash in content_hashes:
                issues.append(ConsistencyIssue(
                    issue_type=ConsistencyIssueType.REDUNDANT_CONTENT,
                    severity=SeverityLevel.MEDIUM,
                    slide_ids=[content_hashes[content_hash], slide.slide_id],
                    description=f"第{content_hashes[content_hash]}页和第{slide.slide_id}页存在重复内容",
                    suggestion="合并重复内容或增加差异化信息",
                    confidence=0.8
                ))
            else:
                content_hashes[content_hash] = slide.slide_id
        
        return issues

    def _ai_consistency_analysis(self, slides: List[SlideContent], outline: Optional[PresentationOutline]) -> List[ConsistencyIssue]:
        """AI深度一致性分析"""
        try:
            logger.debug("执行AI深度一致性分析")
            
            # 构建分析提示词
            prompt = self._build_consistency_analysis_prompt(slides, outline)
            
            # 调用AI模型
            response = self.llm.invoke([HumanMessage(content=prompt)])
            
            # 解析响应
            ai_issues = self._parse_consistency_response(response.content)
            
            return ai_issues
            
        except Exception as e:
            logger.error(f"AI一致性分析失败: {e}")
            return []

    def _build_consistency_analysis_prompt(self, slides: List[SlideContent], outline: Optional[PresentationOutline]) -> str:
        """构建一致性分析提示词"""
        
        # 收集幻灯片内容
        slides_content = []
        for slide in slides[:10]:  # 最多分析前10页以控制token使用
            slides_content.append(f"第{slide.slide_id}页 - {slide.title}: {slide.main_content[:200]}...")
        
        slides_text = "\n".join(slides_content)
        
        prompt = f"""
作为演示一致性专家，请分析以下PPT的跨页面一致性问题。

**演示主题:** {outline.title if outline else '未知'}

**幻灯片内容:**
{slides_text}

**分析维度:**
1. **逻辑连贯性**: 内容是否前后呼应，逻辑链条是否完整
2. **风格统一性**: 语言风格、表达方式是否一致
3. **深度平衡**: 各部分内容深度是否适当平衡
4. **术语一致性**: 专业术语使用是否统一
5. **结构规律**: 幻灯片结构是否有规律可循

请识别可能的一致性问题，并给出修复建议。

**输出格式要求:**
```json
{{
    "issues": [
        {{
            "type": "问题类型(logical_break/style_inconsistency/terminology_mismatch/tone_shift/depth_inconsistency)",
            "severity": "严重程度(low/medium/high/critical)",
            "slide_ids": [涉及的幻灯片ID列表],
            "description": "问题描述",
            "suggestion": "修复建议",
            "confidence": 置信度(0.0-1.0)
        }}
    ],
    "overall_assessment": "整体一致性评估",
    "strengths": ["一致性优点1", "一致性优点2"]
}}
```

请重点关注影响演示整体质量的一致性问题。
"""
        return prompt

    def _parse_consistency_response(self, response: str) -> List[ConsistencyIssue]:
        """解析AI一致性分析响应"""
        try:
            import json
            import re
            
            # 提取JSON部分
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response.strip()
            
            data = json.loads(json_str)
            
            issues = []
            for issue_data in data.get("issues", []):
                try:
                    issue = ConsistencyIssue(
                        issue_type=ConsistencyIssueType(issue_data["type"]),
                        severity=SeverityLevel(issue_data["severity"]),
                        slide_ids=issue_data["slide_ids"],
                        description=issue_data["description"],
                        suggestion=issue_data["suggestion"],
                        confidence=issue_data.get("confidence", 0.5)
                    )
                    issues.append(issue)
                except (KeyError, ValueError) as e:
                    logger.warning(f"解析单个问题失败: {e}")
                    continue
            
            return issues
            
        except Exception as e:
            logger.error(f"解析一致性响应失败: {e}")
            return []

    def _calculate_consistency_score(self, issues: List[ConsistencyIssue], total_slides: int) -> float:
        """计算一致性得分"""
        if not issues:
            return 95.0  # 没有问题，给高分但不满分
        
        # 根据问题严重程度计算扣分
        penalty = 0
        for issue in issues:
            if issue.severity == SeverityLevel.CRITICAL:
                penalty += 25
            elif issue.severity == SeverityLevel.HIGH:
                penalty += 15
            elif issue.severity == SeverityLevel.MEDIUM:
                penalty += 8
            elif issue.severity == SeverityLevel.LOW:
                penalty += 3
        
        # 考虑问题密度（问题数量/幻灯片数量）
        problem_density = len(issues) / max(total_slides, 1)
        density_penalty = problem_density * 10
        
        total_penalty = penalty + density_penalty
        score = max(0, 100 - total_penalty)
        
        return round(score, 1)

    def _identify_consistency_strengths(self, slides: List[SlideContent], issues: List[ConsistencyIssue]) -> List[str]:
        """识别一致性优点"""
        strengths = []
        
        # 检查是否有逻辑问题
        logical_issues = [i for i in issues if i.issue_type in [ConsistencyIssueType.LOGICAL_BREAK, ConsistencyIssueType.MISSING_TRANSITION]]
        if not logical_issues:
            strengths.append("逻辑流程清晰，各部分内容衔接自然")
        
        # 检查是否有风格问题
        style_issues = [i for i in issues if i.issue_type == ConsistencyIssueType.STYLE_INCONSISTENCY]
        if not style_issues:
            strengths.append("语言风格统一，表达方式一致")
        
        # 检查是否有术语问题
        term_issues = [i for i in issues if i.issue_type == ConsistencyIssueType.TERMINOLOGY_MISMATCH]
        if not term_issues:
            strengths.append("专业术语使用规范且一致")
        
        # 检查内容深度
        depth_issues = [i for i in issues if i.issue_type == ConsistencyIssueType.DEPTH_INCONSISTENCY]
        if not depth_issues:
            strengths.append("内容深度适中且均衡")
        
        if not strengths:
            strengths.append("演示结构清晰，基本要素完备")
        
        return strengths

    def _generate_recommendations(self, issues: List[ConsistencyIssue], overall_score: float) -> List[str]:
        """生成总体建议"""
        recommendations = []
        
        if overall_score >= 85:
            recommendations.append("整体一致性良好，只需微调部分细节")
        elif overall_score >= 70:
            recommendations.append("一致性较好，建议重点解决中高优先级问题")
        elif overall_score >= 50:
            recommendations.append("存在较多一致性问题，建议系统性检查和修订")
        else:
            recommendations.append("一致性问题较严重，建议重新审视整体结构和内容")
        
        # 基于问题类型给出具体建议
        issue_types = [issue.issue_type for issue in issues]
        
        if ConsistencyIssueType.LOGICAL_BREAK in issue_types:
            recommendations.append("重点检查逻辑流程，确保前后内容呼应")
        
        if ConsistencyIssueType.STYLE_INCONSISTENCY in issue_types:
            recommendations.append("统一语言风格和表达方式")
        
        if ConsistencyIssueType.TERMINOLOGY_MISMATCH in issue_types:
            recommendations.append("建立术语词汇表，确保专业词汇使用一致")
        
        if ConsistencyIssueType.REDUNDANT_CONTENT in issue_types:
            recommendations.append("消除重复内容，增加内容的差异化和价值")
        
        return recommendations

    # 辅助方法
    def _has_logical_gap(self, slide1: SlideContent, slide2: SlideContent) -> bool:
        """检查两个幻灯片之间是否存在逻辑缺口"""
        # 简化的逻辑缺口检测
        # 可以基于关键词相似度、主题连续性等来判断
        return False  # 占位实现

    def _is_formal_language(self, text: str) -> bool:
        """判断是否为正式语言"""
        formal_indicators = ["因此", "综上", "基于", "根据", "显示", "表明", "证明", "建议", "therefore", "based on", "indicate", "demonstrate"]
        casual_indicators = ["好的", "不错", "挺好", "还行", "大家", "咱们", "ok", "great", "nice", "folks"]
        
        formal_count = sum(1 for indicator in formal_indicators if indicator in text.lower())
        casual_count = sum(1 for indicator in casual_indicators if indicator in text.lower())
        
        return formal_count >= casual_count

    def _analyze_title_format(self, title: str) -> str:
        """分析标题格式"""
        if not title:
            return "empty"
        elif title.endswith(("？", "?", "！", "!")):
            return "question_exclamation"
        elif title.endswith(("。", ".")):
            return "sentence"
        elif len(title.split()) <= 3:
            return "short_phrase"
        else:
            return "long_phrase"

    def _extract_technical_terms(self, text: str) -> List[str]:
        """提取技术术语"""
        # 简化的术语提取，可以使用更复杂的NLP方法
        import re
        terms = re.findall(r'\b[A-Z]{2,}\b|\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b', text)
        return [term for term in terms if len(term) > 2]

    def _find_term_variants(self, terms: List[str]) -> Dict[str, List[str]]:
        """查找术语变体"""
        # 简化实现，查找可能的同义词或变体
        variants = {}
        unique_terms = list(set(terms))
        
        for term in unique_terms:
            base_term = term.lower()
            similar_terms = [t for t in unique_terms if t.lower().startswith(base_term[:3]) and t != term]
            if similar_terms:
                variants[term] = [term] + similar_terms
        
        return variants

    def _check_outline_alignment(self, slides: List[SlideContent], outline: PresentationOutline) -> List[ConsistencyIssue]:
        """检查与大纲的对齐"""
        # 简化实现
        return []

    def _create_minimal_report(self, slide_count: int) -> ConsistencyReport:
        """创建最小化报告"""
        return ConsistencyReport(
            overall_score=100.0 if slide_count == 0 else 90.0,
            issues=[],
            strengths=["演示内容简洁"] if slide_count <= 1 else [],
            recommendations=["增加更多内容以进行全面的一致性检查"] if slide_count <= 1 else [],
            checked_slides=slide_count,
            check_timestamp=self._get_timestamp()
        )

    def _create_error_report(self, error: Exception) -> ConsistencyReport:
        """创建错误报告"""
        return ConsistencyReport(
            overall_score=0.0,
            issues=[],
            strengths=[],
            recommendations=[f"一致性检查失败: {str(error)}"],
            checked_slides=0,
            check_timestamp=self._get_timestamp()
        )

    def _get_timestamp(self) -> str:
        """获取时间戳"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")