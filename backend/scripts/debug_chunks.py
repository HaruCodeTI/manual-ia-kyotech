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

        # Busca chunks sobre cola/adesivo no manual 720
        print("\n=== Chunks do manual 720 sobre cola/adhesive ===")
        r2 = await db.execute(
            text("""
                SELECT cv.source_filename, c.page_number,
                       LEFT(c.content, 300) AS snippet
                FROM chunks c
                JOIN current_versions cv ON c.document_version_id = cv.id
                WHERE cv.source_filename ILIKE '%720%'
                  AND (c.content ILIKE '%adhesive%' OR c.content ILIKE '%glue%'
                       OR c.content ILIKE '%cola%' OR c.content ILIKE '%bond%'
                       OR c.content ILIKE '%lens%' OR c.content ILIKE '%light guide%')
                LIMIT 10
            """)
        )
        rows2 = r2.fetchall()
        if rows2:
            for row in rows2:
                print(f"file={row[0]} | page={row[1]}")
                print(f"  snippet: {row[2]}")
                print()
        else:
            print("Nenhum chunk do manual 720 menciona adhesive/lens/light guide.")

        # Mostra os primeiros chunks do manual 720
        print("\n=== Primeiros chunks do manual 720 (primeiras páginas) ===")
        r3 = await db.execute(
            text("""
                SELECT c.page_number, LEFT(c.content, 200) AS snippet
                FROM chunks c
                JOIN current_versions cv ON c.document_version_id = cv.id
                WHERE cv.source_filename ILIKE '%720%'
                ORDER BY c.page_number ASC
                LIMIT 5
            """)
        )
        for row in r3.fetchall():
            print(f"page={row[0]}: {row[1]}")
            print()


asyncio.run(main())
