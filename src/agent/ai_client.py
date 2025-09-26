"""统一 AI 客户端封装。

负责与大模型交互并产出结构化结果，必要时提供降级方案和离线 stub。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel

from .models import (
    ConsistencyAnalysisResponse,
    OutlineResponse,
    QualityAssessmentResponse,
    SlideResponse,
    StyleAnalysisResponse,
)
from .utils import text_tools

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass
class AIConfig:
    provider: str = "openai"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.6
    max_tokens: int = 1800
    timeout: int = 60
    enable_stub: bool = False


class AIModelClient:
    """统一客户端，支持真实模型与 stub。"""

    def __init__(self, config: Optional[AIConfig] = None) -> None:
        self.config = config or AIConfig()
        self._client = None
        if not self.config.enable_stub:
            self._client = self._initialize_client()

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def structured_completion(self, prompt: str, model: Type[T], system: str = "") -> T:
        if self.config.enable_stub:
            return self._stub_response(prompt, model)

        raw = self._call_model(prompt, system)
        return self._parse_json(raw, model)

    # ------------------------------------------------------------------
    # 模型调用
    # ------------------------------------------------------------------

    def _initialize_client(self):
        try:
            if self.config.provider == "openai":
                from openai import OpenAI

                return OpenAI()
            if self.config.provider == "google":
                import google.generativeai as genai

                return genai.GenerativeModel(self.config.model)
        except Exception as exc:  # pragma: no cover - 网络异常
            logger.warning("模型初始化失败，转入 stub 模式: %s", exc)
            self.config.enable_stub = True
        return None

    def _call_model(self, prompt: str, system: str) -> str:
        try:
            if self.config.provider == "openai":
                response = self._client.chat.completions.create(  # type: ignore[attr-defined]
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": system or "You are a helpful assistant."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    timeout=self.config.timeout,
                )
                return response.choices[0].message.content  # type: ignore[index]

            if self.config.provider == "google":
                formatted = f"{system}\n\n{prompt}" if system else prompt
                response = self._client.generate_content(  # type: ignore[attr-defined]
                    formatted,
                    generation_config={
                        "temperature": self.config.temperature,
                        "max_output_tokens": self.config.max_tokens,
                    },
                )
                return response.text
        except Exception as exc:  # pragma: no cover - 网络异常
            logger.error("模型调用失败: %s", exc)
        return ""

    # ------------------------------------------------------------------
    # 解析 & Stub
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(text: str, model: Type[T]) -> T:
        if "```" in text:
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[len("json"):]
        data = json.loads(text)
        return model(**data)

    def _stub_response(self, prompt: str, model: Type[T]) -> T:
        if model is OutlineResponse:
            return self._stub_outline(prompt)  # type: ignore[return-value]
        if model is SlideResponse:
            return self._stub_slide(prompt)  # type: ignore[return-value]
        if model is StyleAnalysisResponse:
            return self._stub_style(prompt)  # type: ignore[return-value]
        if model is QualityAssessmentResponse:
            return self._stub_quality(prompt)  # type: ignore[return-value]
        if model is ConsistencyAnalysisResponse:
            return self._stub_consistency(prompt)  # type: ignore[return-value]
        raise ValueError(f"未实现的 stub 响应: {model.__name__}")

    def _stub_outline(self, text: str) -> OutlineResponse:
        paragraphs = text_tools.segment_paragraphs(text)
        sections = []
        for idx, para in enumerate(paragraphs[:5], 1):
            sections.append(
                {
                    "section_id": idx,
                    "title": text_tools.derive_section_title(para, f"章节 {idx}"),
                    "summary": text_tools.summarise_text(para, 2),
                    "key_points": text_tools.extract_key_points(para, 4),
                    "estimated_slides": max(1, len(para) // 400 + 1),
                }
            )
        return OutlineResponse(
            title=text_tools.derive_title(text),
            sections=sections or [
                {
                    "section_id": 1,
                    "title": "核心内容",
                    "summary": "请补充输入信息",
                    "key_points": ["关键点"],
                    "estimated_slides": 2,
                }
            ],
        )

    def _stub_slide(self, prompt: str) -> SlideResponse:
        outline = text_tools.extract_key_points(prompt, 3)
        return SlideResponse(
            title=outline[0] if outline else text_tools.derive_title(prompt)[:50],
            body="\n".join(outline[1:4]) or "补充说明",
            bullet_points=outline or ["重点一", "重点二"],
            speaker_notes="围绕要点展开说明",
            slide_type="content",
            layout="standard",
        )

    def _stub_style(self, prompt: str) -> StyleAnalysisResponse:
        return StyleAnalysisResponse(
            recommended_theme=StyleTheme.PROFESSIONAL,
            color_palette=["#1f2937", "#f9fafb", "#2563eb"],
            font_pairing=["Roboto", "Noto Sans"],
            layout_preference="balanced",
            reasoning="根据输入文本无法识别特定语境，使用默认专业主题。",
        )

    def _stub_quality(self, prompt: str) -> QualityAssessmentResponse:
        base = 82.0
        if "summary" in prompt.lower():
            base = 88.0
        return QualityAssessmentResponse(
            overall_score=base,
            logic_score=base - 2,
            relevance_score=base + 1,
            language_score=base,
            layout_score=max(75.0, base - 5),
            strengths=["结构清晰", "要点突出"],
            weaknesses=["需要更多数据支撑"],
            suggestions=["补充具体案例", "增加视觉元素"],
            pass_threshold=base >= 85,
        )

    def _stub_consistency(self, prompt: str) -> ConsistencyAnalysisResponse:
        return ConsistencyAnalysisResponse(
            overall_score=90.0,
            issues=[],
            strengths=["术语使用一致", "章节过渡自然"],
            recommendations=["可增加结论页行动项"],
        )


__all__ = ["AIModelClient", "AIConfig"]
