"""工具集合（轻量版）。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, List

LOGGER_NAME = "ppt_agent"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(LOGGER_NAME)


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


class ResultSaver:
    """负责将生成结果持久化到 results 目录。"""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = ensure_directory(base_dir or Path("results"))

    def save_html(self, html: str, name: str) -> Path:
        path = self.base_dir / f"{name}.html"
        path.write_text(html, encoding="utf-8")
        logger.info("已保存 HTML 输出: %s", path)
        return path

    def save_json(self, data: dict, name: str) -> Path:
        path = self.base_dir / f"{name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("已保存 JSON 输出: %s", path)
        return path


result_saver = ResultSaver()


class _TextTools:
    """封装文本清洗、拆分等辅助逻辑。"""

    def segment_paragraphs(self, text: str) -> List[str]:
        raw_parts = [part.strip() for part in text.replace("\r", "").split("\n")]
        paragraphs: List[str] = []
        buffer: List[str] = []

        for part in raw_parts:
            if not part:
                if buffer:
                    paragraphs.append(" ".join(buffer))
                    buffer = []
                continue
            buffer.append(part)

        if buffer:
            paragraphs.append(" ".join(buffer))

        return [para for para in paragraphs if para]

    def derive_title(self, text: str) -> str:
        first_line = text.strip().splitlines()[0] if text.strip() else "演示文稿"
        return first_line[:80]

    def derive_section_title(self, text: str, fallback: str) -> str:
        sentences = self._split_sentences(text)
        if sentences:
            return sentences[0][:60]
        return fallback

    def summarise_text(self, text: str, max_sentences: int = 2) -> str:
        sentences = self._split_sentences(text)
        return " ".join(sentences[:max_sentences])

    def extract_key_points(self, text: str, max_points: int = 4) -> List[str]:
        sentences = self._split_sentences(text)
        return [sent.strip() for sent in sentences[:max_points] if sent.strip()]

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        separators = "。！？\n"
        sentence = ""
        sentences: List[str] = []
        for char in text:
            sentence += char
            if char in separators and sentence.strip():
                sentences.append(sentence.strip())
                sentence = ""
        if sentence.strip():
            sentences.append(sentence.strip())
        return sentences


text_tools = _TextTools()


__all__ = ["logger", "result_saver", "text_tools", "ensure_directory", "ResultSaver"]
