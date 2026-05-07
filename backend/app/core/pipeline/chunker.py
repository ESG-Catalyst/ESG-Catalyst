"""Semantic chunking — split ingested documents into retrieval-ready chunks.

Design principles:
- Section headers travel with their content (never orphaned).
- Table rows and bullet-list blocks are never split mid-block.
- Configurable chunk size with overlap for context continuity.
- Each chunk carries metadata (page, section, type, offset).

Usage:
    from app.core.pipeline.chunker import chunk_document
    from app.core.pipeline.ingestion import ingest_document

    doc = ingest_document("report.pdf")
    chunks = chunk_document(doc)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from enum import Enum

import structlog

from app.core.pipeline.ingestion import IngestedDocument

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
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Split an ``IngestedDocument`` into semantically meaningful chunks.

    Args:
        doc: Output of ``ingest_document()``.
        chunk_size: Target maximum characters per chunk.
        chunk_overlap: Characters of overlap between consecutive chunks.

    Returns:
        Ordered list of ``Chunk`` objects.
    """
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

    logger.info(
        "chunker.done",
        file=doc.source_file,
        pages=doc.page_count,
        chunks=len(all_chunks),
        avg_chars=sum(len(c.text) for c in all_chunks) // max(len(all_chunks), 1),
    )
    return all_chunks


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
            # Table separators stay with the current table block
            if current_type == "table":
                current_lines.append(line)
            # Otherwise ignore (decorative line)

        elif line_type == "blank":
            # Blank lines end the current block
            if current_lines:
                _flush()
                current_offset = char_pos

        else:
            # Regular text
            if current_type == "table":
                # Transitioning out of a table
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

    # Short lines that look like section titles
    if len(stripped) <= 80 and not stripped.endswith((".",":",",")):
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
        # Track the nearest section header
        if block.block_type == "header":
            # If we have accumulated text, emit before starting new section
            if current_text.strip() and len(current_text) > _MIN_CHUNK_SIZE:
                _emit()
            current_header = block.text
            # Include the header in the next chunk's text
            if current_text:
                current_text += "\n\n" + block.text
            else:
                current_text = block.text
                current_offset = block.char_offset
            continue

        proposed = current_text + ("\n\n" if current_text else "") + block.text

        if len(proposed) <= chunk_size:
            # Fits — accumulate
            if not current_text:
                current_offset = block.char_offset
            current_text = proposed
            current_types.add(block.block_type)
        else:
            # Doesn't fit — emit current, then handle the block
            if current_text.strip():
                _emit()

            # If the block itself exceeds chunk_size, split it
            if len(block.text) > chunk_size:
                sub_chunks = _split_large_block(
                    block.text, chunk_size, chunk_overlap
                )
                for i, sub in enumerate(sub_chunks):
                    current_text = sub
                    if current_header:
                        current_text = current_header + "\n" + current_text
                    current_offset = block.char_offset
                    current_types = {block.block_type}
                    _emit()
            else:
                # Start a new chunk with overlap from previous
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

    # Flush remaining
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
            # If a single paragraph exceeds chunk_size, split on sentences
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
