"""
Kyotech AI — Fixtures centrais de teste.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import fitz  # PyMuPDF
import httpx
import pytest
from fastapi import FastAPI

from app.core.auth import CurrentUser
from app.main import app as real_app


# ── Fake Users ──

@pytest.fixture
def fake_user_admin() -> CurrentUser:
    return CurrentUser(id="test-admin", role="Admin")


@pytest.fixture
def fake_user_tech() -> CurrentUser:
    return CurrentUser(id="test-tech", role="Technician")


# ── Mock Database Session ──

def _make_mock_result(rows: list | None = None, scalar: object = None):
    result = MagicMock()
    result.fetchone.return_value = rows[0] if rows else None
    result.fetchall.return_value = rows or []
    result.rowcount = len(rows) if rows else 0
    result.scalar.return_value = scalar
    return result


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_make_mock_result())
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def make_mock_result():
    return _make_mock_result


# ── Mock OpenAI Client ──

@pytest.fixture
def mock_openai_client():
    client = AsyncMock()

    embedding_data = MagicMock()
    embedding_data.embedding = [0.1] * 1536
    embedding_response = MagicMock()
    embedding_response.data = [embedding_data]
    client.embeddings.create = AsyncMock(return_value=embedding_response)

    choice = MagicMock()
    choice.message.content = "Resposta de teste [Fonte 1]."
    chat_response = MagicMock()
    chat_response.choices = [choice]
    client.chat.completions.create = AsyncMock(return_value=chat_response)

    return client


# ── Mock Azure Blob Storage ──

@pytest.fixture
def mock_blob_client():
    client = MagicMock()
    blob = MagicMock()
    blob.upload_blob = MagicMock()
    downloader = MagicMock()
    downloader.readall.return_value = b"fake-pdf-bytes"
    blob.download_blob.return_value = downloader
    client.get_blob_client.return_value = blob
    client.account_name = "fakeaccount"
    return client


# ── Sample PDF Bytes ──

@pytest.fixture
def sample_pdf_bytes() -> bytes:
    doc = fitz.open()
    for i in range(1, 3):
        page = doc.new_page(width=595, height=842)
        page.insert_text(
            fitz.Point(72, 72),
            f"Page {i} content: This is sample text for testing purposes.",
            fontsize=12,
        )
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# ── Test App with Dependency Overrides ──

@pytest.fixture
def test_app(fake_user_admin, mock_db):
    from app.core.auth import get_current_user
    from app.core.database import get_db

    real_app.dependency_overrides[get_current_user] = lambda: fake_user_admin
    real_app.dependency_overrides[get_db] = lambda: mock_db
    yield real_app
    real_app.dependency_overrides.clear()


@pytest.fixture
def test_app_tech(fake_user_tech, mock_db):
    from app.core.auth import get_current_user
    from app.core.database import get_db

    real_app.dependency_overrides[get_current_user] = lambda: fake_user_tech
    real_app.dependency_overrides[get_db] = lambda: mock_db
    yield real_app
    real_app.dependency_overrides.clear()


@pytest.fixture
async def async_client(test_app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
async def async_client_tech(test_app_tech):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app_tech),
        base_url="http://test",
    ) as client:
        yield client
