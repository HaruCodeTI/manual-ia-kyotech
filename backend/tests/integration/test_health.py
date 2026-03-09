"""
Kyotech AI — Testes de integração do endpoint /health
"""
import pytest


@pytest.mark.anyio
async def test_health_returns_ok(async_client):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"status": "ok", "service": "kyotech-ai"}
