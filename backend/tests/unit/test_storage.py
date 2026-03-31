"""
Kyotech AI — Testes unitarios para app.services.storage
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.storage import upload_pdf, download_blob, generate_signed_url, delete_blob


# ── upload_pdf ──

@pytest.mark.asyncio
async def test_upload_pdf_uses_default_container(mock_blob_client):
    with patch("app.services.storage.get_blob_client", return_value=mock_blob_client), \
         patch("app.services.storage.settings") as mock_settings:
        mock_settings.azure_storage_container_originals = "pdfs-originais"
        result = await upload_pdf(b"pdf-data", "path/test.pdf")

    assert result == "pdfs-originais/path/test.pdf"
    mock_blob_client.get_blob_client.assert_called_once_with(
        container="pdfs-originais", blob="path/test.pdf"
    )


@pytest.mark.asyncio
async def test_upload_pdf_supports_custom_container(mock_blob_client):
    with patch("app.services.storage.get_blob_client", return_value=mock_blob_client):
        result = await upload_pdf(b"pdf-data", "test.pdf", container="custom-container")

    assert result == "custom-container/test.pdf"
    mock_blob_client.get_blob_client.assert_called_once_with(
        container="custom-container", blob="test.pdf"
    )


# ── download_blob ──

@pytest.mark.asyncio
async def test_download_blob_splits_path(mock_blob_client):
    with patch("app.services.storage.get_blob_client", return_value=mock_blob_client):
        data = await download_blob("my-container/some/blob.pdf")

    mock_blob_client.get_blob_client.assert_called_once_with(
        container="my-container", blob="some/blob.pdf"
    )
    assert data == b"fake-pdf-bytes"


# ── generate_signed_url ──

def test_generate_signed_url_contains_account_and_sas(mock_blob_client):
    fake_sas = "sv=2024&sig=abc"

    with patch("app.services.storage.get_blob_client", return_value=mock_blob_client), \
         patch("app.services.storage.settings") as mock_settings, \
         patch("app.services.storage.generate_blob_sas", return_value=fake_sas):
        mock_settings.azure_storage_connection_string = (
            "DefaultEndpointsProtocol=https;AccountName=fakeaccount;"
            "AccountKey=ZmFrZWtleQ==;EndpointSuffix=core.windows.net"
        )
        url = generate_signed_url("container/blob.pdf")

    assert "fakeaccount" in url
    assert fake_sas in url
    assert url.startswith("https://")


# ── delete_blob ──

@pytest.mark.asyncio
async def test_delete_blob_splits_path_and_deletes(mock_blob_client):
    with patch("app.services.storage.get_blob_client", return_value=mock_blob_client):
        await delete_blob("my-container/some/blob.pdf")

    mock_blob_client.get_blob_client.assert_called_once_with(
        container="my-container", blob="some/blob.pdf"
    )
    mock_blob_client.get_blob_client.return_value.delete_blob.assert_called_once()
