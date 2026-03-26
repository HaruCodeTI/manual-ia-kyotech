"""
Script de diagnóstico: lista documentos com poucos/nenhum chunk e busca por EC-720.
"""
import asyncio
import sys
import os

sys.path.insert(0, "/app")

from sqlalchemy import text


async def main():
    from app.core.database import async_session

    async with async_session() as db:
        # Documentos ordenados por qtd de chunks (do menor para o maior)
        r = await db.execute(
            text("""
                SELECT d.doc_type, d.equipment_key, cv.source_filename,
                       (SELECT COUNT(*) FROM chunks c WHERE c.document_version_id = cv.id) AS chunk_count
                FROM documents d
                JOIN current_versions cv ON cv.document_id = d.id
                ORDER BY chunk_count ASC
            """)
        )
        rows = r.fetchall()
        print("=== Documentos por qtd de chunks ===")
        for row in rows:
            print(f"chunks={row[3]:4d} | type={row[0]} | equip={row[1]} | file={row[2]}")

        # Busca chunks que mencionam EC-720
        print("\n=== Chunks mencionando EC-720 ===")
        r2 = await db.execute(
            text("""
                SELECT cv.source_filename, c.page_number,
                       LEFT(c.content, 200) AS snippet
                FROM chunks c
                JOIN current_versions cv ON c.document_version_id = cv.id
                WHERE c.content ILIKE '%EC-720%' OR c.content ILIKE '%720R%' OR c.content ILIKE '%720L%'
                LIMIT 10
            """)
        )
        rows2 = r2.fetchall()
        if rows2:
            for row in rows2:
                print(f"file={row[0]} | page={row[1]}")
                print(f"  snippet: {row[2]}")
        else:
            print("Nenhum chunk menciona EC-720 — documento pode não ter sido indexado.")


asyncio.run(main())
