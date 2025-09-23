"""
PPT智能体状态管理模块

定义LangGraph工作流中的状态结构，使用Pydantic进行数据验证。
采用简化的状态管理策略，避免过度复杂的并发控制。
"""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum


class SlideType(str, Enum):
    """幻灯片类型枚举"""
    TITLE = "title"           # 标题页
    CONTENT = "content"       # 内容页
    SECTION = "section"       # 章节分割页
    SUMMARY = "summary"       # 总结页
    COMPARISON = "comparison" # 对比页
    DATA = "data"            # 数据展示页


class SlideLayout(str, Enum):
    """幻灯片布局枚举"""
    SINGLE_COLUMN = "single_column"       # 单列布局
    TWO_COLUMN = "two_column"            # 双列布局
    THREE_COLUMN = "three_column"        # 三列布局
    TITLE_CONTENT = "title_content"      # 标题+内容
    IMAGE_TEXT = "image_text"            # 图文混排
    FULL_IMAGE = "full_image"            # 全图
    LIST_LAYOUT = "list_layout"          # 列表布局


class StyleTheme(str, Enum):
    """样式主题枚举"""
    PROFESSIONAL = "professional"  # 专业商务
    MODERN = "modern"              # 现代简约
    CREATIVE = "creative"          # 创意设计
    ACADEMIC = "academic"          # 学术风格
    MINIMAL = "minimal"            # 极简风格


class SlideContent(BaseModel):
    """单页幻灯片内容模型"""
    slide_id: int = Field(..., description="幻灯片ID")
    title: str = Field(..., description="幻灯片标题")
    slide_type: SlideType = Field(default=SlideType.CONTENT, description="幻灯片类型")
    main_content: str = Field(default="", description="主要内容")
    bullet_points: List[str] = Field(default_factory=list, description="要点列表")
    speaker_notes: str = Field(default="", description="演讲者备注")
    design_suggestions: str = Field(default="", description="设计建议")
    
    # 质量反思相关字段
    quality_score: Optional[float] = Field(None, description="质量评分(0-100)")
    reflection_count: int = Field(default=0, description="反思优化次数")
    optimization_feedback: List[str] = Field(default_factory=list, description="优化反馈记录")
    
    # 兼容性字段
    layout: SlideLayout = Field(default=SlideLayout.TITLE_CONTENT, description="布局类型")
    content: List[str] = Field(default_factory=list, description="内容段落列表(兼容)")
    images: List[str] = Field(default_factory=list, description="图片描述列表")
    notes: str = Field(default="", description="演讲者备注(兼容)")
    keywords: List[str] = Field(default_factory=list, description="关键词")
    estimated_duration: int = Field(default=60, description="预计展示时长(秒)")


class OutlineSection(BaseModel):
    """大纲章节模型"""
    section_id: int = Field(..., description="章节ID")
    title: str = Field(..., description="章节标题")
    subtitle: str = Field(default="", description="章节副标题")
    key_points: List[str] = Field(default_factory=list, description="关键要点")
    estimated_slides: int = Field(..., description="预计幻灯片数量")
    content_summary: str = Field(..., description="内容摘要")


class PresentationOutline(BaseModel):
    """演示大纲模型"""
    title: str = Field(..., description="演示标题")
    subtitle: str = Field(default="", description="演示副标题")
    total_slides: int = Field(..., description="总幻灯片数")
    estimated_duration: int = Field(..., description="预计总时长(分钟)")
    sections: List[OutlineSection] = Field(default_factory=list, description="章节列表")
    target_audience: str = Field(default="", description="目标受众")
    main_objectives: List[str] = Field(default_factory=list, description="主要目标")


class SlidingSummary(BaseModel):
    """滑动窗口摘要模型 - 用于维护上下文连贯性"""
    slide_id: int = Field(..., description="幻灯片ID")
    main_message: str = Field(..., description="主要信息")
    key_concepts: List[str] = Field(default_factory=list, description="关键概念")
    logical_connection: str = Field(default="", description="与前后内容的逻辑连接")


class QualityMetrics(BaseModel):
    """质量评估指标"""
    content_relevance: float = Field(ge=0.0, le=1.0, description="内容相关性")
    logical_coherence: float = Field(ge=0.0, le=1.0, description="逻辑连贯性")
    visual_appeal: float = Field(ge=0.0, le=1.0, description="视觉吸引力")
    information_density: float = Field(ge=0.0, le=1.0, description="信息密度")
    overall_score: float = Field(ge=0.0, le=1.0, description="综合评分")


class GenerationMetadata(BaseModel):
    """生成元数据"""
    model_used: str = Field(..., description="使用的AI模型")
    generation_time: float = Field(..., description="生成时间(秒)")
    token_usage: int = Field(default=0, description="Token使用量")
    retry_count: int = Field(default=0, description="重试次数")
    quality_metrics: Optional[QualityMetrics] = Field(None, description="质量评估")


class OverallState(BaseModel):
    """全局状态模型 - LangGraph的主要状态（支持质量反思机制）"""

    # 输入数据
    input_text: str = Field(default="", description="原始输入文本")
    input_file_path: str = Field(default="", description="输入文件路径")

    # 大纲相关
    outline: Optional[PresentationOutline] = Field(None, description="演示大纲")
    outline_generated: bool = Field(default=False, description="大纲是否已生成")

    # 内容生成相关
    slides: List[SlideContent] = Field(default_factory=list, description="已生成的幻灯片")
    current_slide_index: int = Field(default=0, description="当前处理的幻灯片索引")
    sliding_summaries: List[SlidingSummary] = Field(default_factory=list, description="滑动窗口摘要")
    generation_completed: bool = Field(default=False, description="生成是否完成")

    # 质量反思相关
    enable_quality_reflection: bool = Field(default=True, description="是否启用质量反思")
    total_reflection_attempts: int = Field(default=0, description="总反思尝试次数")
    successful_reflections: int = Field(default=0, description="成功反思次数")
    quality_improvement_log: List[str] = Field(default_factory=list, description="质量改进日志")

    # 样式相关
    selected_theme: StyleTheme = Field(default=StyleTheme.PROFESSIONAL, description="选择的主题")
    custom_styles: Dict[str, Any] = Field(default_factory=dict, description="自定义样式")

    # 输出相关
    html_output: str = Field(default="", description="生成的HTML输出")
    output_file_path: str = Field(default="", description="输出文件路径")

    # 错误处理
    errors: List[str] = Field(default_factory=list, description="错误信息列表")
    warnings: List[str] = Field(default_factory=list, description="警告信息列表")

    # 生成配置
    max_slides_per_section: int = Field(default=8, description="每章节最大幻灯片数")
    sliding_window_size: int = Field(default=3, description="滑动窗口大小")
    quality_threshold: float = Field(default=0.8, description="质量阈值")

    # 元数据
    generation_metadata: List[GenerationMetadata] = Field(default_factory=list, description="生成元数据")

    class Config:
        """Pydantic配置"""
        # 允许任意类型的字段（为了兼容性）
        arbitrary_types_allowed = True
        # 使用枚举值而非枚举名称
        use_enum_values = True
        # 验证赋值
        validate_assignment = True


# 状态操作辅助函数
def add_slide_to_state(state: OverallState, slide: SlideContent) -> OverallState:
    """向状态中添加新的幻灯片"""
    state.slides.append(slide)
    return state


def add_sliding_summary(state: OverallState, summary: SlidingSummary) -> OverallState:
    """添加滑动窗口摘要"""
    state.sliding_summaries.append(summary)
    # 保持滑动窗口大小限制
    if len(state.sliding_summaries) > state.sliding_window_size:
        state.sliding_summaries = state.sliding_summaries[-state.sliding_window_size:]
    return state


def get_recent_context(state: OverallState, context_size: int = 3) -> str:
    """获取最近的上下文信息"""
    recent_summaries = state.sliding_summaries[-context_size:]
    if not recent_summaries:
        return ""

    context_parts = []
    for summary in recent_summaries:
        context_parts.append(f"第{summary.slide_id}页: {summary.main_message}")

    return "\n".join(context_parts)


def add_error(state: OverallState, error_message: str) -> OverallState:
    """添加错误信息"""
    state.errors.append(error_message)
    return state


def add_warning(state: OverallState, warning_message: str) -> OverallState:
    """添加警告信息"""
    state.warnings.append(warning_message)
    return state