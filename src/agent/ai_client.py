"""统一 AI 客户端封装。

负责与大模型交互并产出结构化结果，必要时提供降级方案和离线 stub。
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel

from .domain import StyleTheme
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
    provider: str = "google"
    model: str = "gemini-2.5-flash"
    temperature: float = 0.6
    max_tokens: int = 65536
    timeout: int = 600
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
        if not raw.strip():
            logger.warning("模型返回内容为空，切换至 stub 模式")
            self.config.enable_stub = True
            return self._stub_response(prompt, model)

        return self._parse_json(raw, model)

    # ------------------------------------------------------------------
    # 模型调用
    # ------------------------------------------------------------------

    def _initialize_client(self):
        try:
            if self.config.provider == "openai":
                from openai import OpenAI

                api_key = os.environ.get("OPENAI_API_KEY")
                if api_key:
                    return OpenAI(api_key=api_key)
                return OpenAI()
            if self.config.provider == "google":
                import google.generativeai as genai

                api_key = os.environ.get("GOOGLE_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)
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
                        "response_mime_type": "application/json",
                    },
                )
                return self._extract_google_text(response)
        except Exception as exc:  # pragma: no cover - 网络异常
            logger.error("模型调用失败: %s", exc)
        return ""

    @staticmethod
    def _extract_google_text(response: Any) -> str:
        candidates = getattr(response, "candidates", None)
        if not candidates:
            logger.warning("Google 模型未返回候选结果，可能因安全策略被拦截")
            return ""

        reason_map = {
            0: "UNSPECIFIED",
            1: "STOP",
            2: "MAX_TOKENS",
            3: "SAFETY",
            4: "RECITATION",
            5: "OTHER",
        }

        for candidate in candidates:
            finish_reason = getattr(candidate, "finish_reason", None)
            reason_label = reason_map.get(finish_reason, str(finish_reason)) if isinstance(finish_reason, int) else str(finish_reason)
            content = getattr(candidate, "content", None)
            parts = []
            if content is not None:
                for part in getattr(content, "parts", []) or []:
                    text = getattr(part, "text", None)
                    if text:
                        parts.append(text)
            if not parts:
                continue

            if reason_label in {"None", "UNSPECIFIED", "STOP", "FINISH_REASON_STOP"}:
                return "\n".join(parts)
            if reason_label in {"MAX_TOKENS", "FINISH_REASON_MAX_TOKENS"}:
                logger.info("Google 模型输出因触达 token 上限而截断，仍将使用当前内容")
                return "\n".join(parts)
            if reason_label in {"SAFETY", "FINISH_REASON_SAFETY"}:
                logger.warning("Google 模型输出被安全策略拦截 (finish_reason=%s)", reason_label)
                return ""
            logger.info("Google 模型返回 finish_reason=%s，继续使用生成内容", reason_label)
            return "\n".join(parts)
        logger.warning("Google 模型未返回有效文本内容")
        return ""

    # ------------------------------------------------------------------
    # 解析 & Stub
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_outline_payload(data: Dict[str, Any]) -> Dict[str, Any]:
        duration = data.get("estimated_duration")
        if isinstance(duration, str):
            digits = re.findall(r"\d+", duration)
            if digits:
                data["estimated_duration"] = int(digits[0])
            else:
                data["estimated_duration"] = 15

        sections = data.get("sections") or []
        normalized_sections = []
        for idx, section in enumerate(sections, start=1):
            if not isinstance(section, dict):
                continue
            title = section.get("title") or section.get("section_title") or section.get("heading") or f"章节 {idx}"
            summary = section.get("summary") or section.get("section_summary") or ""
            key_points = section.get("key_points") or section.get("bullets") or []
            if isinstance(key_points, str):
                key_points = [item.strip() for item in key_points.split("\n") if item.strip()]
            estimated = section.get("estimated_slides") or section.get("slides") or section.get("estimated_slide_count")
            if isinstance(estimated, str):
                digits = re.findall(r"\d+", estimated)
                estimated = int(digits[0]) if digits else 3
            if not isinstance(estimated, int):
                estimated = 3
            normalized_sections.append(
                {
                    "section_id": section.get("section_id") or idx,
                    "title": title,
                    "summary": summary,
                    "key_points": key_points,
                    "estimated_slides": estimated,
                }
            )
        data["sections"] = normalized_sections
        return data

    @staticmethod
    def _normalize_style_payload(data: Dict[str, Any]) -> Dict[str, Any]:
        theme_value = str(data.get("recommended_theme", ""))
        matched = AIModelClient._match_theme(theme_value)
        data["recommended_theme"] = matched.value
        palette = data.get("color_palette") or []
        if isinstance(palette, str):
            palette = [item.strip() for item in palette.split(",") if item.strip()]
        data["color_palette"] = palette
        fonts = data.get("font_pairing") or []
        if isinstance(fonts, str):
            fonts = [item.strip() for item in fonts.split(",") if item.strip()]
        data["font_pairing"] = fonts
        return data

    @staticmethod
    def _match_theme(raw: str) -> StyleTheme:
        value = raw.lower()
        if value in StyleTheme._value2member_map_:
            return StyleTheme(value)
        keywords = {
            StyleTheme.PROFESSIONAL: ["专业", "business", "corporate"],
            StyleTheme.MODERN: ["科技", "tech", "modern", "future"],
            StyleTheme.CREATIVE: ["创意", "creative", "design"],
            StyleTheme.ACADEMIC: ["学术", "research", "academic"],
            StyleTheme.MINIMAL: ["极简", "minimal", "simple"],
        }
        for theme, hints in keywords.items():
            if any(hint in value for hint in hints):
                return theme
        return StyleTheme.PROFESSIONAL

    @staticmethod
    def _parse_json(text: str, model: Type[T]) -> T:
        if "```" in text:
            pieces = text.split("```")
            for piece in pieces:
                piece = piece.strip()
                if piece.startswith("json"):
                    return model(**json.loads(piece[len("json"):].strip()))
                if piece.startswith("{"):
                    return model(**json.loads(piece))
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("解析模型输出失败: %s", exc)
            raise

        if model is OutlineResponse:
            data = AIModelClient._normalize_outline_payload(data)
        if model is StyleAnalysisResponse:
            data = AIModelClient._normalize_style_payload(data)
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
