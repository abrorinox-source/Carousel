from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_EXTENSIONS = {".txt", ".md"}

STOP_WORDS = {
    "and", "the", "with", "from", "this", "that", "what", "when", "where", "why", "how",
    "для", "или", "что", "это", "как", "при", "если", "чем", "так", "все", "ещё", "уже",
    "она", "они", "его", "ему", "мне", "меня", "мои", "мой", "нам", "нас", "вам", "вас",
    "без", "под", "над", "про", "кто", "где", "там", "тут", "вот", "быть", "было",
}


@dataclass(frozen=True)
class RagChunk:
    source: str
    score: int
    text: str


@dataclass(frozen=True)
class RagContext:
    text: str
    chunks: list[RagChunk]

    @property
    def has_context(self) -> bool:
        return bool(self.chunks)


class KeywordRag:
    """Very simple file-based RAG using keyword scoring.

    This is intentionally lightweight for the MVP:
    - reads .txt and .md files from the knowledge folder
    - splits them into chunks
    - scores chunks by query keyword matches
    - returns the best chunks as prompt context
    """

    def __init__(self, knowledge_dir: Path, chunk_size: int = 1800) -> None:
        self.knowledge_dir = knowledge_dir
        self.chunk_size = chunk_size

    def build_context(self, query: str, top_k: int = 5) -> RagContext:
        files = self._knowledge_files()
        if not files:
            return RagContext(text="", chunks=[])

        query_terms = self._tokens(query)
        if not query_terms:
            return RagContext(text="", chunks=[])

        scored_chunks: list[RagChunk] = []

        for file_path in files:
            text = self._read_file(file_path)
            for chunk in self._split_text(text):
                score = self._score_chunk(chunk, query_terms, query)
                if score > 0:
                    scored_chunks.append(
                        RagChunk(
                            source=file_path.name,
                            score=score,
                            text=chunk,
                        )
                    )

        scored_chunks.sort(key=lambda item: item.score, reverse=True)
        best_chunks = scored_chunks[:top_k]

        context_parts = []
        for index, chunk in enumerate(best_chunks, start=1):
            context_parts.append(
                f"[Source {index}: {chunk.source}, score={chunk.score}]\n{chunk.text}"
            )

        return RagContext(
            text="\n\n---\n\n".join(context_parts),
            chunks=best_chunks,
        )

    def _knowledge_files(self) -> list[Path]:
        if not self.knowledge_dir.exists():
            return []

        return sorted(
            file_path
            for file_path in self.knowledge_dir.iterdir()
            if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS
        )

    @staticmethod
    def _read_file(file_path: Path) -> str:
        return file_path.read_text(encoding="utf-8", errors="ignore")

    def _split_text(self, text: str) -> list[str]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        chunks: list[str] = []
        current = ""

        for paragraph in paragraphs:
            if not current:
                current = paragraph
                continue

            if len(current) + len(paragraph) + 2 <= self.chunk_size:
                current = f"{current}\n\n{paragraph}"
            else:
                chunks.append(current.strip())
                current = paragraph

        if current.strip():
            chunks.append(current.strip())

        return chunks

    @staticmethod
    def _tokens(text: str) -> list[str]:
        raw_tokens = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", text.lower())
        return [token for token in raw_tokens if len(token) >= 3 and token not in STOP_WORDS]

    def _score_chunk(self, chunk: str, query_terms: list[str], original_query: str) -> int:
        chunk_lower = chunk.lower()
        score = 0

        for term in query_terms:
            count = chunk_lower.count(term)
            if count:
                score += count

        # Small boost for exact multi-word query pieces.
        query_clean = original_query.strip().lower()
        if len(query_clean) >= 10 and query_clean in chunk_lower:
            score += 10

        return score
