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
    stats = {
        "equipments": 5,
        "documents": 10,
        "versions": 15,
        "chunks": 200,
        "docs_without_chunks": 2,
    }

    with patch("app.api.upload.repository.get_ingestion_stats", new_callable=AsyncMock, return_value=stats):
        resp = await async_client.get("/api/v1/upload/stats")

    assert resp.status_code == 200
    assert resp.json() == stats


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


@pytest.mark.anyio
async def test_upload_without_metadata_succeeds(async_client, sample_pdf_bytes):
    """Upload sem equipment_key, doc_type e published_date deve ser aceito."""
    from app.services.ingestion import IngestionResult

    mock_result = IngestionResult(
        success=True,
        message="Documento ingerido.",
        document_id="doc-999",
        version_id="ver-999",
        total_pages=1,
        total_chunks=5,
    )

    with patch("app.api.upload.ingest_document", new_callable=AsyncMock, return_value=mock_result):
        resp = await async_client.post(
            "/api/v1/upload/document",
            files={"file": ("sem-meta.pdf", sample_pdf_bytes, "application/pdf")},
            data={},
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.anyio
async def test_upload_invalid_doc_type_when_provided(async_client, sample_pdf_bytes):
    """doc_type inválido quando fornecido deve retornar 400."""
    resp = await async_client.post(
        "/api/v1/upload/document",
        files={"file": ("manual.pdf", sample_pdf_bytes, "application/pdf")},
        data={"doc_type": "invalido"},
    )
    assert resp.status_code == 400
    assert "doc_type" in resp.json()["detail"]


@pytest.mark.anyio
async def test_upload_rejects_empty_file(async_client):
    """Arquivo de 0 bytes deve retornar 400."""
    resp = await async_client.post(
        "/api/v1/upload/document",
        files={"file": ("vazio.pdf", b"", "application/pdf")},
        data={},
    )
    assert resp.status_code == 400
    assert "vazio" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_upload_rejects_oversized_file(async_client):
    """Arquivo acima do limite deve retornar 400."""
    from unittest.mock import patch
    import app.api.upload as upload_module

    with patch.object(upload_module.settings, "max_upload_size_mb", 0):
        resp = await async_client.post(
            "/api/v1/upload/document",
            files={"file": ("grande.pdf", b"%PDF-1.4 content", "application/pdf")},
            data={},
        )

    assert resp.status_code == 400
    assert "excede" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_upload_rejects_invalid_pdf_magic_bytes(async_client):
    """Arquivo sem magic bytes PDF (%PDF-) deve retornar 400."""
    # Cria um arquivo com extensão .pdf mas sem os magic bytes corretos
    fake_pdf_content = b"FAKE PDF CONTENT WITHOUT MAGIC BYTES"
    resp = await async_client.post(
        "/api/v1/upload/document",
        files={"file": ("fake.pdf", fake_pdf_content, "application/pdf")},
        data={},
    )
    assert resp.status_code == 400
    assert "inválido" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_upload_rejects_text_file_as_pdf(async_client):
    """Arquivo de texto com extensão .pdf deve retornar 400 (magic bytes inválidos)."""
    text_content = b"This is just plain text, not a PDF"
    resp = await async_client.post(
        "/api/v1/upload/document",
        files={"file": ("notapdf.pdf", text_content, "application/pdf")},
        data={},
    )
    assert resp.status_code == 400
    # Falha na validação de magic bytes
    assert "pdf" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_get_usage_stats_admin(async_client):
    usage = {
        "total_sessions": 100,
        "total_messages": 350,
        "thumbs_up": 42,
        "thumbs_down": 8,
    }

    with patch("app.api.upload.repository.get_usage_stats", new_callable=AsyncMock, return_value=usage):
        resp = await async_client.get("/api/v1/upload/stats/usage")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sessions"] == 100
    assert data["total_messages"] == 350
    assert data["thumbs_up"] == 42
    assert data["thumbs_down"] == 8


@pytest.mark.anyio
async def test_technician_cannot_see_usage_stats(async_client_tech):
    resp = await async_client_tech.get("/api/v1/upload/stats/usage")
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_upload_accepts_valid_pdf_magic_bytes(async_client, sample_pdf_bytes):
    """Arquivo com magic bytes PDF válidos deve ser processado normalmente."""
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
            files={"file": ("valid.pdf", sample_pdf_bytes, "application/pdf")},
            data={
                "equipment_key": "frontier-780",
                "doc_type": "manual",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ── Duplicates API ──

@pytest.mark.anyio
async def test_get_duplicates_returns_groups(async_client):
    mock_groups = {
        "groups": [
            {
                "source_hash": "abc123",
                "keep": {
                    "version_id": "ver-1",
                    "document_id": "doc-1",
                    "filename": "manual.pdf",
                    "equipment_key": "frontier-780",
                    "doc_type": "manual",
                    "published_date": "2025-01-15",
                    "created_at": "2025-01-15T10:00:00",
                    "storage_path": "container/path1.pdf",
                    "chunk_count": 10,
                },
                "duplicates": [
                    {
                        "version_id": "ver-2",
                        "document_id": "doc-2",
                        "filename": "manual.pdf",
                        "equipment_key": "frontier-780",
                        "doc_type": "manual",
                        "published_date": "2025-03-01",
                        "created_at": "2025-03-01T14:30:00",
                        "storage_path": "container/path2.pdf",
                        "chunk_count": 10,
                    }
                ],
            }
        ],
        "total_groups": 1,
        "total_removable": 1,
    }

    with patch(
        "app.api.upload.repository.find_duplicate_groups",
        new_callable=AsyncMock,
        return_value=mock_groups,
    ):
        resp = await async_client.get("/api/v1/upload/duplicates")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_groups"] == 1
    assert data["total_removable"] == 1
    assert data["groups"][0]["keep"]["version_id"] == "ver-1"


@pytest.mark.anyio
async def test_get_duplicates_empty(async_client):
    mock_groups = {"groups": [], "total_groups": 0, "total_removable": 0}

    with patch(
        "app.api.upload.repository.find_duplicate_groups",
        new_callable=AsyncMock,
        return_value=mock_groups,
    ):
        resp = await async_client.get("/api/v1/upload/duplicates")

    assert resp.status_code == 200
    assert resp.json()["total_groups"] == 0


@pytest.mark.anyio
async def test_technician_cannot_get_duplicates(async_client_tech):
    resp = await async_client_tech.get("/api/v1/upload/duplicates")
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_delete_duplicates_success(async_client):
    delete_result = {
        "deleted": 2,
        "skipped": 0,
        "storage_paths": ["container/a.pdf", "container/b.pdf"],
        "orphan_documents_deleted": 1,
    }

    with patch(
        "app.api.upload.repository.delete_duplicate_versions",
        new_callable=AsyncMock,
        return_value=delete_result,
    ) as mock_delete, \
    patch(
        "app.api.upload.delete_blob",
        new_callable=AsyncMock,
    ) as mock_blob_delete, \
    patch(
        "app.api.upload.invalidate_cache",
        new_callable=AsyncMock,
    ):
        resp = await async_client.request(
            "DELETE",
            "/api/v1/upload/duplicates",
            json={"version_ids": ["ver-1", "ver-2"]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 2
    assert mock_blob_delete.call_count == 2


@pytest.mark.anyio
async def test_delete_duplicates_empty_list(async_client):
    resp = await async_client.request(
        "DELETE",
        "/api/v1/upload/duplicates",
        json={"version_ids": []},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_technician_cannot_delete_duplicates(async_client_tech):
    resp = await async_client_tech.request(
        "DELETE",
        "/api/v1/upload/duplicates",
        json={"version_ids": ["ver-1"]},
    )
    assert resp.status_code == 403
