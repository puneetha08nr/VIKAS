import asyncio
from typing import Any

from openai import AsyncOpenAI

_MODEL = "text-embedding-3-small"
_DIMS = 1536
_BATCH_SIZE = 100


class EmbeddingGenerator:

    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self._client = client or AsyncOpenAI()

    async def generate(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, batching in groups of 100."""
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i : i + _BATCH_SIZE]
            response = await self._client.embeddings.create(
                model=_MODEL,
                input=batch,
                dimensions=_DIMS,
            )
            # API returns items sorted by index
            batch_embeddings = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def generate_one(self, text: str) -> list[float]:
        """Embed a single string."""
        results = await self.generate([text])
        return results[0]
