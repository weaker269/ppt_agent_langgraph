"""
PPT智能体一致性验证模块

提供跨页面一致性检查和内容验证功能。
"""

from .consistency import ConsistencyChecker, ConsistencyReport, ConsistencyIssue

__all__ = [
    "ConsistencyChecker",
    "ConsistencyReport", 
    "ConsistencyIssue"
]