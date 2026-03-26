"""
Script de amostragem: extrai trechos dos documentos reais para formular perguntas de teste.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text

DOCS = [
    "%720Series%",
    "%Endoscope System Training%",
]

async def main():
    from app.core.database import async_session

    async with async_session() as db:
        for pattern in DOCS:
            r = await db.execute(
                text("""
                    SELECT cv.source_filename, c.page_number, c.content
                    FROM chunks c
                    JOIN current_versions cv ON c.document_version_id = cv.id
                    WHERE cv.source_filename ILIKE :pat
                    ORDER BY c.page_number ASC
                    LIMIT 15
                """),
                {"pat": pattern},
            )
            rows = r.fetchall()
            if not rows:
                print(f"\n[SEM RESULTADOS para {pattern}]")
                continue
            print(f"\n{'='*70}")
            print(f"DOCUMENTO: {rows[0][0]}")
            print(f"{'='*70}")
            for filename, page, content in rows:
                print(f"\n--- Página {page} ---")
                print(content[:500])


asyncio.run(main())
