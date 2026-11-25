"""Chunking strategies: recursive, semantic (embeddings), structure-aware, agentic (LLM), page-based."""

from __future__ import annotations

import json
import re
from typing import Callable

import numpy as np

from app.core.logging import get_logger
from app.modules.chunking.base import Chunk, ChunkingStrategy
from app.modules.embeddings.base import EmbeddingProvider
from app.modules.llms.base import LLMProvider

logger = get_logger("chunking")


def _window_split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    size = max(1, chunk_size)
    overlap = max(0, min(chunk_overlap, size - 1))
    step = max(1, size - overlap)
    chunks: list[str] = []
    for i in range(0, len(words), step):
        piece = " ".join(words[i : i + size])
        if piece.strip():
            chunks.append(piece)
        if i + size >= len(words):
            break
    return chunks


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", text.strip())
    return [s.strip() for s in parts if s and s.strip()]


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
    return float(np.dot(a, b) / denom)


def _pack_with_overlap(groups: list[str], chunk_size: int, chunk_overlap: int) -> list[str]:
    """Re-pack oversized groups and apply word overlap between final chunks."""
    packed: list[str] = []
    for group in groups:
        if len(group.split()) <= chunk_size:
            packed.append(group)
        else:
            packed.extend(_window_split(group, chunk_size, chunk_overlap))

    if chunk_overlap <= 0 or len(packed) <= 1:
        return packed

    # Light overlap: prepend tail words from previous chunk
    out: list[str] = [packed[0]]
    for i in range(1, len(packed)):
        prev_words = packed[i - 1].split()
        tail = " ".join(prev_words[-chunk_overlap:]) if prev_words else ""
        cur = packed[i]
        if tail and not cur.startswith(tail):
            out.append(f"{tail} {cur}".strip())
        else:
            out.append(cur)
    return out


class RecursiveChunkingStrategy(ChunkingStrategy):
    name = "recursive"

    def split(
        self,
        text: str,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        pages: list[str] | None = None,
    ) -> list[Chunk]:
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=max(100, chunk_size * 4),
                chunk_overlap=max(0, chunk_overlap * 4),
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            parts = splitter.split_text(text)
        except Exception:
            parts = _window_split(text, chunk_size, chunk_overlap)
        return [Chunk(text=p, index=i, metadata={"strategy": "recursive"}) for i, p in enumerate(parts)]


class SemanticChunkingStrategy(ChunkingStrategy):
    """
    True semantic chunking using the configured embedding model.

    1) Split into sentences
    2) Embed consecutive sentences
    3) Break where cosine similarity drops (topic shift)
    4) Pack to chunk_size with overlap
    """

    name = "semantic"

    def __init__(
        self,
        embedding: EmbeddingProvider | None = None,
        breakpoint_percentile: float = 25.0,
        absolute_threshold: float | None = None,
    ) -> None:
        self.embedding = embedding
        self.breakpoint_percentile = breakpoint_percentile
        self.absolute_threshold = absolute_threshold

    def _resolve_embedding(self) -> EmbeddingProvider:
        if self.embedding is not None:
            return self.embedding
        from app.core.container import get_container

        return get_container().embedding

    def split(
        self,
        text: str,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        pages: list[str] | None = None,
    ) -> list[Chunk]:
        sentences = _split_sentences(text)
        if len(sentences) <= 1:
            return [Chunk(text=text.strip(), index=0, metadata={"strategy": "semantic", "mode": "single"})]

        try:
            emb = self._resolve_embedding()
            vectors = emb.embed_documents(sentences)
            matrix = np.array(vectors, dtype=np.float32)
            if matrix.ndim != 2 or len(matrix) != len(sentences):
                raise ValueError("Embedding provider returned unexpected shape")

            sims: list[float] = []
            for i in range(len(matrix) - 1):
                sims.append(_cosine(matrix[i], matrix[i + 1]))

            if self.absolute_threshold is not None:
                threshold = self.absolute_threshold
            else:
                threshold = float(np.percentile(sims, self.breakpoint_percentile)) if sims else 0.5

            groups: list[list[str]] = [[sentences[0]]]
            breakpoints: list[int] = []
            for i, sim in enumerate(sims):
                # Low similarity => semantic boundary between sentence i and i+1
                if sim < threshold:
                    breakpoints.append(i)
                    groups.append([sentences[i + 1]])
                else:
                    groups[-1].append(sentences[i + 1])

            group_texts = [" ".join(g).strip() for g in groups if g]
            packed = _pack_with_overlap(group_texts, chunk_size, chunk_overlap)
            logger.info(
                "semantic_chunking",
                sentences=len(sentences),
                breakpoints=len(breakpoints),
                threshold=round(threshold, 4),
                chunks=len(packed),
                embedding=getattr(emb, "name", "unknown"),
            )
            return [
                Chunk(
                    text=p,
                    index=i,
                    metadata={
                        "strategy": "semantic",
                        "mode": "embedding_cosine",
                        "embedding_provider": getattr(emb, "name", "unknown"),
                        "similarity_threshold": round(threshold, 4),
                    },
                )
                for i, p in enumerate(packed)
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("semantic_chunking_fallback", error=str(exc))
            # Fallback: sentence packing without embeddings
            parts = _window_split(text, chunk_size, chunk_overlap)
            return [
                Chunk(text=p, index=i, metadata={"strategy": "semantic", "mode": "fallback"})
                for i, p in enumerate(parts)
            ]


class StructureAwareChunkingStrategy(ChunkingStrategy):
    name = "structure_aware"

    def split(
        self,
        text: str,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        pages: list[str] | None = None,
    ) -> list[Chunk]:
        sections = re.split(r"(?m)^(?=\d+\.|#{1,3}\s|[A-Z][A-Z \-/]{6,}$)", text)
        sections = [s.strip() for s in sections if s.strip()]
        out: list[Chunk] = []
        idx = 0
        for section in sections:
            parts = _window_split(section, chunk_size, chunk_overlap) or [section]
            for part in parts:
                heading = section.splitlines()[0][:120] if section.splitlines() else ""
                out.append(
                    Chunk(
                        text=part,
                        index=idx,
                        metadata={"strategy": "structure_aware", "section": heading},
                    )
                )
                idx += 1
        return out


class AgenticChunkingStrategy(ChunkingStrategy):
    """
    True agentic chunking using the configured LLM.

    The LLM proposes topic segment boundaries over numbered sentences.
    Segments are then packed to chunk_size with overlap.
    """

    name = "agentic"

    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm

    def _resolve_llm(self) -> LLMProvider:
        if self.llm is not None:
            return self.llm
        from app.core.container import get_container

        return get_container().llm_for("chunking")

    def _heuristic_fallback(
        self, text: str, chunk_size: int, chunk_overlap: int
    ) -> list[Chunk]:
        cues = [
            r"(?i)\bpurpose\b",
            r"(?i)\bscope\b",
            r"(?i)\bprocedure\b",
            r"(?i)\bexample\b",
            r"(?i)\bout of scope\b",
            r"(?i)\bchecklist\b",
        ]
        pattern = "|".join(cues)
        parts = re.split(f"({pattern})", text)
        merged: list[str] = []
        i = 0
        while i < len(parts):
            if re.fullmatch(pattern, parts[i] or ""):
                block = parts[i]
                if i + 1 < len(parts):
                    block += parts[i + 1]
                    i += 2
                else:
                    i += 1
                merged.append(block.strip())
            else:
                if parts[i].strip():
                    merged.append(parts[i].strip())
                i += 1
        out: list[Chunk] = []
        idx = 0
        for block in merged:
            for piece in _window_split(block, chunk_size, chunk_overlap) or [block]:
                out.append(
                    Chunk(
                        text=piece,
                        index=idx,
                        metadata={"strategy": "agentic", "mode": "heuristic_fallback"},
                    )
                )
                idx += 1
        return out

    def _parse_segments(self, raw: str, sentence_count: int) -> list[dict]:
        """Extract JSON list of {start, end, title} from LLM output."""
        raw = raw.strip()
        # Prefer fenced JSON
        fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, flags=re.DOTALL)
        payload = fence.group(1) if fence else None
        if payload is None:
            match = re.search(r"\[.*\]", raw, flags=re.DOTALL)
            payload = match.group(0) if match else None
        if not payload:
            raise ValueError("LLM did not return a JSON segment list")

        data = json.loads(payload)
        if not isinstance(data, list) or not data:
            raise ValueError("Segment list empty")

        cleaned: list[dict] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            start = int(item.get("start", 0))
            end = int(item.get("end", start))
            start = max(0, min(start, sentence_count - 1))
            end = max(start, min(end, sentence_count - 1))
            cleaned.append(
                {
                    "start": start,
                    "end": end,
                    "title": str(item.get("title") or item.get("topic") or "segment"),
                }
            )
        if not cleaned:
            raise ValueError("No valid segments parsed")
        return cleaned

    def split(
        self,
        text: str,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        pages: list[str] | None = None,
    ) -> list[Chunk]:
        sentences = _split_sentences(text)
        if len(sentences) <= 1:
            return [Chunk(text=text.strip(), index=0, metadata={"strategy": "agentic", "mode": "single"})]

        # Keep prompt bounded for long docs
        max_sentences = 80
        work = sentences[:max_sentences]
        numbered = "\n".join(f"{i}: {s}" for i, s in enumerate(work))

        system = (
            "You are a document segmentation agent for a fictional pharma training knowledge base. "
            "Propose coherent topic segments. Return ONLY valid JSON. "
            "Do not give medical advice."
        )
        prompt = (
            "Split the numbered sentences into topical segments for RAG chunking.\n"
            "Return a JSON array only, where each item is:\n"
            '{"start": <int inclusive>, "end": <int inclusive>, "title": "<short topic>"}\n'
            "Rules:\n"
            "- cover all sentence indexes from 0 to "
            f"{len(work) - 1} without gaps if possible\n"
            "- keep segments coherent and not tiny unless necessary\n"
            "- titles must be short\n\n"
            f"Sentences:\n{numbered}\n"
        )

        try:
            llm = self._resolve_llm()
            resp = llm.generate(prompt, system=system)
            segments = self._parse_segments(resp.content, len(work))

            group_texts: list[str] = []
            titles: list[str] = []
            for seg in segments:
                piece = " ".join(work[seg["start"] : seg["end"] + 1]).strip()
                if piece:
                    group_texts.append(piece)
                    titles.append(seg["title"])

            # Append any leftover sentences beyond the prompt window
            if len(sentences) > max_sentences:
                leftover = " ".join(sentences[max_sentences:]).strip()
                if leftover:
                    group_texts.append(leftover)
                    titles.append("remainder")

            packed = _pack_with_overlap(group_texts, chunk_size, chunk_overlap)
            logger.info(
                "agentic_chunking",
                sentences=len(sentences),
                llm_segments=len(segments),
                chunks=len(packed),
                llm=getattr(llm, "name", "unknown"),
                model=resp.model,
            )
            return [
                Chunk(
                    text=p,
                    index=i,
                    metadata={
                        "strategy": "agentic",
                        "mode": "llm_segments",
                        "llm_provider": getattr(llm, "name", "unknown"),
                        "llm_model": resp.model,
                        "title": titles[i] if i < len(titles) else "",
                    },
                )
                for i, p in enumerate(packed)
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("agentic_chunking_fallback", error=str(exc))
            return self._heuristic_fallback(text, chunk_size, chunk_overlap)


class PageBasedChunkingStrategy(ChunkingStrategy):
    name = "page_based"

    def split(
        self,
        text: str,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        pages: list[str] | None = None,
    ) -> list[Chunk]:
        page_texts = pages if pages else [text]
        out: list[Chunk] = []
        idx = 0
        for page_no, page in enumerate(page_texts, start=1):
            parts = _window_split(page, chunk_size, chunk_overlap) or ([page] if page.strip() else [])
            for part in parts:
                out.append(
                    Chunk(
                        text=part,
                        index=idx,
                        page_number=page_no,
                        metadata={"strategy": "page_based", "page": page_no},
                    )
                )
                idx += 1
        return out


_STRATEGIES: dict[str, Callable[..., ChunkingStrategy]] = {
    "recursive": RecursiveChunkingStrategy,
    "semantic": SemanticChunkingStrategy,
    "structure_aware": StructureAwareChunkingStrategy,
    "agentic": AgenticChunkingStrategy,
    "page_based": PageBasedChunkingStrategy,
}


def get_chunking_strategy(
    name: str,
    *,
    embedding: EmbeddingProvider | None = None,
    llm: LLMProvider | None = None,
) -> ChunkingStrategy:
    key = (name or "recursive").lower().strip()
    if key not in _STRATEGIES:
        raise ValueError(f"Unknown chunk strategy '{name}'. Available: {list(_STRATEGIES)}")

    if key == "semantic":
        return SemanticChunkingStrategy(embedding=embedding)
    if key == "agentic":
        return AgenticChunkingStrategy(llm=llm)
    return _STRATEGIES[key]()


def list_chunking_strategies() -> list[str]:
    return sorted(_STRATEGIES.keys())
