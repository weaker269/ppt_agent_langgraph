"""
PPT智能体主模块

提供便捷的API接口用于生成PPT演示文稿。
"""

from .graph import PPTAgentGraph, create_ppt_agent, generate_ppt_from_text, generate_ppt_from_file
from .state import OverallState, SlideContent, PresentationOutline, StyleTheme
from .evaluators import QualityEvaluator, QualityScore, OptimizationSuggestion
from .utils import logger, ConfigManager

__version__ = "1.0.0"
__author__ = "PPT智能体团队"

__all__ = [
    "PPTAgentGraph",
    "create_ppt_agent",
    "generate_ppt_from_text",
    "generate_ppt_from_file",
    "OverallState",
    "SlideContent",
    "PresentationOutline",
    "StyleTheme",
    "QualityEvaluator",
    "QualityScore", 
    "OptimizationSuggestion",
    "logger",
    "ConfigManager"
]