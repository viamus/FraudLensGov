from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .normalization import normalize_text, stable_id


@dataclass(frozen=True)
class DocumentChunk:
    id: str
    document_id: str
    source: str
    text: str
    position: int
    metadata: dict[str, Any] = field(default_factory=dict)


def chunk_text(
    document_id: str,
    source: str,
    text: str,
    chunk_words: int = 180,
    overlap_words: int = 30,
    metadata: dict[str, Any] | None = None,
) -> list[DocumentChunk]:
    words = re.findall(r"\S+", text)
    if not words:
        return []
    step = max(1, chunk_words - overlap_words)
    chunks: list[DocumentChunk] = []
    for position, start in enumerate(range(0, len(words), step)):
        selected = words[start : start + chunk_words]
        if not selected:
            continue
        chunk_body = " ".join(selected)
        chunks.append(
            DocumentChunk(
                id=stable_id(document_id, source, position, chunk_body),
                document_id=document_id,
                source=source,
                text=chunk_body,
                position=position,
                metadata=metadata or {},
            )
        )
        if start + chunk_words >= len(words):
            break
    return chunks


def retrieve_chunks(query: str, chunks: list[DocumentChunk], limit: int = 5) -> list[tuple[DocumentChunk, float]]:
    query_terms = _terms(query)
    if not query_terms:
        return []

    scored: list[tuple[DocumentChunk, float]] = []
    for chunk in chunks:
        chunk_terms = _terms(chunk.text)
        if not chunk_terms:
            continue
        overlap = len(query_terms & chunk_terms)
        if overlap == 0:
            continue
        score = overlap / len(query_terms | chunk_terms)
        scored.append((chunk, score))
    return sorted(scored, key=lambda pair: pair[1], reverse=True)[:limit]


def _terms(text: str) -> set[str]:
    normalized = normalize_text(text)
    return {term for term in re.findall(r"[A-Z0-9]{3,}", normalized)}
