"""
Kyotech AI — Testes de integração da API de Upload
"""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.anyio
async def test_upload_document_success(async_client, sample_pdf_bytes):
    from app.services.ingestion import IngestionResult

    mock_result = IngestionResult(
        success=True,
        message="Documento ingerido com sucesso.",
        document_id="doc-123",
        version_id="ver-456",
        total_pages=2,
        total_chunks=10,
        was_duplicate=False,
    )

    with patch("app.api.upload.ingest_document", new_callable=AsyncMock, return_value=mock_result):
        resp = await async_client.post(
            "/api/v1/upload/document",
            files={"file": ("manual.pdf", sample_pdf_bytes, "application/pdf")},
            data={
                "equipment_key": "frontier-780",
                "doc_type": "manual",
                "published_date": "2025-01-15",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["document_id"] == "doc-123"
    assert data["version_id"] == "ver-456"
    assert data["total_pages"] == 2
    assert data["total_chunks"] == 10


@pytest.mark.anyio
async def test_upload_rejects_non_pdf(async_client):
    resp = await async_client.post(
        "/api/v1/upload/document",
        files={"file": ("readme.txt", b"hello world", "text/plain")},
        data={
            "equipment_key": "frontier-780",
            "doc_type": "manual",
            "published_date": "2025-01-15",
        },
    )
    assert resp.status_code == 400
    assert "PDF" in resp.json()["detail"]


@pytest.mark.anyio
async def test_upload_rejects_invalid_doc_type(async_client, sample_pdf_bytes):
    resp = await async_client.post(
        "/api/v1/upload/document",
        files={"file": ("manual.pdf", sample_pdf_bytes, "application/pdf")},
        data={
            "equipment_key": "frontier-780",
            "doc_type": "invalido",
            "published_date": "2025-01-15",
        },
    )
    assert resp.status_code == 400
    assert "doc_type" in resp.json()["detail"]


@pytest.mark.anyio
async def test_technician_cannot_upload(async_client_tech, sample_pdf_bytes):
    resp = await async_client_tech.post(
        "/api/v1/upload/document",
        files={"file": ("manual.pdf", sample_pdf_bytes, "application/pdf")},
        data={
            "equipment_key": "frontier-780",
            "doc_type": "manual",
            "published_date": "2025-01-15",
        },
    )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_get_stats_admin(async_client):
    stats = {"equipments": 5, "documents": 10, "versions": 15, "chunks": 200}

    with patch("app.api.upload.repository.get_ingestion_stats", new_callable=AsyncMock, return_value=stats):
        resp = await async_client.get("/api/v1/upload/stats")

    assert resp.status_code == 200
    data = resp.json()
    assert data == stats


@pytest.mark.anyio
async def test_technician_cannot_see_stats(async_client_tech):
    resp = await async_client_tech.get("/api/v1/upload/stats")
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_list_equipments(async_client):
    equipment_list = [
        {"equipment_key": "frontier-780", "display_name": "Frontier 780"},
        {"equipment_key": "versant-180", "display_name": "Versant 180"},
    ]

    with patch("app.api.upload.repository.list_equipments", new_callable=AsyncMock, return_value=equipment_list):
        resp = await async_client.get("/api/v1/upload/equipments")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["equipment_key"] == "frontier-780"
