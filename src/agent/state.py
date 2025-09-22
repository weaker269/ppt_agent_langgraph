#!/usr/bin/env python3
"""
PPT Agent 数据状态模型

定义系统中使用的核心数据结构，使用Pydantic进行数据验证
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class SlideType(str, Enum):
    """幻灯片类型枚举"""
    TITLE = "title"
    CONTENT = "content"
    SECTION = "section"


class ContentType(str, Enum):
    """内容类型枚举"""
    TEXT = "text"
    LIST = "list"
    QUOTE = "quote"
    CODE = "code"


class SlideContent(BaseModel):
    """单个幻灯片内容"""
    slide_id: int = Field(..., description="幻灯片ID")
    title: str = Field(..., description="幻灯片标题")
    slide_type: SlideType = Field(default=SlideType.CONTENT, description="幻灯片类型")
    content: str = Field(default="", description="幻灯片内容")
    content_type: ContentType = Field(default=ContentType.TEXT, description="内容类型")

    class Config:
        """Pydantic配置"""
        use_enum_values = True


class SectionInfo(BaseModel):
    """章节信息"""
    section_id: int = Field(..., description="章节ID")
    title: str = Field(..., description="章节标题")
    slides: List[SlideContent] = Field(default_factory=list, description="章节下的幻灯片")
    estimated_slides: int = Field(default=1, description="预估幻灯片数量")


class GlobalContext(BaseModel):
    """全局上下文信息"""
    main_title: str = Field(..., description="主标题")
    theme: str = Field(default="professional", description="主题风格")
    total_slides: int = Field(default=0, description="总幻灯片数")
    generation_time: datetime = Field(default_factory=datetime.now, description="生成时间")


class OverallState(BaseModel):
    """系统整体状态"""
    source_content: str = Field(..., description="源内容")
    global_context: GlobalContext = Field(..., description="全局上下文")
    sections: List[SectionInfo] = Field(default_factory=list, description="所有章节")
    generated_slides: List[SlideContent] = Field(default_factory=list, description="已生成的幻灯片")
    current_phase: str = Field(default="init", description="当前阶段")

    def get_total_slides(self) -> int:
        """获取总幻灯片数"""
        return len(self.generated_slides)

    def add_slide(self, slide: SlideContent) -> None:
        """添加幻灯片"""
        self.generated_slides.append(slide)
        self.global_context.total_slides = self.get_total_slides()


class QualityMetrics(BaseModel):
    """质量评估指标"""
    completeness_score: float = Field(default=0.0, ge=0.0, le=1.0, description="完整性评分")
    consistency_score: float = Field(default=0.0, ge=0.0, le=1.0, description="一致性评分")
    clarity_score: float = Field(default=0.0, ge=0.0, le=1.0, description="清晰度评分")
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0, description="总体评分")

    def calculate_overall_score(self) -> float:
        """计算总体评分"""
        self.overall_score = (self.completeness_score + self.consistency_score + self.clarity_score) / 3
        return self.overall_score


class GenerationResult(BaseModel):
    """生成结果"""
    success: bool = Field(..., description="是否成功")
    output_file: str = Field(..., description="输出文件路径")
    slides_count: int = Field(..., description="生成的幻灯片数量")
    quality_metrics: QualityMetrics = Field(default_factory=QualityMetrics, description="质量指标")
    generation_time: float = Field(..., description="生成耗时(秒)")
    error_message: Optional[str] = Field(default=None, description="错误信息")