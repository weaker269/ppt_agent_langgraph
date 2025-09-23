"""
PPT智能体质量评估模块

提供幻灯片内容的多维度质量评分和优化建议。
"""

from .quality import QualityEvaluator, QualityScore, OptimizationSuggestion

__all__ = [
    "QualityEvaluator",
    "QualityScore", 
    "OptimizationSuggestion"
]