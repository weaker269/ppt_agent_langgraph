"""幻灯片内容生成器（轻量版）。

根据 `PresentationOutline` 生成结构化的 `SlideContent` 列表。
"""

from __future__ import annotations

from typing import List

from ..domain import OutlineSection, PresentationOutline, SlideContent, SlideLayout, SlideType
from ..state import OverallState


class SlideComposer:
    """负责将大纲转换为幻灯片内容。"""

    def build_slides(self, outline: PresentationOutline) -> List[SlideContent]:
        slides: List[SlideContent] = []
        slide_id = 1

        slides.append(
            SlideContent(
                slide_id=slide_id,
                slide_type=SlideType.TITLE,
                layout=SlideLayout.TITLE,
                title=outline.title,
                body="",
                bullet_points=[section.title for section in outline.sections[:4]],
                notes="概述演示主旨与结构",
            )
        )
        slide_id += 1

        for section in outline.sections:
            slides.extend(self._build_section_slides(section, start_id=slide_id))
            slide_id = slides[-1].slide_id + 1

        slides.append(
            SlideContent(
                slide_id=slide_id,
                slide_type=SlideType.SUMMARY,
                layout=SlideLayout.STANDARD,
                title="总结与下一步",
                body="综合回顾要点",
                bullet_points=self._collect_summary_points(outline),
                notes="鼓励听众提问或讨论下一步行动",
            )
        )

        return slides

    def _build_section_slides(self, section: OutlineSection, start_id: int) -> List[SlideContent]:
        slides: List[SlideContent] = []

        slides.append(
            SlideContent(
                slide_id=start_id,
                slide_type=SlideType.SECTION,
                layout=SlideLayout.TITLE,
                title=section.title,
                body=section.summary,
                bullet_points=[],
                notes="引入章节背景",
            )
        )

        current_id = start_id + 1
        for point in section.key_points:
            slides.append(
                SlideContent(
                    slide_id=current_id,
                    slide_type=SlideType.CONTENT,
                    layout=SlideLayout.STANDARD,
                    title=point,
                    body="",
                    bullet_points=self._expand_point(point),
                    notes=f"围绕“{point}”展开阐述，补充数据或案例",
                )
            )
            current_id += 1

        return slides

    @staticmethod
    def _expand_point(point: str) -> List[str]:
        if len(point) < 40:
            return [point, "补充背景", "关键证据"]
        return [segment.strip() for segment in point.split("，") if segment.strip()][:4]

    @staticmethod
    def _collect_summary_points(outline: PresentationOutline) -> List[str]:
        highlights = []
        for section in outline.sections:
            if section.key_points:
                highlights.append(f"{section.title}: {section.key_points[0]}")
        return highlights[:5] or ["回顾核心结论", "呼吁下一步行动"]


class SlidingWindowContentGenerator:
    """兼容旧接口的外层封装。"""

    def __init__(self) -> None:
        self.composer = SlideComposer()

    def generate_all_slides(self, state: OverallState) -> OverallState:
        if not state.outline:
            state.record_error("缺少大纲，无法生成幻灯片")
            return state

        state.slides = self.composer.build_slides(state.outline)
        return state


__all__ = ["SlidingWindowContentGenerator", "SlideComposer"]
