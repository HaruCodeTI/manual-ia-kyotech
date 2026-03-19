"""
Kyotech AI — Testes de integração: security headers
"""
import pytest


@pytest.mark.anyio
async def test_security_headers_present_on_health(async_client):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert resp.headers.get("permissions-policy") == "geolocation=(), camera=(), microphone=()"
    assert "max-age=31536000" in resp.headers.get("strict-transport-security", "")
