"""
Kyotech AI — Serviço de Embeddings
"""
from __future__ import annotations

import logging
from typing import List, Optional

from openai import AsyncAzureOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncAzureOpenAI] = None


def get_openai_client() -> AsyncAzureOpenAI:
    global _client
    if _client is None:
        _client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            timeout=90.0,
            max_retries=2,
        )
    return _client


async def generate_embeddings(texts: List[str], batch_size: int = 50) -> List[List[float]]:
    client = get_openai_client()
    all_embeddings: List[List[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        logger.info(f"Gerando embeddings: lote {i // batch_size + 1} ({len(batch)} textos)")

        response = await client.embeddings.create(
            input=batch,
            model=settings.azure_openai_embedding_deployment,
        )

        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

    logger.info(f"Total de embeddings gerados: {len(all_embeddings)}")
    return all_embeddings


async def generate_single_embedding(text: str) -> List[float]:
    client = get_openai_client()
    response = await client.embeddings.create(
        input=[text],
        model=settings.azure_openai_embedding_deployment,
    )
    return response.data[0].embedding
