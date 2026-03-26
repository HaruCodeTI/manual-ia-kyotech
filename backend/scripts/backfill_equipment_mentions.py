"""
Kyotech AI — Backfill de equipment_mentions para chunks existentes.

Uso:
    cd backend
    python scripts/backfill_equipment_mentions.py

Idempotente: pode ser rodado múltiplas vezes sem efeito colateral.
Processa apenas chunks onde equipment_mentions = '[]'.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.core.database import async_session
from app.services.equipment_detector import build_equipment_patterns, detect_equipment_mentions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def run_backfill() -> None:
    async with async_session() as db:
        eq_result = await db.execute(
            text("SELECT equipment_key, aliases FROM equipments ORDER BY equipment_key")
        )
        equipment_list = [(row[0], row[1] or []) for row in eq_result.fetchall()]

        if not equipment_list:
            logger.warning("Nenhum equipamento cadastrado. Backfill não tem o que fazer.")
            return

        patterns = build_equipment_patterns(equipment_list)
        logger.info(f"{len(equipment_list)} equipamentos carregados para detecção.")

        chunk_result = await db.execute(
            text("SELECT id, content FROM chunks WHERE equipment_mentions = '[]'::jsonb")
        )
        chunks = chunk_result.fetchall()

        if not chunks:
            logger.info("Nenhum chunk com equipment_mentions vazio. Backfill já completo.")
            return

        logger.info(f"{len(chunks)} chunks para processar.")

        updated = 0
        for i, (chunk_id, content) in enumerate(chunks, 1):
            mentions = detect_equipment_mentions(content or "", patterns)
            if mentions:
                await db.execute(
                    text("UPDATE chunks SET equipment_mentions = :m WHERE id = :id"),
                    {"m": json.dumps(mentions), "id": str(chunk_id)},
                )
                updated += 1

            if i % 50 == 0:
                logger.info(f"  Progresso: {i}/{len(chunks)} chunks processados...")

        await db.commit()
        logger.info(
            f"Backfill concluído: {len(chunks)} processados, "
            f"{updated} atualizados com equipamentos detectados."
        )


if __name__ == "__main__":
    asyncio.run(run_backfill())
