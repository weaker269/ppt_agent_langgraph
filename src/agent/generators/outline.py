"""大纲生成器（轻量版）。

基于纯文本的启发式拆分生成 `PresentationOutline`，避免依赖外部大模型，
方便在本地快速验证整体流程。
"""

from __future__ import annotations

import re
from typing import Iterable, List

from ..domain import OutlineSection, PresentationOutline
from ..state import OverallState
from ..utils import text_tools


class OutlineGenerator:
    """将输入文本转换为结构化演示大纲。"""

    def __init__(self, section_size: int = 1200) -> None:
        self.section_size = section_size

    def generate_outline(self, state: OverallState) -> OverallState:
        if not state.input_text.strip():
            state.record_error("输入文本为空，无法生成大纲")
            return state

        paragraphs = text_tools.segment_paragraphs(state.input_text)
        sections = self._build_sections(paragraphs)

        outline = PresentationOutline(
            title=text_tools.derive_title(state.input_text),
            sections=sections,
            target_audience="通用听众",
            estimated_duration=max(5, len(sections) * 3),
        )

        state.outline = outline
        return state

    def _build_sections(self, paragraphs: List[str]) -> List[OutlineSection]:
        if not paragraphs:
            return [OutlineSection(index=1, title="内容概览", summary="", key_points=["补充输入信息"]) ]

        chunks = list(self._chunk_paragraphs(paragraphs))
        sections: List[OutlineSection] = []

        for idx, chunk in enumerate(chunks, start=1):
            combined = " ".join(chunk).strip()
            title = text_tools.derive_section_title(combined, fallback=f"章节 {idx}")
            key_points = text_tools.extract_key_points(combined, max_points=4)
            summary = text_tools.summarise_text(combined, max_sentences=2)
            sections.append(
                OutlineSection(
                    index=idx,
                    title=title,
                    summary=summary,
                    key_points=key_points or [summary or title],
                )
            )

        return sections

    def _chunk_paragraphs(self, paragraphs: Iterable[str]) -> Iterable[List[str]]:
        buffer: List[str] = []
        current_length = 0

        for paragraph in paragraphs:
            length = len(paragraph)
            if current_length + length > self.section_size and buffer:
                yield buffer
                buffer = [paragraph]
                current_length = length
            else:
                buffer.append(paragraph)
                current_length += length

        if buffer:
            yield buffer


__all__ = ["OutlineGenerator"]
