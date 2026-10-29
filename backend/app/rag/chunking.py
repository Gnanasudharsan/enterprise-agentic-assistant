"""Heading-aware chunking.

Sections (Markdown headings) are natural retrieval units, so chunks never span two
sections. Within a section, paragraphs, lists, and tables are packed up to a word
budget; a block that is too large on its own is split by sentences with overlap.
Every chunk keeps its heading path (e.g. "Employee Handbook › Paid time off") so
citations can point to a meaningful location.
"""

import math
import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
SECTION_SEPARATOR = " › "


@dataclass(frozen=True)
class ChunkDraft:
    section: str
    content: str

    @property
    def token_count(self) -> int:
        # ~1.33 tokens per English word: close enough for budgeting without a tokenizer.
        return math.ceil(len(self.content.split()) * 4 / 3)


@dataclass
class _Section:
    path: list[str]
    blocks: list[str]


def _words(text: str) -> int:
    return len(text.split())


def _split_sections(title: str, body: str) -> list[_Section]:
    sections = [_Section(path=[title], blocks=[])]
    stack: list[tuple[int, str]] = []
    current: list[str] = []

    def flush_block() -> None:
        block = "\n".join(current).strip()
        if block:
            sections[-1].blocks.append(block)
        current.clear()

    in_code = False
    for line in body.split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
        heading = None if in_code else _HEADING.match(line)
        if heading:
            flush_block()
            level, text = len(heading.group(1)), heading.group(2).strip()
            if level == 1 and text == title:
                continue  # the document title is already the root of every path
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, text))
            sections.append(_Section(path=[title, *(t for _, t in stack)], blocks=[]))
        elif not line.strip() and not in_code:
            flush_block()
        else:
            current.append(line)
    flush_block()
    return [s for s in sections if s.blocks]


def _split_large_block(block: str, max_words: int, overlap_words: int) -> list[str]:
    sentences = [s for s in _SENTENCE_END.split(block) if s.strip()]
    if len(sentences) == 1:  # no sentence boundaries: fall back to a word window
        words = block.split()
        step = max(max_words - overlap_words, 1)
        return [" ".join(words[i : i + max_words]) for i in range(0, len(words), step)]

    pieces: list[str] = []
    window: list[str] = []
    for sentence in sentences:
        if window and _words(" ".join([*window, sentence])) > max_words:
            pieces.append(" ".join(window))
            # Carry trailing sentences forward as overlap, for context continuity.
            carry: list[str] = []
            for s in reversed(window):
                if _words(" ".join([s, *carry])) > overlap_words:
                    break
                carry.insert(0, s)
            window = carry
        window.append(sentence)
    if window:
        pieces.append(" ".join(window))
    return pieces


def chunk_document(
    title: str,
    body: str,
    *,
    max_words: int = 220,
    overlap_words: int = 40,
    min_words: int = 25,
) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    carry = ""  # a too-small section, prepended to the next one instead of standing alone

    for section in _split_sections(title, body):
        path = SECTION_SEPARATOR.join(section.path)
        blocks: list[str] = []
        for block in section.blocks:
            if _words(block) > max_words:
                blocks.extend(_split_large_block(block, max_words, overlap_words))
            else:
                blocks.append(block)
        if carry:
            blocks.insert(0, carry)
            carry = ""

        packed: list[str] = []
        for block in blocks:
            if packed and _words(packed[-1]) + _words(block) <= max_words:
                packed[-1] = f"{packed[-1]}\n\n{block}"
            else:
                packed.append(block)

        if len(packed) == 1 and _words(packed[0]) < min_words:
            carry = packed[0]
            continue
        drafts.extend(ChunkDraft(section=path, content=p) for p in packed)

    if carry:  # trailing small section with nothing after it
        if drafts and _words(drafts[-1].content) + _words(carry) <= max_words:
            last = drafts.pop()
            drafts.append(ChunkDraft(section=last.section, content=f"{last.content}\n\n{carry}"))
        else:
            drafts.append(ChunkDraft(section=title, content=carry))
    return drafts


def embedding_text(chunk: ChunkDraft) -> str:
    """Text sent to the embedder: the heading path gives the passage its context."""
    return f"{chunk.section}\n\n{chunk.content}" if chunk.section else chunk.content
