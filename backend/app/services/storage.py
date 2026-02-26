"""
Kyotech AI — Serviço de Armazenamento (Azure Blob Storage)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Optional

from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
    BlobSasPermissions,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

_blob_client: Optional[BlobServiceClient] = None


def get_blob_client() -> BlobServiceClient:
    global _blob_client
    if _blob_client is None:
        _blob_client = BlobServiceClient.from_connection_string(
            settings.azure_storage_connection_string,
            max_single_put_size=1 * 1024 * 1024,
            max_block_size=1 * 1024 * 1024,
            connection_timeout=120,
            read_timeout=600,
        )
    return _blob_client


def _upload_blob_sync(
    file_bytes: bytes,
    container: str,
    storage_path: str,
) -> str:
    client = get_blob_client()
    blob_client = client.get_blob_client(container=container, blob=storage_path)
    blob_client.upload_blob(
        file_bytes,
        overwrite=True,
        content_settings=ContentSettings(content_type="application/pdf"),
        timeout=600,
        max_concurrency=4,
    )
    full_path = f"{container}/{storage_path}"
    logger.info(f"PDF uploaded: {full_path}")
    return full_path


async def upload_pdf(
    file_bytes: bytes,
    storage_path: str,
    container: Optional[str] = None,
) -> str:
    container = container or settings.azure_storage_container_originals
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(_upload_blob_sync, file_bytes, container, storage_path),
    )


def generate_signed_url(storage_path: str, expiry_hours: int = 1) -> str:
    parts = storage_path.split("/", 1)
    container_name = parts[0]
    blob_name = parts[1] if len(parts) > 1 else ""

    client = get_blob_client()
    account_name = client.account_name

    account_key = None
    for part in settings.azure_storage_connection_string.split(";"):
        if part.startswith("AccountKey="):
            account_key = part.split("=", 1)[1]
            break

    if not account_key:
        raise ValueError("AccountKey não encontrada na connection string")

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container_name,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
    )

    url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"
    return url
