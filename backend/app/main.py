"""
Kyotech AI — Aplicação Principal
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.upload import router as upload_router
from app.api.chat import router as chat_router
from app.api.sessions import router as sessions_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-30s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(
    title="Kyotech AI",
    description="Sistema RAG interno para consulta de manuais e informativos Fujifilm",
    version="0.1.0",
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
        "https://kyotech-frontend.redmeadow-72ffb9e6.canadacentral.azurecontainerapps.io"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(sessions_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "kyotech-ai"}
