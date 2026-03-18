"""
Kyotech AI — Configurações centralizadas
"""
from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    database_url: str = Field(..., description="URL de conexão asyncpg")

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_embedding_deployment: str = "embedding-small"
    azure_openai_chat_deployment: str = "gpt-4o"
    azure_openai_mini_deployment: str = "gpt-4o-mini"

    azure_storage_connection_string: str = ""
    azure_storage_container_originals: str = "pdfs-originais"
    azure_storage_container_processed: str = "pdfs-processados"

    clerk_jwks_url: str = ""

    chunk_size: int = 800
    chunk_overlap: int = 200
    max_upload_size_mb: int = 200

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
