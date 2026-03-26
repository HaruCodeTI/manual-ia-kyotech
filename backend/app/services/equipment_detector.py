"""
Kyotech AI — Detecção de equipamentos em chunks via regex.
Busca equipment_keys e aliases da tabela equipments no conteúdo dos chunks.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Pattern, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def build_equipment_patterns(
    equipment_list: List[Tuple[str, List]],
) -> Dict[str, Pattern]:
    """
    Compila um dict {equipment_key: regex_pattern} a partir da lista de equipamentos.
    Cada pattern verifica o key + todos os aliases, case-insensitive, com word boundary.
    """
    patterns: Dict[str, Pattern] = {}
    for equipment_key, aliases in equipment_list:
        terms = [equipment_key]
        if aliases:
            terms.extend(str(a) for a in aliases if a)
        terms_sorted = sorted(set(terms), key=len, reverse=True)
        escaped = [re.escape(t) for t in terms_sorted]
        pattern_str = r"(?<![A-Za-z0-9])(?:" + "|".join(escaped) + r")(?![A-Za-z0-9])"
        patterns[equipment_key] = re.compile(pattern_str, re.IGNORECASE)
    return patterns


def detect_equipment_mentions(
    content: str,
    patterns: Dict[str, Pattern],
) -> List[str]:
    """
    Retorna lista deduplicada de equipment_keys encontrados no conteúdo.
    Puro CPU — sem I/O.
    """
    found = []
    for equipment_key, pattern in patterns.items():
        if pattern.search(content):
            found.append(equipment_key)
    return found


async def detect_mentions_for_version(
    db: AsyncSession,
    version_id: str,
) -> int:
    """
    Para todos os chunks de uma versão, detecta equipamentos mencionados
    e atualiza o campo equipment_mentions no banco.
    Retorna o número de chunks atualizados.
    """
    eq_result = await db.execute(
        text("SELECT equipment_key, aliases FROM equipments ORDER BY equipment_key")
    )
    equipment_list = [(row[0], row[1] or []) for row in eq_result.fetchall()]

    if not equipment_list:
        logger.info("Nenhum equipamento cadastrado — detecção ignorada.")
        return 0

    patterns = build_equipment_patterns(equipment_list)

    chunk_result = await db.execute(
        text("SELECT id, content FROM chunks WHERE document_version_id = :vid"),
        {"vid": version_id},
    )
    chunks = chunk_result.fetchall()

    if not chunks:
        return 0

    updated = 0
    for chunk_id, content in chunks:
        mentions = detect_equipment_mentions(content or "", patterns)
        await db.execute(
            text("UPDATE chunks SET equipment_mentions = :mentions WHERE id = :id"),
            {"mentions": json.dumps(mentions), "id": str(chunk_id)},
        )
        if mentions:
            updated += 1

    await db.commit()
    logger.info(
        f"Detecção concluída para versão {version_id}: "
        f"{len(chunks)} chunks processados, {updated} com equipamentos detectados."
    )
    return updated
