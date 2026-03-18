"""
Kyotech AI — Aplicação Principal
"""
from __future__ import annotations

import logging
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from scalar_fastapi import get_scalar_api_reference
from sqlalchemy import text

from app.api.upload import router as upload_router
from app.api.chat import router as chat_router
from app.api.sessions import router as sessions_router
from app.api.viewer import router as viewer_router
from app.core.database import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-30s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent / "migrations"


async def run_migrations() -> None:
    """Executa todos os arquivos .sql em migrations/ em ordem alfabética."""
    if not MIGRATIONS_DIR.exists():
        logger.warning("Diretório de migrations não encontrado: %s", MIGRATIONS_DIR)
        return

    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        logger.info("Nenhuma migration encontrada.")
        return

    async with engine.begin() as conn:
        for sql_file in sql_files:
            logger.info("Executando migration: %s", sql_file.name)
            sql = sql_file.read_text()
            await conn.execute(text(sql))
            logger.info("Migration concluída: %s", sql_file.name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_migrations()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Kyotech AI",
    description="Sistema RAG interno para consulta de manuais e informativos Fujifilm",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:5173",
        "https://kyotech-frontend.redmeadow-72ffb9e6.canadacentral.azurecontainerapps.io",
        "https://kyotech-ai.harucode.com.br",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(sessions_router, prefix="/api/v1")
app.include_router(viewer_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "kyotech-ai"}


@app.get("/docs", include_in_schema=False)
async def scalar_docs():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title="Kyotech AI — API Docs",
    )
