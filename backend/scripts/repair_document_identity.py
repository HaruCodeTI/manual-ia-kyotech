"""
Reparo da identidade de documentos (migration 010).

Contexto: até a migration 010, documents era identificado por
(doc_type, equipment_key) e document_versions tinha chave única
(document_id, published_date). Como published_date cai em date.today() quando
não vem no upload, arquivos distintos enviados no mesmo dia colidiam via
ON CONFLICT e passavam a compartilhar a mesma linha de versão. Os chunks de
todos eles ficaram sob um único source_filename — o do último a gravar.

O script faz três coisas, nesta ordem:

  1. Backfill de documents.doc_key usando exatamente a mesma normalização do
     código de produção (repository.normalize_doc_key).
  2. Identifica versões contaminadas — as que acumulam chunks de mais de um
     arquivo — apaga seus chunks e as próprias versões.
  3. Reingere, a partir dos PDFs originais no Blob Storage, todo blob que ficou
     sem versão correspondente.

Os PDFs originais nunca foram apagados, então nada é recuperado de backup:
a fonte de verdade é o próprio container de originais.

Uso:
    python scripts/repair_document_identity.py --dry-run   # só relata
    python scripts/repair_document_identity.py --apply     # executa
"""
import argparse
import asyncio
import logging
import sys
from datetime import date

sys.path.insert(0, "/app")

from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("repair")

# Silencia o SDK do Azure, que loga cada header de cada request
for noisy in ("azure.core.pipeline.policies.http_logging_policy", "azure.identity", "httpx"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


async def backfill_doc_keys(db, apply: bool) -> int:
    """Preenche documents.doc_key a partir do nome da versão mais recente."""
    from app.services.repository import normalize_doc_key

    rows = (await db.execute(text("""
        SELECT DISTINCT ON (d.id) d.id, dv.source_filename
        FROM documents d
        JOIN document_versions dv ON dv.document_id = d.id
        WHERE d.doc_key IS NULL
        ORDER BY d.id, dv.created_at DESC NULLS LAST
    """))).fetchall()

    # Dois documents podem normalizar para a mesma chave (duplicatas reais).
    # O índice único não deixa ambos ficarem com ela; o segundo recebe um
    # sufixo estável derivado do próprio id para não colidir, e a deduplicação
    # de verdade fica para o fluxo de duplicatas já existente.
    taken: set[str] = set()
    updated = 0
    for doc_id, filename in rows:
        key = normalize_doc_key(filename or str(doc_id))
        if key in taken:
            key = f"{key} #{str(doc_id)[:8]}"
        taken.add(key)
        if apply:
            await db.execute(
                text("UPDATE documents SET doc_key = :k WHERE id = :id"),
                {"k": key, "id": doc_id},
            )
        updated += 1

    logger.info(f"doc_key backfill: {updated} documentos")
    return updated


async def find_contaminated_versions(db) -> list:
    """
    Versões que acumulam chunks de mais de um arquivo.

    Assinatura da contaminação: a chave única uq_chunk é
    (document_version_id, page_number, chunk_index), então dois documentos na
    mesma versão se sobrepõem nas páginas iniciais e a contagem de chunks fica
    incoerente com a numeração de páginas. Usamos o sinal direto e barato:
    versões cujo document_id foi alvo do bug (doc_type preenchido e
    equipment_key nulo) e que têm mais de um arquivo apontando para elas no
    Blob Storage.
    """
    rows = (await db.execute(text("""
        SELECT dv.id, dv.source_filename, dv.storage_path, dv.published_date,
               count(c.id) AS chunks, max(c.page_number) AS max_page
        FROM document_versions dv
        JOIN documents d ON dv.document_id = d.id
        LEFT JOIN chunks c ON c.document_version_id = dv.id
        WHERE d.doc_type IS NOT NULL AND d.equipment_key IS NULL
        GROUP BY dv.id, dv.source_filename, dv.storage_path, dv.published_date
        ORDER BY chunks DESC
    """))).fetchall()
    return rows


async def main(apply: bool) -> None:
    from app.core.database import async_session
    from app.services import storage as storage_mod
    from app.services.ingestion import ingest_document
    from app.services.semantic_cache import invalidate_cache
    from app.core.config import settings

    async with async_session() as db:
        # ── 1. Backfill ──
        await backfill_doc_keys(db, apply)

        # ── 2. Versões contaminadas ──
        contaminated = await find_contaminated_versions(db)
        if not contaminated:
            logger.info("Nenhuma versão contaminada encontrada.")
        for v in contaminated:
            logger.info(
                f"  contaminada: {v[4]:>5} chunks | max_page={v[5]} | {v[1][:60]}"
            )

        victim_ids = [str(v[0]) for v in contaminated]

        # ── 3. Blobs órfãos: os que não têm versão apontando para eles ──
        client = storage_mod.get_blob_client()
        container = settings.azure_storage_container_originals
        loop = asyncio.get_running_loop()
        blobs = await loop.run_in_executor(
            None,
            lambda: [b.name for b in client.get_container_client(container).list_blobs()],
        )
        logger.info(f"Blobs no container de originais: {len(blobs)}")

        known = {
            r[0].split("/", 1)[1] if "/" in r[0] else r[0]
            for r in (await db.execute(text(
                "SELECT storage_path FROM document_versions WHERE storage_path IS NOT NULL"
            ))).fetchall()
        }
        # Blobs cobertos apenas por uma versão contaminada precisam voltar.
        surviving = {
            r[0].split("/", 1)[1] if "/" in r[0] else r[0]
            for r in (await db.execute(text(
                "SELECT storage_path FROM document_versions"
                " WHERE storage_path IS NOT NULL AND id <> ALL(:ids)"
            ), {"ids": victim_ids or ["00000000-0000-0000-0000-000000000000"]})).fetchall()
        }
        to_reingest = sorted(b for b in blobs if b not in surviving)

        logger.info(
            f"Blobs já cobertos por versão íntegra: {len(surviving & set(blobs))} | "
            f"a reingerir: {len(to_reingest)}"
        )
        for b in to_reingest[:20]:
            logger.info(f"  reingerir: {b}")
        if len(to_reingest) > 20:
            logger.info(f"  … e mais {len(to_reingest) - 20}")

        if not apply:
            logger.info("DRY-RUN — nada foi alterado. Use --apply para executar.")
            return

        # ── 4. Apaga chunks e versões contaminadas ──
        if victim_ids:
            deleted = (await db.execute(
                text("DELETE FROM chunks WHERE document_version_id = ANY(:ids)"),
                {"ids": victim_ids},
            )).rowcount
            await db.execute(
                text("DELETE FROM document_versions WHERE id = ANY(:ids)"),
                {"ids": victim_ids},
            )
            await db.commit()
            logger.info(f"Removidos {deleted} chunks de {len(victim_ids)} versões contaminadas")

        # ── 5. Reingestão a partir dos originais ──
        ok = fail = 0
        for name in to_reingest:
            filename = name.rsplit("/", 1)[-1]
            # O storage_path é recomposto por ingest_document como
            # "<equipment_key ou misc>/<published_date>/<filename>". Passando de
            # volta a pasta e a data lidas do próprio blob, a reingestão
            # sobrescreve o mesmo blob em vez de criar uma cópia em
            # misc/<hoje>/ — sem isso o original ficaria órfão e uma segunda
            # execução do reparo reingeriria tudo outra vez.
            parts = name.split("/")
            folder = parts[0] if len(parts) == 3 else None
            try:
                orig_date = date.fromisoformat(parts[1]) if len(parts) == 3 else None
            except ValueError:
                orig_date = None
            try:
                data = await storage_mod.download_blob(f"{container}/{name}")
                result = await ingest_document(
                    db=db, file_bytes=data, filename=filename,
                    equipment_key=None if folder == "misc" else folder,
                    published_date=orig_date,
                )
                if result.success:
                    ok += 1
                else:
                    fail += 1
                    logger.warning(f"  falhou: {filename} — {result.message}")
            except Exception as exc:  # noqa: BLE001 — queremos seguir o lote
                fail += 1
                logger.warning(f"  erro: {filename} — {exc}")

        logger.info(f"Reingestão concluída: {ok} ok, {fail} falhas")

        n = await invalidate_cache(db)
        await db.commit()
        logger.info(f"Cache semântico invalidado: {n} entradas")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = p.parse_args()
    asyncio.run(main(apply=args.apply))
