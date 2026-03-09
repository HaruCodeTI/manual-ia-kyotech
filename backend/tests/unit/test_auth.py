"""Tests for app.core.auth — _extract_role, get_current_user, require_role."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from app.core.auth import CurrentUser, _extract_role, get_current_user, require_role


# ── _extract_role ──


class TestExtractRole:
    def test_admin_role(self):
        claims = {"metadata": {"role": "Admin"}}
        assert _extract_role(claims) == "Admin"

    def test_technician_role(self):
        claims = {"metadata": {"role": "Technician"}}
        assert _extract_role(claims) == "Technician"

    def test_no_metadata_defaults_to_technician(self):
        claims = {}
        assert _extract_role(claims) == "Technician"

    def test_metadata_not_dict_defaults_to_technician(self):
        claims = {"metadata": "not-a-dict"}
        assert _extract_role(claims) == "Technician"

    def test_metadata_without_role_defaults_to_technician(self):
        claims = {"metadata": {"other_key": "value"}}
        assert _extract_role(claims) == "Technician"


# ── get_current_user ──


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_dev_mode_when_jwks_url_empty(self):
        """When clerk_jwks_url is empty, return dev user."""
        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.clerk_jwks_url = ""
            user = await get_current_user(credentials=None)
            assert user.id == "dev"
            assert user.role == "Admin"

    @pytest.mark.asyncio
    async def test_missing_token_raises_401(self):
        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.clerk_jwks_url = "https://example.com/.well-known/jwks.json"
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials=None)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self):
        creds = MagicMock()
        creds.credentials = "expired-token"
        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.clerk_jwks_url = "https://example.com/.well-known/jwks.json"
            with patch("app.core.auth._get_jwk_client") as mock_jwk:
                mock_jwk.return_value.get_signing_key_from_jwt.side_effect = (
                    pyjwt.ExpiredSignatureError("Token expired")
                )
                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(credentials=creds)
                assert exc_info.value.status_code == 401
                assert "expirado" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        creds = MagicMock()
        creds.credentials = "bad-token"
        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.clerk_jwks_url = "https://example.com/.well-known/jwks.json"
            with patch("app.core.auth._get_jwk_client") as mock_jwk:
                mock_jwk.return_value.get_signing_key_from_jwt.side_effect = (
                    pyjwt.InvalidTokenError("Invalid")
                )
                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(credentials=creds)
                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_jwks_failure_raises_503(self):
        creds = MagicMock()
        creds.credentials = "some-token"
        with patch("app.core.auth.settings") as mock_settings:
            mock_settings.clerk_jwks_url = "https://example.com/.well-known/jwks.json"
            with patch("app.core.auth._get_jwk_client") as mock_jwk:
                mock_jwk.return_value.get_signing_key_from_jwt.side_effect = (
                    ConnectionError("JWKS unreachable")
                )
                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(credentials=creds)
                assert exc_info.value.status_code == 503


# ── require_role ──


class TestRequireRole:
    @pytest.mark.asyncio
    async def test_admin_can_access_admin_route(self):
        checker = require_role("Admin")
        admin_user = CurrentUser(id="u1", role="Admin")
        result = await checker(user=admin_user)
        assert result.role == "Admin"

    @pytest.mark.asyncio
    async def test_technician_cannot_access_admin_route(self):
        checker = require_role("Admin")
        tech_user = CurrentUser(id="u2", role="Technician")
        with pytest.raises(HTTPException) as exc_info:
            await checker(user=tech_user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_access_technician_route(self):
        checker = require_role("Technician")
        admin_user = CurrentUser(id="u3", role="Admin")
        result = await checker(user=admin_user)
        assert result.role == "Admin"

    @pytest.mark.asyncio
    async def test_technician_can_access_technician_route(self):
        checker = require_role("Technician")
        tech_user = CurrentUser(id="u4", role="Technician")
        result = await checker(user=tech_user)
        assert result.role == "Technician"
