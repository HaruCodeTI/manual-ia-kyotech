"""
Kyotech AI — Autenticação via Clerk
Valida tokens JWT emitidos pelo Clerk usando JWKS.

Requer configuração de Session Token no Clerk Dashboard:
  Sessions → Customize session token → Edit
  {
    "metadata": "{{user.public_metadata}}"
  }
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

_jwk_client: Optional[PyJWKClient] = None


def _get_jwk_client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(settings.clerk_jwks_url)
    return _jwk_client


@dataclass
class CurrentUser:
    id: str
    role: str  # "Admin" | "Technician"


def _extract_role(claims: dict) -> str:
    metadata = claims.get("metadata", {})
    if isinstance(metadata, dict) and metadata.get("role") == "Admin":
        return "Admin"
    return "Technician"


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> CurrentUser:
    if not settings.clerk_jwks_url:
        return CurrentUser(id="dev", role="Admin")

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação não fornecido.",
        )

    token = credentials.credentials
    try:
        jwk_client = _get_jwk_client()
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )

        user = CurrentUser(
            id=payload.get("sub", ""),
            role=_extract_role(payload),
        )
        logger.info(f"Usuário autenticado: {user.id} (role={user.role})")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado.")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Token inválido: {e}")
        raise HTTPException(status_code=401, detail="Token inválido.")
    except Exception as e:
        logger.error(f"Erro ao validar token: {e}")
        raise HTTPException(status_code=503, detail="Erro ao validar autenticação.")


def require_role(role: str):
    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role != role and user.role != "Admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso restrito ao perfil {role}.",
            )
        return user
    return _check
