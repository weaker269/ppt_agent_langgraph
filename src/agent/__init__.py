"""PPT Agent 轻量化接口。

该包提供 LangGraph 工作流封装及生成结果的数据结构。
"""

from .graph import (
    PPTAgentGraph,
    create_ppt_agent,
    generate_ppt_from_file,
    generate_ppt_from_text,
)
from .domain import PresentationOutline, SlideContent, SlideLayout, SlideType, StyleTheme
from .state import OverallState
from . import utils

__all__ = [
    "PPTAgentGraph",
    "create_ppt_agent",
    "generate_ppt_from_file",
    "generate_ppt_from_text",
    "PresentationOutline",
    "SlideContent",
    "SlideLayout",
    "SlideType",
    "StyleTheme",
    "OverallState",
    "utils",
]
