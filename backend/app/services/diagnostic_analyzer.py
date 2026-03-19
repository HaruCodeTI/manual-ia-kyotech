"""
Kyotech AI — Diagnóstico Multi-Problema
Detecta perguntas com múltiplos sintomas e decompõe em sub-queries para busca paralela.
"""
from __future__ import annotations

import json
import logging
import re
from typing import List

from app.services.embedder import get_openai_client
from app.core.config import settings

logger = logging.getLogger(__name__)

# Padrões "fracos" — precisam de 2+ matches para ativar
_WEAK_PATTERNS = [
    re.compile(r'\be também\b', re.IGNORECASE),
    re.compile(r'\balém disso\b', re.IGNORECASE),
    re.compile(r'\bao mesmo tempo\b', re.IGNORECASE),
    re.compile(r'\be mais\b', re.IGNORECASE),
    re.compile(r'\btambém\b', re.IGNORECASE),
]

# Padrões "fortes" — ativam sozinhos
_STRONG_PATTERNS = [
    re.compile(r'\b\d+[\.\)]\s+\w.{5,}\b\d+[\.\)]\s*', re.IGNORECASE | re.DOTALL),
    re.compile(r'(?:[^,]{10,},){2,}', re.IGNORECASE),
]

_DECOMPOSE_PROMPT = """You are a technical query decomposer for Fujifilm equipment.
The technician described multiple problems in one message.

Your job: decompose the message into 2–4 independent technical search queries IN ENGLISH.
Each query should be specific and searchable in a Fujifilm service manual.

Respond ONLY with a JSON array of strings, no markdown:
["search query 1", "search query 2"]"""


def is_diagnostic_query(question: str) -> bool:
    """
    Detecta perguntas com múltiplos sintomas via regex (sem LLM).
    Retorna True se:
      - qualquer padrão forte bater, OU
      - 2 ou mais padrões fracos baterem.
    """
    if not question:
        return False
    if any(p.search(question) for p in _STRONG_PATTERNS):
        return True
    weak_count = sum(1 for p in _WEAK_PATTERNS if p.search(question))
    return weak_count >= 2


async def decompose_problems(question: str) -> List[str]:
    """
    Decompõe uma pergunta multi-problema em 2-4 sub-queries em inglês.
    Usa gpt-4o-mini. Fallback para [question] se parse falhar.
    Propaga exceções de rede/timeout — tratadas pelo caller em chat.py.
    """
    client = get_openai_client()
    response = await client.chat.completions.create(
        model=settings.azure_openai_mini_deployment,
        messages=[
            {"role": "system", "content": _DECOMPOSE_PROMPT},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
        max_tokens=200,
    )
    raw = response.choices[0].message.content.strip()
    logger.info(f"Decomposição: '{question}' → {raw}")

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list) or not parsed:
            return [question]
        return [str(q) for q in parsed[:4]]
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Falha no parse da decomposição: {e}. Usando query original.")
        return [question]
