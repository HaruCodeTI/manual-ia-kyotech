"""
Kyotech AI — Testes de integração da API de Viewer
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


def _version_info():
    return {
        "source_filename": "manual_frontier.pdf",
        "equipment_key": "frontier-780",
        "doc_type": "manual",
        "published_date": "2025-01-15",
        "storage_path": "documents/frontier-780/manual_frontier.pdf",
    }


@pytest.mark.anyio
async def test_viewer_info_success(async_client, sample_pdf_bytes):
    version_id = uuid4()

    with (
        patch("app.api.viewer.get_version_info", new_callable=AsyncMock, return_value=_version_info()),
        patch("app.api.viewer._get_pdf_bytes", new_callable=AsyncMock, return_value=sample_pdf_bytes),
    ):
        resp = await async_client.get(f"/api/v1/viewer/info/{version_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["version_id"] == str(version_id)
    assert data["source_filename"] == "manual_frontier.pdf"
    assert data["total_pages"] == 2
    assert data["equipment_key"] == "frontier-780"


@pytest.mark.anyio
async def test_viewer_info_not_found(async_client):
    version_id = uuid4()

    with patch("app.api.viewer.get_version_info", new_callable=AsyncMock, return_value=None):
        resp = await async_client.get(f"/api/v1/viewer/info/{version_id}")

    assert resp.status_code == 404


@pytest.mark.anyio
async def test_viewer_page_success(async_client, sample_pdf_bytes):
    version_id = uuid4()
    # Pre-render a known PNG from sample_pdf_bytes so we know what to expect
    from app.services.viewer import render_page_as_image
    png_bytes, total_pages = render_page_as_image(sample_pdf_bytes, page_number=1, user_id="test-admin")

    with (
        patch("app.api.viewer.get_version_info", new_callable=AsyncMock, return_value=_version_info()),
        patch("app.api.viewer._get_pdf_bytes", new_callable=AsyncMock, return_value=sample_pdf_bytes),
    ):
        resp = await async_client.get(f"/api/v1/viewer/page/{version_id}/1")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    # PNG magic bytes
    assert resp.content[:4] == b"\x89PNG"


@pytest.mark.anyio
async def test_viewer_page_invalid_page_number(async_client, sample_pdf_bytes):
    version_id = uuid4()

    with (
        patch("app.api.viewer.get_version_info", new_callable=AsyncMock, return_value=_version_info()),
        patch("app.api.viewer._get_pdf_bytes", new_callable=AsyncMock, return_value=sample_pdf_bytes),
    ):
        # sample_pdf_bytes has 2 pages; page 99 is out of range
        resp = await async_client.get(f"/api/v1/viewer/page/{version_id}/99")

    assert resp.status_code == 400
