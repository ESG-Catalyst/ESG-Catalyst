"""Chunking strategies — split ingested documents into retrieval-ready chunks.

Two strategies are available, selected by ``settings.chunk_strategy``:

  ``sentence_window`` *(default — A2 tuning winner)*
      Per-page, 3-sentence window with stride 1 and a 1500-char hard cap.
      Best ESG-relevance recall and lowest noise ratio on the Beltone PDF
      under the post-C3 3-voter ensemble classifier
      (see ``scripts/experiments/results/chunking_tuning.json``).

  ``block_merge`` *(legacy)*
      Original header/table-aware regex blocker that merges small blocks
      and splits oversized ones with overlap. Retained for A/B tests.

The public interface is unchanged:

    from app.core.nlp.chunker import chunk_document
    chunks = chunk_document(doc)   # uses settings.chunk_strategy

Design principles still honoured by both strategies:
- Section headers travel with their content (never orphaned).
- Table rows and bullet-list blocks are never split mid-block.
- Each chunk carries metadata (page, section, type, offset).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from enum import Enum

import structlog

from app.config import settings
from app.core.ingestion.parser import IngestedDocument

logger = structlog.get_logger(__name__)

# ── Defaults ─────────────────────────────────────────────────────────────
_DEFAULT_CHUNK_SIZE = 2000       # chars (~500 tokens)
_DEFAULT_CHUNK_OVERLAP = 200     # chars carried into next chunk
_MIN_CHUNK_SIZE = 80             # discard anything smaller


# ── Header / table detection patterns ────────────────────────────────────
_HEADER_RE = re.compile(
    r"^("
    r"(?:GRI\s+\d[\d\-\.]*\b.*)"          # "GRI 302-1 …"
    r"|(?:FRA[\-\s]\d+\b.*)"              # "FRA-36 …"
    r"|(?:[A-Z][A-Za-z\s,&\-\(\)]{3,80})$"  # Title-case line ≤80 chars
    r"|(?:[A-Z\s\-&]{4,80})$"             # ALL-CAPS line
    r")",
    re.MULTILINE,
)

_TABLE_LINE_RE = re.compile(r".*\|.*\|")            # lines with pipe separators
_SEPARATOR_LINE_RE = re.compile(r"^[\-=]{4,}\s*$")  # "----" or "===="
_BULLET_RE = re.compile(r"^\s*[-•●▪]\s+")           # bullet list items


# ── Public data class ────────────────────────────────────────────────────
class ChunkType(str, Enum):
    text = "text"
    table = "table"
    mixed = "mixed"


@dataclass
class Chunk:
    """A single chunk of document text with provenance metadata."""

    chunk_id: str
    text: str
    page_number: int
    section_header: str | None
    chunk_type: str            # "text" | "table" | "mixed"
    source_file: str
    char_offset: int           # offset within the page text

    @property
    def token_estimate(self) -> int:
        """Rough token count (~3 chars/token for mixed Arabic+English)."""
        return len(self.text) // 3


# ── Internal block representation ────────────────────────────────────────
@dataclass
class _Block:
    text: str
    block_type: str            # "header", "table", "text"
    char_offset: int


# ── Public API ───────────────────────────────────────────────────────────
def chunk_document(
    doc: IngestedDocument,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    strategy: str | None = None,
) -> list[Chunk]:
    """Split an ``IngestedDocument`` into semantically meaningful chunks.

    The active strategy comes from ``settings.chunk_strategy`` unless
    overridden by the ``strategy`` argument — explicit kwarg wins for
    A/B testing and for the comparison scripts under ``scripts/experiments/``.

    Args:
        doc: Output of ``ingest_document()``.
        chunk_size: ``block_merge`` only — target max characters per chunk.
            Defaults to ``settings.chunk_size_chars``.
        chunk_overlap: ``block_merge`` only — characters of overlap between
            consecutive chunks. Defaults to ``settings.chunk_overlap_chars``.
        strategy: Override ``settings.chunk_strategy`` for one call.
            One of ``"sentence_window"`` (default) or ``"block_merge"``.

    Returns:
        Ordered list of ``Chunk`` objects.
    """
    active = (strategy or settings.chunk_strategy).lower()

    if active == "sentence_window":
        chunks = _chunk_sentence_window(
            doc,
            window=settings.chunk_window_sentences,
            stride=settings.chunk_stride_sentences,
            max_chars=settings.chunk_max_chars,
        )
    elif active == "block_merge":
        chunks = _chunk_block_merge(
            doc,
            chunk_size=chunk_size if chunk_size is not None else settings.chunk_size_chars,
            chunk_overlap=chunk_overlap if chunk_overlap is not None else settings.chunk_overlap_chars,
        )
    else:
        raise ValueError(
            f"Unknown chunk_strategy={active!r}. "
            f"Valid: 'sentence_window' | 'block_merge'."
        )

    logger.info(
        "chunker.done",
        strategy=active,
        file=doc.source_file,
        pages=doc.page_count,
        chunks=len(chunks),
        avg_chars=sum(len(c.text) for c in chunks) // max(len(chunks), 1),
    )
    return chunks


# ── Strategy: block_merge (legacy — original chunker logic) ─────────────
def _chunk_block_merge(
    doc: IngestedDocument,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    """Header/table-aware regex blocker + size-bounded merge with overlap."""
    all_chunks: list[Chunk] = []

    for page in doc.pages:
        blocks = _parse_blocks(page.text)
        page_chunks = _merge_blocks_into_chunks(
            blocks=blocks,
            page_number=page.page_number,
            source_file=doc.source_file,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        all_chunks.extend(page_chunks)

    # Drop tiny chunks (footers, page numbers, etc.)
    all_chunks = [c for c in all_chunks if len(c.text.strip()) >= _MIN_CHUNK_SIZE]
    return all_chunks


# ── Strategy: sentence_window (A2 tuning winner) ────────────────────────
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z؀-ۿ])")


def _split_sentences(text: str) -> list[str]:
    """Sentence splitter that's safe for English + Arabic-script starts."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    parts = _SENT_SPLIT_RE.split(cleaned)
    return [p.strip() for p in parts if p.strip()]


def _nearest_header_above(text: str) -> str | None:
    """Return the most recent header-shaped line at the start of ``text``.

    Used so sentence-window chunks still carry the section_header metadata
    that retrieval / report rendering relies on.
    """
    for line in text.split("\n")[:6]:
        s = line.strip()
        if not s or len(s) > 80:
            continue
        if _HEADER_RE.match(s):
            return s
    return None


def _chunk_sentence_window(
    doc: IngestedDocument,
    window: int,
    stride: int,
    max_chars: int,
) -> list[Chunk]:
    """Per-page sentence window with a hard char cap.

    Long single sentences (run-on table rows) are sub-split on sentence
    boundaries inside the window — this is the knob that brings the long
    tail of >512-token chunks from ~6% (A1 winner) down to ~1% (A2 winner).
    """
    chunks: list[Chunk] = []

    for page in doc.pages:
        page_header = _nearest_header_above(page.text)
        sents = _split_sentences(page.text)
        if not sents:
            continue

        i = 0
        while i < len(sents):
            window_sents = sents[i : i + window]
            text = " ".join(window_sents).strip()

            if len(text) > max_chars:
                # Sub-pack sentences into multiple chunks under the cap.
                acc = ""
                for s in window_sents:
                    candidate = (acc + " " + s).strip() if acc else s
                    if len(candidate) > max_chars and acc:
                        chunks.append(_emit_sentence_chunk(
                            acc, page.page_number, page_header, doc.source_file,
                        ))
                        acc = s
                    else:
                        acc = candidate
                if acc:
                    chunks.append(_emit_sentence_chunk(
                        acc, page.page_number, page_header, doc.source_file,
                    ))
            else:
                if text:
                    chunks.append(_emit_sentence_chunk(
                        text, page.page_number, page_header, doc.source_file,
                    ))

            if i + window >= len(sents):
                break
            i += stride

    return chunks


def _emit_sentence_chunk(
    text: str,
    page_number: int,
    section_header: str | None,
    source_file: str,
) -> Chunk:
    """Construct a Chunk from a sentence-window slice."""
    return Chunk(
        chunk_id=uuid.uuid4().hex,
        text=text,
        page_number=page_number,
        section_header=section_header,
        chunk_type=ChunkType.text,
        source_file=source_file,
        char_offset=0,
    )


# ── Step 1: Parse page text into typed blocks ────────────────────────────
def _parse_blocks(text: str) -> list[_Block]:
    """Split page text into header / table / text blocks."""
    lines = text.split("\n")
    blocks: list[_Block] = []
    current_lines: list[str] = []
    current_type: str = "text"
    current_offset: int = 0
    char_pos: int = 0

    def _flush():
        nonlocal current_lines, current_type, current_offset
        if current_lines:
            block_text = "\n".join(current_lines).strip()
            if block_text:
                blocks.append(_Block(text=block_text, block_type=current_type, char_offset=current_offset))
        current_lines = []
        current_type = "text"

    for line in lines:
        line_type = _classify_line(line)

        if line_type == "header":
            _flush()
            current_offset = char_pos
            blocks.append(_Block(text=line.strip(), block_type="header", char_offset=char_pos))

        elif line_type == "table":
            if current_type != "table":
                _flush()
                current_offset = char_pos
                current_type = "table"
            current_lines.append(line)

        elif line_type == "separator":
            if current_type == "table":
                current_lines.append(line)

        elif line_type == "blank":
            if current_lines:
                _flush()
                current_offset = char_pos

        else:
            if current_type == "table":
                _flush()
                current_offset = char_pos
            if not current_lines:
                current_offset = char_pos
            current_type = "text"
            current_lines.append(line)

        char_pos += len(line) + 1  # +1 for newline

    _flush()
    return blocks


def _classify_line(line: str) -> str:
    """Classify a single line as header / table / separator / blank / text."""
    stripped = line.strip()

    if not stripped:
        return "blank"

    if _SEPARATOR_LINE_RE.match(stripped):
        return "separator"

    if _TABLE_LINE_RE.match(stripped):
        return "table"

    if len(stripped) <= 80 and not stripped.endswith((".", ":", ",")):
        if _HEADER_RE.match(stripped):
            return "header"

    return "text"


# ── Step 2: Merge blocks into sized chunks ───────────────────────────────
def _merge_blocks_into_chunks(
    blocks: list[_Block],
    page_number: int,
    source_file: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    """Merge small blocks, split large ones, and apply overlap."""
    if not blocks:
        return []

    chunks: list[Chunk] = []
    current_text = ""
    current_header: str | None = None
    current_offset = 0
    current_types: set[str] = set()

    def _emit():
        nonlocal current_text, current_types, current_offset
        if current_text.strip():
            ctype = _resolve_chunk_type(current_types)
            chunks.append(Chunk(
                chunk_id=uuid.uuid4().hex,
                text=current_text.strip(),
                page_number=page_number,
                section_header=current_header,
                chunk_type=ctype,
                source_file=source_file,
                char_offset=current_offset,
            ))
        current_text = ""
        current_types = set()

    for block in blocks:
        if block.block_type == "header":
            if current_text.strip() and len(current_text) > _MIN_CHUNK_SIZE:
                _emit()
            current_header = block.text
            if current_text:
                current_text += "\n\n" + block.text
            else:
                current_text = block.text
                current_offset = block.char_offset
            continue

        proposed = current_text + ("\n\n" if current_text else "") + block.text

        if len(proposed) <= chunk_size:
            if not current_text:
                current_offset = block.char_offset
            current_text = proposed
            current_types.add(block.block_type)
        else:
            if current_text.strip():
                _emit()

            if len(block.text) > chunk_size:
                sub_chunks = _split_large_block(block.text, chunk_size, chunk_overlap)
                for sub in sub_chunks:
                    current_text = sub
                    if current_header:
                        current_text = current_header + "\n" + current_text
                    current_offset = block.char_offset
                    current_types = {block.block_type}
                    _emit()
            else:
                overlap_text = ""
                if chunks and chunk_overlap > 0:
                    prev = chunks[-1].text
                    overlap_text = prev[-chunk_overlap:].lstrip()

                current_offset = block.char_offset
                if overlap_text:
                    current_text = overlap_text + "\n\n" + block.text
                else:
                    current_text = block.text
                current_types = {block.block_type}

    _emit()
    return chunks


def _split_large_block(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split an oversized block at paragraph or sentence boundaries."""
    paragraphs = re.split(r"\n\n+", text)
    result: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_size:
            current = (current + "\n\n" + para) if current else para
        else:
            if current:
                result.append(current)
            if len(para) > chunk_size:
                sentences = re.split(r"(?<=[.!?])\s+", para)
                current = ""
                for sent in sentences:
                    if len(current) + len(sent) + 1 <= chunk_size:
                        current = (current + " " + sent) if current else sent
                    else:
                        if current:
                            result.append(current)
                        current = sent
            else:
                current = para

    if current:
        result.append(current)

    return result


def _resolve_chunk_type(types: set[str]) -> str:
    """Determine chunk type from the block types it contains."""
    types.discard("header")
    if not types:
        return ChunkType.text
    if types == {"table"}:
        return ChunkType.table
    if types == {"text"}:
        return ChunkType.text
    return ChunkType.mixed
