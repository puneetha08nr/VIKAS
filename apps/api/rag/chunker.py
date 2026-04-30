from typing import Any

import tiktoken

_ENCODING = tiktoken.get_encoding("cl100k_base")

_CHUNK_SIZE = 512   # tokens
_OVERLAP = 50       # tokens


class TextChunker:

    def chunk(
        self,
        text: str,
        source_doc: str,
        strategy: str = "fixed",
    ) -> list[dict[str, Any]]:
        if strategy == "fixed":
            return self._fixed(text, source_doc)
        raise ValueError(f"Unknown chunking strategy: {strategy!r}")

    # ── Fixed-size chunking ───────────────────────────────────────────────────

    def _fixed(self, text: str, source_doc: str) -> list[dict[str, Any]]:
        tokens = _ENCODING.encode(text)
        if not tokens:
            return []

        chunks: list[dict[str, Any]] = []
        start = 0
        chunk_index = 0

        while start < len(tokens):
            end = min(start + _CHUNK_SIZE, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = _ENCODING.decode(chunk_tokens)

            chunks.append({
                "text": chunk_text,
                "source_doc": source_doc,
                "chunk_index": chunk_index,
                "metadata": {
                    "token_count": len(chunk_tokens),
                    "start_token": start,
                    "end_token": end,
                    "strategy": "fixed",
                },
            })

            chunk_index += 1
            next_start = start + _CHUNK_SIZE - _OVERLAP
            # Stop if we can't advance (last chunk is smaller than overlap)
            if next_start <= start:
                break
            start = next_start

        return chunks
