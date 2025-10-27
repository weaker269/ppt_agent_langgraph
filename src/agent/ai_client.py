"""统一 AI 客户端封装。

负责与大模型交互并产出结构化结果，必要时提供降级方案和离线 stub。
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .domain import StyleTheme
from .models import (
    ConsistencyAnalysisResponse,
    OutlineResponse,
    QualityAssessmentResponse,
    SlideResponse,
    StyleAnalysisResponse,
)
from .utils import snapshot_manager, text_tools

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

    def structured_completion(
        self,
        prompt: str,
        model: Type[T],
        system: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> T:
        """向模型请求结构化结果，并在出现解析问题时尝试自动修复或回退。"""

        context = context or {}
        prompt_attempt = prompt

        for attempt in range(2):
            if self.config.enable_stub:
                logger.debug("使用 stub 响应: %s", model.__name__)
                return self._stub_response(prompt_attempt, model)

            raw = self._call_model(prompt_attempt, system)
            if not raw.strip():
                logger.warning("模型返回结果为空，切换到 stub 模式")
                self.config.enable_stub = True
                continue

            try:
                return self._parse_json(raw, model, context=context)
            except (json.JSONDecodeError, ValidationError) as exc:
                self._log_parse_failure(exc, raw, prompt_attempt, model, context, attempt)
                if attempt == 0 and not self.config.enable_stub:
                    prompt_attempt = self._augment_prompt_for_retry(prompt, model)
                    continue
                self.config.enable_stub = True

        return self._stub_response(prompt_attempt, model)

    def _log_parse_failure(
        self,
        error: Exception,
        raw: str,
        prompt: str,
        model: Type[T],
        context: Dict[str, Any],
        attempt: int,
    ) -> None:
        logger.error("解析模型输出失败: %s", error)
        self._save_snapshot(context, raw, model, suffix=f"_attempt{attempt}_raw")
        if attempt == 0:
            self._save_snapshot(context, prompt, model, suffix=f"_attempt{attempt}_prompt")

    @staticmethod
    def _augment_prompt_for_retry(original_prompt: str, model: Type[T]) -> str:
        retry_instruction = "\n\nPlease return only a valid JSON object with double quotes and no extra text."

        if retry_instruction.strip() in original_prompt:
            return original_prompt
        return f"{original_prompt}{retry_instruction}"

    @staticmethod
    def _extract_json_block(text: str) -> str:
        if "```" in text:
            matches = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if matches:
                return matches[-1]

        start = text.find('{')
        if start == -1:
            return text

        depth = 0
        for idx in range(start, len(text)):
            char = text[idx]
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    return text[start:idx + 1]
        return text[start:]

    @staticmethod
    def _strip_js_functions(text: str) -> str:
        pattern = re.compile(r'("[-_a-zA-Z0-9]+"\s*:\s*)function\s*\([^)]*\)\s*\{.*?\}', re.DOTALL)

        def _replace(match):
            return f"{match.group(1)}null"

        return pattern.sub(_replace, text)

    def _save_snapshot(self, context: Dict[str, Any], content: str, model: Type[T], suffix: str) -> None:
        run_id = context.get("run_id")
        if not run_id:
            return
        stage = context.get("stage", "model")
        name = context.get("name") or context.get("entity") or model.__name__.lower()
        filename = f"{stage}/{name}{suffix}.txt"
        snapshot_manager.write_text(run_id, filename, content)

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
            data["estimated_duration"] = int(digits[0]) if digits else 15
        elif not isinstance(duration, int):
            data["estimated_duration"] = 15

        sections = data.get("sections") or []
        normalized_sections: List[Dict[str, Any]] = []
        for idx, section in enumerate(sections, start=1):
            if not isinstance(section, dict):
                continue
            title = (
                section.get("title")
                or section.get("section_title")
                or section.get("heading")
                or f"章节 {idx}"
            )
            summary = section.get("summary") or section.get("section_summary") or ""
            key_points_raw = section.get("key_points") or section.get("bullets") or []
            if isinstance(key_points_raw, str):
                key_points_raw = [item.strip() for item in re.split(r"[\n\r]", key_points_raw) if item.strip()]

            normalized_points: List[Dict[str, Any]] = []
            for point_idx, item in enumerate(key_points_raw, 1):
                if isinstance(item, dict):
                    point_text = (item.get("point") or item.get("text") or item.get("value") or "").strip()
                    template = (item.get("template_suggestion") or item.get("template") or item.get("layout") or "").strip()
                else:
                    point_text = str(item).strip()
                    template = ""
                if not point_text:
                    continue
                if template not in {
                    "simple_content",
                    "text_with_chart",
                    "text_with_table",
                    "full_width_image",
                    "standard_single_column",
                    "standard_dual_column",
                    "title_section",
                }:
                    template = "simple_content"
                normalized_points.append({"point": point_text, "template_suggestion": template})
            if not normalized_points:
                normalized_points.append({"point": title, "template_suggestion": "simple_content"})

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
                    "key_points": normalized_points,
                    "estimated_slides": max(1, min(int(estimated), 10)),
                }
            )
        data["sections"] = normalized_sections
        return data
    @staticmethod
    def _normalize_style_payload(data: Dict[str, Any]) -> Dict[str, Any]:
        theme_value = str(data.get("recommended_theme", ""))
        data["recommended_theme"] = AIModelClient._match_theme(theme_value)

        palette_raw = data.get("color_palette")
        palette: Dict[str, str] = {}
        if isinstance(palette_raw, dict):
            for key, value in palette_raw.items():
                if isinstance(value, str) and value.strip():
                    palette[key.strip()] = value.strip()
        elif isinstance(palette_raw, (list, tuple)):
            for item in palette_raw:
                if isinstance(item, dict):
                    name = (item.get("usage") or item.get("name") or item.get("role") or "").strip()
                    hex_value = (item.get("hex") or item.get("value") or item.get("color") or "").strip()
                    if name and hex_value:
                        palette[name] = hex_value
                elif isinstance(item, str):
                    match = re.search(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", item)
                    if match:
                        palette[f"color_{len(palette)+1}"] = match.group(0)
        data["color_palette"] = palette

        chart_colors_raw = data.get("chart_colors")
        if isinstance(chart_colors_raw, (list, tuple)):
            chart_colors = [color for color in chart_colors_raw if isinstance(color, str) and color.strip()]
        else:
            chart_colors = []
        if len(chart_colors) < 4:
            chart_colors.extend(["#2563eb", "#16a34a", "#f59e0b", "#f97316"])
        data["chart_colors"] = chart_colors[:6]

        font_raw = data.get("font_pairing")
        fonts: Dict[str, str] = {}
        if isinstance(font_raw, dict):
            for key, value in font_raw.items():
                if isinstance(value, str) and value.strip():
                    fonts[key.strip()] = value.strip()
        elif isinstance(font_raw, (list, tuple)):
            for item in font_raw:
                if isinstance(item, dict):
                    role = (item.get("role") or item.get("name") or item.get("usage") or "").strip()
                    font_name = (item.get("font_name") or item.get("font") or item.get("value") or "").strip()
                    if role and font_name:
                        fonts[role] = font_name
                elif isinstance(item, str):
                    parts = [part.strip() for part in re.split(r"[:|-]", item, maxsplit=1) if part.strip()]
                    if len(parts) == 2:
                        fonts[parts[0]] = parts[1]
        if "title" not in fonts:
            fonts["title"] = "Roboto"
        if "body" not in fonts:
            fonts["body"] = "Source Sans"
        data["font_pairing"] = fonts

        layout_pref = data.get("layout_preference")
        if isinstance(layout_pref, str):
            layout_pref = layout_pref.strip() or "balanced"
        else:
            layout_pref = "balanced"
        data["layout_preference"] = layout_pref

        reasoning = data.get("reasoning")
        if isinstance(reasoning, str):
            data["reasoning"] = reasoning.strip()
        return data

    @staticmethod
    def _normalize_quality_payload(data: Dict[str, Any]) -> Dict[str, Any]:
        def _extract_score(payload: Any) -> Optional[float]:
            if isinstance(payload, (int, float)):
                return float(payload)
            if isinstance(payload, str):
                digits = re.findall(r"[-+]?[0-9]*\.?[0-9]+", payload)
                if digits:
                    try:
                        return float(digits[0])
                    except ValueError:
                        return None
                return None
            if isinstance(payload, dict):
                for key in ("score", "value", "rating", "overall", "total"):
                    if key in payload and payload[key] is not None:
                        try:
                            return float(payload[key])
                        except (TypeError, ValueError):
                            continue
            return None

        assessment = data.get("assessment")
        if isinstance(assessment, dict):
            for key, value in assessment.items():
                score = _extract_score(value)
                if score is not None:
                    data[key] = score

        dimensions = {
            "logic": "logic_score",
            "logical": "logic_score",
            "logic_dimension": "logic_score",
            "relevance": "relevance_score",
            "content": "relevance_score",
            "language": "language_score",
            "communication": "language_score",
            "style": "layout_score",
            "layout": "layout_score",
            "visual": "layout_score",
        }
        for source, target in dimensions.items():
            if isinstance(data.get(target), (int, float)):
                continue
            entry = data.get(source)
            score = _extract_score(entry)
            if score is not None:
                data[target] = score

        if not isinstance(data.get("overall_score"), (int, float)):
            overall_entry = (
                data.get("overall")
                or data.get("summary")
                or data.get("overall_assessment")
                or (assessment.get("overall") if isinstance(assessment, dict) else None)
            )
            score = _extract_score(overall_entry)
            if score is None:
                collected = [
                    data.get("logic_score"),
                    data.get("relevance_score"),
                    data.get("language_score"),
                    data.get("layout_score"),
                ]
                collected = [value for value in collected if isinstance(value, (int, float))]
                if collected:
                    score = sum(collected) / len(collected)
            if score is not None:
                data["overall_score"] = score

        if "pass_threshold" not in data:
            decision_keys = ("pass", "passed", "is_pass", "pass_threshold")
            decided = False
            for key in decision_keys:
                if key in data:
                    value = data[key]
                    if isinstance(value, bool):
                        data["pass_threshold"] = value
                        decided = True
                        break
                    if isinstance(value, str):
                        lowered = value.strip().lower()
                        if lowered in {"true", "pass", "yes", "通过"}:
                            data["pass_threshold"] = True
                            decided = True
                            break
                        if lowered in {"false", "fail", "no", "未通过"}:
                            data["pass_threshold"] = False
                            decided = True
                            break
            if not decided and isinstance(data.get("overall_score"), (int, float)):
                data["pass_threshold"] = data["overall_score"] >= 85

        if "strengths" not in data:
            highlights = data.get("highlights") or data.get("advantages")
            if isinstance(highlights, str):
                data["strengths"] = [segment.strip() for segment in re.split(r"[\s;]", highlights) if segment.strip()]
            elif isinstance(highlights, list):
                data["strengths"] = [str(item).strip() for item in highlights if str(item).strip()]

        if "weaknesses" not in data and isinstance(data.get("issues"), list):
            data["weaknesses"] = [str(item).strip() for item in data["issues"] if str(item).strip()]

        if "suggestions" not in data:
            advice = data.get("recommendations") or data.get("actions")
            if isinstance(advice, str):
                data["suggestions"] = [segment.strip() for segment in re.split(r"[\s;]", advice) if segment.strip()]
            elif isinstance(advice, list):
                data["suggestions"] = [str(item).strip() for item in advice if str(item).strip()]

        return data

    @staticmethod
    def _normalize_slide_payload(data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return {"slide_html": ""}

        html_candidates = (
            data.get("slide_html"),
            data.get("slideHtml"),
            data.get("html"),
            data.get("content"),
            data.get("body"),
        )
        for candidate in html_candidates:
            if isinstance(candidate, str) and candidate.strip():
                data["slide_html"] = candidate.strip()
                break

        speaker = data.get("speaker_notes") or data.get("speakerNotes") or data.get("notes")
        if isinstance(speaker, str):
            data["speaker_notes"] = speaker.strip()
        elif speaker is None:
            data["speaker_notes"] = ""

        title_candidate = data.get("page_title") or data.get("title") or data.get("pageTitle")
        if isinstance(title_candidate, str):
            data["page_title"] = title_candidate.strip()

        layout_candidate = data.get("layout_template") or data.get("layoutTemplate") or data.get("layout")
        if isinstance(layout_candidate, str):
            data["layout_template"] = layout_candidate.strip()

        suggestion_candidate = data.get("template_suggestion") or data.get("templateSuggestion")
        if isinstance(suggestion_candidate, str):
            data["template_suggestion"] = suggestion_candidate.strip()

        charts = data.get("charts")
        if isinstance(charts, dict):
            charts_iterable = [charts]
        elif isinstance(charts, list):
            charts_iterable = charts
        else:
            charts_iterable = []

        normalised_charts = []
        for chart in charts_iterable:
            if not isinstance(chart, dict):
                continue
            element = (
                chart.get("elementId")
                or chart.get("element_id")
                or chart.get("id")
                or chart.get("chartId")
                or chart.get("chart_id")
            )
            if isinstance(element, str) and element.strip():
                chart["elementId"] = element.strip()
            elif element is not None:
                chart["elementId"] = str(element)

            options = chart.get("options") if "options" in chart else chart.get("option")
            if isinstance(options, dict):
                chart["options"] = options
            elif isinstance(options, str):
                try:
                    chart["options"] = json.loads(options)
                except Exception:
                    chart["options"] = {}
            if "options" not in chart:
                chart["options"] = {}

            for extra in ("element_id", "id", "chartId", "chart_id", "option"):
                chart.pop(extra, None)

            if chart.get("elementId"):
                normalised_charts.append(chart)

        data["charts"] = normalised_charts

        if not isinstance(data.get("slide_html"), str) or len(data["slide_html"].strip()) < 20:
            data["slide_html"] = (
                '<div class="slide-content">'
                '<div class="page-header"><h2>占位幻灯片</h2></div>'
                '<div class="content-grid grid-1-cols">'
                '<div class="card"><p>内容生成出现异常，当前为占位结果。</p></div>'
                '</div>'
                '</div>'
            )
        if "page_title" not in data or not isinstance(data["page_title"], str) or not data["page_title"].strip():
            data["page_title"] = "占位幻灯片"
        if "layout_template" not in data or not isinstance(data["layout_template"], str):
            data["layout_template"] = "standard_single_column"
        if "template_suggestion" not in data or not isinstance(data["template_suggestion"], str):
            data["template_suggestion"] = "simple_content"
        return data

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
    def _parse_json(text: str, model: Type[T], *, context: Optional[Dict[str, Any]] = None) -> T:
        cleaned = AIModelClient._extract_json_block(text)
        cleaned = AIModelClient._strip_js_functions(cleaned)
        data = json.loads(cleaned)

        if model is OutlineResponse:
            data = AIModelClient._normalize_outline_payload(data)
        if model is StyleAnalysisResponse:
            data = AIModelClient._normalize_style_payload(data)
        if model is QualityAssessmentResponse:
            data = AIModelClient._normalize_quality_payload(data)
        if model is SlideResponse:
            data = AIModelClient._normalize_slide_payload(data)

        return model(**data)

    def _stub_response(self, prompt: str, model: Type[T]) -> T:
        """为断网/调试场景提供结构化占位结果。"""

        if model is SlideResponse:
            payload = {
                "slide_html": (
                    '<div class="slide-content">'
                    '<div class="page-header"><h2>占位幻灯片</h2></div>'
                    '<div class="content-grid grid-1-cols">'
                    '<div class="card"><p>当前处于 stub 模式，未调用真实模型。</p></div>'
                    '</div>'
                    '</div>'
                ),
                "charts": [],
                "speaker_notes": "占位提示：请连接真实模型以生成最终内容。",
                "page_title": "占位幻灯片",
                "layout_template": "standard_single_column",
                "template_suggestion": "simple_content",
            }
        elif model is OutlineResponse:
            payload = {
                "title": "占位演示文稿",
                "subtitle": "离线模式草稿",
                "target_audience": "内部评审",
                "estimated_duration": 15,
                "sections": [
                    {
                        "section_id": 1,
                        "title": "占位章节",
                        "summary": "用于 stub 模式的默认章节。",
                        "key_points": [
                            {"point": "占位要点一"},
                            {"point": "占位要点二"}
                        ],
                        "estimated_slides": 2,
                    }
                ],
            }
        elif model is StyleAnalysisResponse:
            payload = {
                "recommended_theme": StyleTheme.PROFESSIONAL,
                "color_palette": {
                    "primary": "#0D47A1",
                    "on_primary": "#FFFFFF",
                    "background": "#F5F7FA",
                    "text": "#1E293B",
                    "text_muted": "#64748B",
                    "border": "#E2E8F0",
                    "accent": "#F97316",
                },
                "chart_colors": ["#0D47A1", "#F97316", "#16A34A", "#5A67D8"],
                "font_pairing": {"title": "Source Han Sans CN", "body": "Source Han Sans CN"},
                "layout_preference": "balanced",
                "reasoning": "占位样式：stub 模式下提供的默认专业方案。",
            }
        elif model is QualityAssessmentResponse:
            payload = {
                "overall_score": 90.0,  # 恢复默认分数
                "logic_score": 90.0,
                "relevance_score": 90.0,
                "language_score": 90.0,
                "layout_score": 90.0,
                "strengths": ["结构完整", "语言流畅"],
                "weaknesses": ["占位结果，仅供内部调试"],
                "suggestions": ["连接真实模型以获取正式评审结果。"],
                "pass_threshold": True,
                "issues": [
                    {
                        "dimension": "relevance",
                        "description": "占位问题：内容深度可进一步增强",
                        "suggestion": "补充更多数据支撑和案例",
                        "evidence_refs": ["E1", "E2"]
                    }
                ],
            }
        elif model is ConsistencyAnalysisResponse:
            payload = {
                "overall_score": 85.0,
                "issues": [],
                "strengths": ["占位结果"],
                "recommendations": ["启用真实模型进行一致性检测。"],
            }
        else:
            raise ValueError(f"No stub available for model: {model.__name__}")

        return model(**payload)

