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

import functools
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


@functools.lru_cache(maxsize=1)
def _get_jwk_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


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
        if settings.environment not in {"development", "test"}:
            raise HTTPException(
                status_code=500,
                detail="CLERK_JWKS_URL não configurado",
            )
        return CurrentUser(id="dev", role="Admin")

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação não fornecido.",
        )

    token = credentials.credentials
    try:
        jwk_client = _get_jwk_client(settings.clerk_jwks_url)
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        decode_options: dict = {}
        decode_kwargs: dict = {"algorithms": ["RS256"]}
        if settings.clerk_jwt_audience:
            decode_options["verify_aud"] = True
            decode_kwargs["audience"] = settings.clerk_jwt_audience
        else:
            decode_options["verify_aud"] = False
        decode_kwargs["options"] = decode_options

        payload = jwt.decode(
            token,
            signing_key.key,
            **decode_kwargs,
        )

        user_id = payload.get("sub", "")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token inválido: sub ausente")

        user = CurrentUser(
            id=user_id,
            role=_extract_role(payload),
        )
        logger.info(f"Usuário autenticado: {user.id} (role={user.role})")
        return user
    except HTTPException:
        raise
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
