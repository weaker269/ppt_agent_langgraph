"""文档分块逻辑。"""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from .models import DocumentChunk, DocumentSection, LoadedDocument


DEFAULT_CHUNK_SIZE = 280
DEFAULT_SENTENCE_OVERLAP = 1
FALLBACK_OVERLAP_CHARS = 40


SentenceTuple = Tuple[str, int, int]


def _split_sentences(text: str) -> List[SentenceTuple]:
    """粗粒度中文断句并保留偏移。"""

    sentences: List[SentenceTuple] = []
    if not text:
        return sentences

    end_tokens = "。！？!?；;\n"
    start: int | None = None

    for idx, ch in enumerate(text):
        if start is None:
            if ch.isspace():
                continue
            start = idx

        if ch in end_tokens and start is not None:
            end = idx + 1
            raw = text[start:end]
            stripped = raw.strip()
            if stripped:
                leading_spaces = len(raw) - len(raw.lstrip())
                trailing_spaces = len(raw) - len(raw.rstrip())
                real_start = start + leading_spaces
                real_end = end - trailing_spaces
                sentences.append((stripped, real_start, real_end))
            start = None

    if start is not None:
        raw = text[start:]
        stripped = raw.strip()
        if stripped:
            leading_spaces = len(raw) - len(raw.lstrip())
            real_start = start + leading_spaces
            real_end = real_start + len(stripped)
            sentences.append((stripped, real_start, real_end))

    if not sentences and text.strip():
        stripped = text.strip()
        start_index = text.find(stripped)
        sentences.append((stripped, start_index, start_index + len(stripped)))

    return sentences


def _split_sentence_by_window(
    sentence: SentenceTuple,
    chunk_size: int,
    overlap_chars: int,
) -> List[SentenceTuple]:
    content, start, _ = sentence
    if len(content) <= chunk_size:
        return [sentence]

    window = chunk_size
    overlap = max(0, min(overlap_chars, chunk_size // 2))
    stride = max(1, window - overlap)
    pieces: List[SentenceTuple] = []

    for offset in range(0, len(content), stride):
        segment = content[offset : offset + window]
        segment_start = start + offset
        segment_end = segment_start + len(segment)
        pieces.append((segment, segment_start, segment_end))
        if offset + window >= len(content):
            break

    return pieces


def _normalize_sentences(
    sentences: Sequence[SentenceTuple],
    chunk_size: int,
) -> List[SentenceTuple]:
    normalized: List[SentenceTuple] = []
    for sentence in sentences:
        normalized.extend(
            _split_sentence_by_window(sentence, chunk_size, FALLBACK_OVERLAP_CHARS)
        )
    return normalized


def _merge_sentences(
    sentences: Sequence[SentenceTuple],
    chunk_size: int,
    overlap: int,
) -> List[List[SentenceTuple]]:
    chunks: List[List[SentenceTuple]] = []
    buffer: List[SentenceTuple] = []
    buffer_length = 0

    for sentence in sentences:
        sentence_length = len(sentence[0])
        if buffer and buffer_length + sentence_length > chunk_size:
            chunks.append(buffer)
            if overlap > 0:
                buffer = buffer[-overlap:]
                buffer_length = sum(len(s[0]) for s in buffer)
            else:
                buffer = []
                buffer_length = 0

        buffer.append(sentence)
        buffer_length += sentence_length

    if buffer:
        chunks.append(buffer)

    return chunks


def _chunk_section(
    section: DocumentSection,
    document_id: str,
    source: str,
    base_index: int,
    chunk_size: int,
    overlap: int,
) -> List[DocumentChunk]:
    if section.is_empty():
        return []

    sentences = _split_sentences(section.text)
    sentences = _normalize_sentences(sentences, chunk_size)
    sentence_groups = _merge_sentences(sentences, chunk_size, overlap)

    chunks: List[DocumentChunk] = []

    for group_index, sentence_group in enumerate(sentence_groups):
        content = "".join(sentence for sentence, _, _ in sentence_group).strip()
        if not content:
            continue

        first_sentence = sentence_group[0]
        last_sentence = sentence_group[-1]
        start_char = section.start_char + first_sentence[1]
        end_char = section.start_char + last_sentence[2]

        chunk = DocumentChunk(
            chunk_id=f"{document_id}_chunk_{base_index + group_index:04d}",
            document_id=document_id,
            content=content,
            source=source,
            section_title=section.title,
            section_level=section.level,
            page_number=section.page_number,
            start_char=start_char,
            end_char=end_char,
            metadata=dict(section.metadata),
        )
        chunks.append(chunk)

    return chunks


def chunk_document(
    document: LoadedDocument,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    sentence_overlap: int = DEFAULT_SENTENCE_OVERLAP,
) -> List[DocumentChunk]:
    """对单个文档执行递归分块。"""

    normalized_chunk_size = max(80, min(chunk_size, 800))
    normalized_overlap = max(0, min(sentence_overlap, 3))

    chunks: List[DocumentChunk] = []
    base_index = 0
    for section in document.non_empty_sections():
        section_chunks = _chunk_section(
            section,
            document_id=document.metadata.document_id,
            source=document.metadata.source_path,
            base_index=base_index,
            chunk_size=normalized_chunk_size,
            overlap=normalized_overlap,
        )
        chunks.extend(section_chunks)
        base_index += len(section_chunks)

    return chunks


def chunk_documents(
    documents: Iterable[LoadedDocument],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    sentence_overlap: int = DEFAULT_SENTENCE_OVERLAP,
) -> List[DocumentChunk]:
    chunks: List[DocumentChunk] = []
    for document in documents:
        chunks.extend(chunk_document(document, chunk_size, sentence_overlap))
    return chunks


__all__ = [
    "chunk_document",
    "chunk_documents",
]
