"""
Kyotech AI — Query Rewriting
Conforme Seção 7: reescreve consulta do técnico (PT) para inglês técnico,
melhorando a busca contra manuais em inglês da Fujifilm.

Usa gpt-4o-mini (barato e rápido) para:
1. Traduzir PT → EN
2. Expandir termos técnicos
3. Classificar se é Manual ou Informativo
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from app.services.embedder import get_openai_client
from app.core.config import settings

logger = logging.getLogger(__name__)

REWRITE_PROMPT = """You are a technical assistant for Fujifilm printing equipment.
Your job is to rewrite a technician's question (in Portuguese) into an optimized English search query.

Rules:
1. Translate to English
2. Use technical terms that would appear in Fujifilm service manuals
3. Keep the query focused and specific (max 2-3 sentences)
4. Classify the query as "manual" (procedures, specs, parts) or "informativo" (bulletins, updates, known issues)
5. If the question mentions a specific equipment model, extract it

Respond ONLY with this JSON format, no markdown:
{"query_en": "...", "doc_type": "manual" or "informativo" or "both", "equipment_hint": "model name or null"}"""


@dataclass
class RewrittenQuery:
    original: str
    query_en: str
    doc_type: Optional[str]  # "manual", "informativo", or "both"
    equipment_hint: Optional[str]


async def rewrite_query(question: str) -> RewrittenQuery:
    """
    Reescreve a pergunta do técnico para busca otimizada.
    
    Input: "Como trocar o rolo de pressão da Frontier 780?"
    Output: RewrittenQuery(
        query_en="How to replace pressure roller Frontier 780",
        doc_type="manual",
        equipment_hint="frontier-780"
    )
    """
    client = get_openai_client()

    response = await client.chat.completions.create(
        model=settings.azure_openai_mini_deployment,
        messages=[
            {"role": "system", "content": REWRITE_PROMPT},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
        max_tokens=200,
    )

    raw = response.choices[0].message.content.strip()
    logger.info(f"Query rewrite: '{question}' → {raw}")

    try:
        parsed = json.loads(raw)
        doc_type = parsed.get("doc_type")
        if doc_type == "both":
            doc_type = None  # busca em todos

        equipment = parsed.get("equipment_hint")
        if equipment and equipment.lower() in ("null", "none", ""):
            equipment = None
        if equipment:
            equipment = equipment.lower().replace(" ", "-")

        return RewrittenQuery(
            original=question,
            query_en=parsed.get("query_en", question),
            doc_type=doc_type,
            equipment_hint=equipment,
        )
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Falha no parse do rewrite, usando query original: {e}")
        return RewrittenQuery(
            original=question,
            query_en=question,
            doc_type=None,
            equipment_hint=None,
        )
