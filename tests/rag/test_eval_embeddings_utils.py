"""验证嵌入评测脚本中的文本处理辅助函数"""

from __future__ import annotations

from scripts.eval_embeddings import chunk_text, strip_markdown


def test_strip_markdown_removes_markers_and_preserves_paragraphs() -> None:
    raw = (
        "# 概述\n\n"
        "> 引用说明\n"
        "第一段包含 **加粗** 和 `代码`。\n\n"
        "第二段包含 [链接](https://example.com)。\n"
    )

    cleaned = strip_markdown(raw)

    assert "#" not in cleaned
    assert ">" not in cleaned
    assert "**" not in cleaned
    assert "`" not in cleaned
    paragraphs = [p for p in cleaned.split("\n\n") if p]
    assert len(paragraphs) >= 2
    assert "链接" in cleaned


def test_chunk_text_respects_paragraph_boundaries() -> None:
    cleaned = "第一段内容。\n\n第二段继续说明。"
    chunks = chunk_text(cleaned, max_chars=6, overlap=2)

    assert chunks
    assert chunks[0].startswith("第一段")
    assert any(chunk.startswith("第二段") for chunk in chunks)
