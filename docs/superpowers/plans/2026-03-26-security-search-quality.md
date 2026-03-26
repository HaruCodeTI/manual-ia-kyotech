# Security + Search Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir falha de segurança no endpoint de chat e melhorar qualidade de busca para documentos sem equipamento vinculado via detecção de equipamentos por chunk.

**Architecture:** Adicionar campo `equipment_mentions jsonb` na tabela `chunks` populado por regex contra a tabela `equipments`. A busca individual aumenta de 8→30 resultados; o boost de equipamento passa a usar também `equipment_mentions`. A segurança de sessão é resolvida com validação de ownership antes de usar o `session_id`.

**Tech Stack:** Python 3.9, FastAPI, SQLAlchemy async, PostgreSQL + pgvector, pytest/anyio

---

## File Map

| Ação | Arquivo |
|------|---------|
| Create | `backend/migrations/007_chunk_equipment_mentions.sql` |
| Create | `backend/app/services/equipment_detector.py` |
| Create | `backend/scripts/backfill_equipment_mentions.py` |
| Create | `backend/tests/unit/test_equipment_detector.py` |
| Modify | `backend/app/services/search.py` |
| Modify | `backend/app/services/ingestion.py` |
| Modify | `backend/app/api/chat.py` |
| Modify | `backend/tests/unit/test_search.py` |
| Modify | `backend/tests/integration/test_chat_api.py` |

---

## Task 1: Migration SQL

**Files:**
- Create: `backend/migrations/007_chunk_equipment_mentions.sql`

- [ ] **Step 1: Criar o arquivo de migration**

```sql
-- 007_chunk_equipment_mentions.sql
ALTER TABLE chunks
ADD COLUMN IF NOT EXISTS equipment_mentions jsonb NOT NULL DEFAULT '[]';

CREATE INDEX IF NOT EXISTS idx_chunks_equipment_mentions
ON chunks USING gin(equipment_mentions);
```

- [ ] **Step 2: Verificar que a migration será aplicada automaticamente**

O arquivo `backend/app/main.py` já aplica migrations em ordem alfabética via `run_migrations()`. Confirme que `007_` vem depois de `006_` com:

```bash
ls backend/migrations/
```

Expected output inclui:
```
006_conversation_memory.sql
007_chunk_equipment_mentions.sql
```

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/007_chunk_equipment_mentions.sql
git commit -m "feat(db): adicionar campo equipment_mentions aos chunks"
```

---

## Task 2: Equipment Detector Service + Testes

**Files:**
- Create: `backend/app/services/equipment_detector.py`
- Create: `backend/tests/unit/test_equipment_detector.py`

- [ ] **Step 1: Escrever os testes que devem falhar**

Crie `backend/tests/unit/test_equipment_detector.py`:

```python
"""
Kyotech AI — Testes unitários para app.services.equipment_detector
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.equipment_detector import (
    build_equipment_patterns,
    detect_equipment_mentions,
    detect_mentions_for_version,
)


def _make_equipment_rows(items: list[tuple[str, list[str]]]):
    """items: [(equipment_key, aliases), ...]"""
    rows = []
    for key, aliases in items:
        row = MagicMock()
        row.__getitem__ = lambda self, i, _key=key, _aliases=aliases: _key if i == 0 else _aliases
        rows.append((key, aliases))
    return rows


# ── build_equipment_patterns ──

def test_build_patterns_returns_dict_keyed_by_equipment():
    equipment_list = [("ec-720r/l", ["EC-720R/L", "720R"]), ("ec-530", [])]
    patterns = build_equipment_patterns(equipment_list)
    assert "ec-720r/l" in patterns
    assert "ec-530" in patterns


def test_build_patterns_includes_aliases():
    equipment_list = [("ec-720r/l", ["720R/L", "EC720"])]
    patterns = build_equipment_patterns(equipment_list)
    pattern = patterns["ec-720r/l"]
    assert pattern.search("the 720R/L guide") is not None
    assert pattern.search("EC720 repair") is not None


def test_build_patterns_matches_key_case_insensitive():
    equipment_list = [("ec-530wm", [])]
    patterns = build_equipment_patterns(equipment_list)
    assert patterns["ec-530wm"].search("ec-530WM adhesive") is not None
    assert patterns["ec-530wm"].search("EC-530wm adhesive") is not None


def test_build_patterns_no_partial_match():
    """EC-530 should not match EC-5300."""
    equipment_list = [("ec-530", [])]
    patterns = build_equipment_patterns(equipment_list)
    assert patterns["ec-530"].search("EC-5300 unit") is None


# ── detect_equipment_mentions ──

def test_detect_mentions_returns_matched_keys():
    equipment_list = [("ec-720r/l", ["EC-720R/L"]), ("ec-530", [])]
    patterns = build_equipment_patterns(equipment_list)
    result = detect_equipment_mentions(
        "Use adhesive on EC-720R/L light guide lens.", patterns
    )
    assert result == ["ec-720r/l"]


def test_detect_mentions_returns_empty_for_no_match():
    equipment_list = [("ec-720r/l", []), ("ec-530", [])]
    patterns = build_equipment_patterns(equipment_list)
    result = detect_equipment_mentions("Generic repair procedure.", patterns)
    assert result == []


def test_detect_mentions_deduplicates():
    equipment_list = [("ec-720r/l", ["EC-720R/L"])]
    patterns = build_equipment_patterns(equipment_list)
    result = detect_equipment_mentions(
        "EC-720R/L and EC-720R/L again", patterns
    )
    assert result.count("ec-720r/l") == 1


def test_detect_mentions_finds_multiple_equipments():
    equipment_list = [("ec-720r/l", []), ("ec-530", [])]
    patterns = build_equipment_patterns(equipment_list)
    result = detect_equipment_mentions(
        "Compatible with EC-720R/L and EC-530.", patterns
    )
    assert set(result) == {"ec-720r/l", "ec-530"}


# ── detect_mentions_for_version ──

@pytest.mark.asyncio
async def test_detect_mentions_for_version_updates_chunks(mock_db, make_mock_result):
    chunk_rows = [
        ("chunk-1", "Adhesive for EC-720R/L light guide."),
        ("chunk-2", "Generic endoscope cleaning procedure."),
    ]
    equipment_rows = [("ec-720r/l", []), ("ec-530", [])]

    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # query for equipment list
            return make_mock_result(rows=equipment_rows)
        # query for chunks
        return make_mock_result(rows=chunk_rows)

    mock_db.execute = AsyncMock(side_effect=side_effect)

    await detect_mentions_for_version(mock_db, "version-uuid-123")

    # Should have called execute: 1x equipment list + 1x chunk list + updates
    assert mock_db.execute.call_count >= 2
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_detect_mentions_for_version_skips_empty_chunks(mock_db, make_mock_result):
    equipment_rows = [("ec-720r/l", [])]
    chunk_rows = []

    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_result(rows=equipment_rows)
        return make_mock_result(rows=chunk_rows)

    mock_db.execute = AsyncMock(side_effect=side_effect)

    await detect_mentions_for_version(mock_db, "version-uuid-123")

    mock_db.commit.assert_not_awaited()
```

- [ ] **Step 2: Rodar testes para confirmar que falham**

```bash
cd backend && python -m pytest tests/unit/test_equipment_detector.py -v 2>&1 | head -30
```

Expected: `ImportError` ou `ModuleNotFoundError` para `equipment_detector`.

- [ ] **Step 3: Implementar `equipment_detector.py`**

Crie `backend/app/services/equipment_detector.py`:

```python
"""
Kyotech AI — Detecção de equipamentos em chunks via regex.
Busca equipment_keys e aliases da tabela equipments no conteúdo dos chunks.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Pattern, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def build_equipment_patterns(
    equipment_list: List[Tuple[str, List]],
) -> Dict[str, Pattern]:
    """
    Compila um dict {equipment_key: regex_pattern} a partir da lista de equipamentos.
    Cada pattern verifica o key + todos os aliases, case-insensitive, com word boundary.
    """
    patterns: Dict[str, Pattern] = {}
    for equipment_key, aliases in equipment_list:
        terms = [equipment_key]
        if aliases:
            terms.extend(str(a) for a in aliases if a)
        # Ordena por tamanho decrescente para evitar match parcial de alias menor
        terms_sorted = sorted(set(terms), key=len, reverse=True)
        escaped = [re.escape(t) for t in terms_sorted]
        pattern_str = r"(?<![A-Za-z0-9])(?:" + "|".join(escaped) + r")(?![A-Za-z0-9])"
        patterns[equipment_key] = re.compile(pattern_str, re.IGNORECASE)
    return patterns


def detect_equipment_mentions(
    content: str,
    patterns: Dict[str, Pattern],
) -> List[str]:
    """
    Retorna lista deduplicada de equipment_keys encontrados no conteúdo.
    Puro CPU — sem I/O.
    """
    found = []
    for equipment_key, pattern in patterns.items():
        if pattern.search(content):
            found.append(equipment_key)
    return found


async def detect_mentions_for_version(
    db: AsyncSession,
    version_id: str,
) -> int:
    """
    Para todos os chunks de uma versão, detecta equipamentos mencionados
    e atualiza o campo equipment_mentions no banco.
    Retorna o número de chunks atualizados.
    """
    # Carregar lista de equipamentos
    eq_result = await db.execute(
        text("SELECT equipment_key, aliases FROM equipments ORDER BY equipment_key")
    )
    equipment_list = [(row[0], row[1] or []) for row in eq_result.fetchall()]

    if not equipment_list:
        logger.info("Nenhum equipamento cadastrado — detecção ignorada.")
        return 0

    patterns = build_equipment_patterns(equipment_list)

    # Buscar chunks da versão
    chunk_result = await db.execute(
        text("SELECT id, content FROM chunks WHERE document_version_id = :vid"),
        {"vid": version_id},
    )
    chunks = chunk_result.fetchall()

    if not chunks:
        return 0

    updated = 0
    for chunk_id, content in chunks:
        mentions = detect_equipment_mentions(content or "", patterns)
        await db.execute(
            text("UPDATE chunks SET equipment_mentions = :mentions WHERE id = :id"),
            {"mentions": json.dumps(mentions), "id": str(chunk_id)},
        )
        if mentions:
            updated += 1

    await db.commit()
    logger.info(
        f"Detecção concluída para versão {version_id}: "
        f"{len(chunks)} chunks processados, {updated} com equipamentos detectados."
    )
    return updated
```

- [ ] **Step 4: Rodar testes para confirmar que passam**

```bash
cd backend && python -m pytest tests/unit/test_equipment_detector.py -v
```

Expected: todos os testes `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/equipment_detector.py backend/tests/unit/test_equipment_detector.py
git commit -m "feat(search): implementar equipment_detector com regex e testes"
```

---

## Task 3: Atualizar `search.py` — SearchResult + pool + boost

**Files:**
- Modify: `backend/app/services/search.py`
- Modify: `backend/tests/unit/test_search.py`

- [ ] **Step 1: Adicionar testes para as mudanças em search.py**

Em `backend/tests/unit/test_search.py`, adicione ao final do arquivo:

```python
@pytest.mark.asyncio
async def test_hybrid_search_boosts_equipment_mentions(mock_db, make_mock_result):
    """Chunk com equipment_key=None mas equipment_mentions=['ec-720r/l'] recebe boost."""
    from app.services.search import EQUIPMENT_BOOST

    # chunk sem equipment_key mas com mention
    mention_row = _make_row(
        chunk_id="mention", similarity=0.5, equip=None,
        equipment_mentions=["ec-720r/l"]
    )
    # chunk com equipment_key correto
    tagged_row = _make_row(
        chunk_id="tagged", similarity=0.5, equip="ec-720r/l",
        equipment_mentions=[]
    )
    # chunk sem nenhum vínculo
    other_row = _make_row(
        chunk_id="other", similarity=0.5, equip="ec-530",
        equipment_mentions=[]
    )

    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[mention_row, tagged_row, other_row])
    )

    with patch("app.services.search.generate_single_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
        results = await hybrid_search(mock_db, "q", "q", equipment_key="ec-720r/l")

    ids_in_order = [r.chunk_id for r in results]
    # "mention" e "tagged" devem vir antes de "other"
    assert ids_in_order.index("other") > ids_in_order.index("mention")
    assert ids_in_order.index("other") > ids_in_order.index("tagged")


@pytest.mark.asyncio
async def test_hybrid_search_uses_pool_of_30(mock_db, make_mock_result):
    """hybrid_search deve passar limit=30 para vector_search e text_search."""
    mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[]))

    with patch("app.services.search.vector_search", new_callable=AsyncMock, return_value=[]) as mock_v, \
         patch("app.services.search.text_search", new_callable=AsyncMock, return_value=[]) as mock_t:
        await hybrid_search(mock_db, "q_en", "q_pt", limit=8)

    assert mock_v.call_args.kwargs.get("limit") == 30
    assert mock_t.call_args.kwargs.get("limit") == 30
```

- [ ] **Step 2: Rodar novos testes para confirmar que falham**

```bash
cd backend && python -m pytest tests/unit/test_search.py::test_hybrid_search_boosts_equipment_mentions tests/unit/test_search.py::test_hybrid_search_uses_pool_of_30 -v
```

Expected: `FAILED` — `_make_row` não aceita `equipment_mentions`, pool ainda é 8.

- [ ] **Step 3: Atualizar `_make_row` no arquivo de testes**

Em `backend/tests/unit/test_search.py`, substitua a função `_make_row`:

```python
def _make_row(chunk_id="c1", content="texto", page=1, similarity=0.9,
              doc_id="d1", doc_type="manual", equip="equip-a",
              pub_date=date(2024, 1, 1), filename="f.pdf",
              storage="container/blob", version_id="v1", quality_score=0.0,
              equipment_mentions=None):
    return (chunk_id, content, page, similarity, doc_id, doc_type,
            equip, pub_date, filename, storage, version_id, quality_score,
            equipment_mentions or [])
```

- [ ] **Step 4: Atualizar `search.py`**

Em `backend/app/services/search.py`:

**4a. Adicionar `equipment_mentions` ao `SearchResult`:**

```python
@dataclass
class SearchResult:
    chunk_id: str
    content: str
    page_number: int
    similarity: float
    document_id: str
    doc_type: str
    equipment_key: str
    published_date: date
    source_filename: str
    storage_path: str
    search_type: str
    document_version_id: str = ""
    quality_score: float = 0.0
    equipment_mentions: list = field(default_factory=list)
```

Adicione o import no topo do arquivo:
```python
from dataclasses import dataclass, field
```

**4b. Adicionar `c.equipment_mentions` ao SELECT em `vector_search`:**

No SELECT de `vector_search`, adicione após `c.quality_score`:
```sql
c.equipment_mentions
```

E no retorno, adicione `equipment_mentions=row[12] or []` ao construtor `SearchResult`.

**4c. Fazer o mesmo em `text_search`:**

Mesmo padrão — adicione `c.equipment_mentions` ao SELECT e `equipment_mentions=row[12] or []` ao construtor.

**4d. Atualizar `hybrid_search` — pool de 30:**

```python
vector_results = await vector_search(db, query_en, limit=30, include_all_versions=include_all_versions)
text_results = await text_search(db, query_original, limit=30, include_all_versions=include_all_versions)
```

**4e. Atualizar boost em `hybrid_search`:**

Substitua o bloco de boost de equipamento:

```python
# Boost para documentos do equipamento mencionado
if equipment_key:
    for chunk_id, result in merged.items():
        # boost por tag do documento
        if result.equipment_key and result.equipment_key == equipment_key:
            scores[chunk_id] += EQUIPMENT_BOOST
        # boost por menção detectada no chunk (docs misc incluídos)
        elif equipment_key in (result.equipment_mentions or []):
            scores[chunk_id] += EQUIPMENT_BOOST
```

- [ ] **Step 5: Rodar todos os testes de search**

```bash
cd backend && python -m pytest tests/unit/test_search.py -v
```

Expected: todos `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/search.py backend/tests/unit/test_search.py
git commit -m "feat(search): aumentar pool para 30 e boost via equipment_mentions"
```

---

## Task 4: Atualizar Ingestion — passo 7/7

**Files:**
- Modify: `backend/app/services/ingestion.py`

- [ ] **Step 1: Adicionar passo 7/7 em `ingestion.py`**

Após a linha `logger.info(f"✅ Ingestion completa: {filename} → {len(chunks)} chunks")`, adicione:

```python
        # Passo 7: Detectar equipamentos nos chunks
        if chunks:
            from app.services.equipment_detector import detect_mentions_for_version
            logger.info(f"[7/7] Detectando equipamentos nos chunks")
            detected = await detect_mentions_for_version(db, str(version_id))
            logger.info(f"  → {detected} chunks com equipamentos detectados")
```

O import local evita import circular pois `equipment_detector` usa `repository` indiretamente.

- [ ] **Step 2: Verificar que os testes de ingestion existentes ainda passam**

```bash
cd backend && python -m pytest tests/unit/test_repository.py -v
```

Expected: todos `PASSED`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/ingestion.py
git commit -m "feat(ingestion): adicionar passo 7/7 de detecção de equipamentos por chunk"
```

---

## Task 5: Script de Backfill

**Files:**
- Create: `backend/scripts/backfill_equipment_mentions.py`

- [ ] **Step 1: Criar o script**

Crie `backend/scripts/backfill_equipment_mentions.py`:

```python
"""
Kyotech AI — Backfill de equipment_mentions para chunks existentes.

Uso:
    cd backend
    python scripts/backfill_equipment_mentions.py

Idempotente: pode ser rodado múltiplas vezes sem efeito colateral.
Processa apenas chunks onde equipment_mentions = '[]'.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

# Garante que o módulo app está no path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.core.database import async_session
from app.services.equipment_detector import build_equipment_patterns, detect_equipment_mentions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def run_backfill() -> None:
    async with async_session() as db:
        # Carregar equipamentos
        eq_result = await db.execute(
            text("SELECT equipment_key, aliases FROM equipments ORDER BY equipment_key")
        )
        equipment_list = [(row[0], row[1] or []) for row in eq_result.fetchall()]

        if not equipment_list:
            logger.warning("Nenhum equipamento cadastrado. Backfill não tem o que fazer.")
            return

        patterns = build_equipment_patterns(equipment_list)
        logger.info(f"{len(equipment_list)} equipamentos carregados para detecção.")

        # Buscar chunks com equipment_mentions vazio
        chunk_result = await db.execute(
            text("SELECT id, content FROM chunks WHERE equipment_mentions = '[]'::jsonb")
        )
        chunks = chunk_result.fetchall()

        if not chunks:
            logger.info("Nenhum chunk com equipment_mentions vazio. Backfill já completo.")
            return

        logger.info(f"{len(chunks)} chunks para processar.")

        updated = 0
        for i, (chunk_id, content) in enumerate(chunks, 1):
            mentions = detect_equipment_mentions(content or "", patterns)
            if mentions:
                await db.execute(
                    text("UPDATE chunks SET equipment_mentions = :m WHERE id = :id"),
                    {"m": json.dumps(mentions), "id": str(chunk_id)},
                )
                updated += 1

            if i % 50 == 0:
                logger.info(f"  Progresso: {i}/{len(chunks)} chunks processados...")

        await db.commit()
        logger.info(
            f"Backfill concluído: {len(chunks)} processados, "
            f"{updated} atualizados com equipamentos detectados."
        )


if __name__ == "__main__":
    asyncio.run(run_backfill())
```

- [ ] **Step 2: Commit do script**

```bash
git add backend/scripts/backfill_equipment_mentions.py
git commit -m "feat(scripts): backfill de equipment_mentions para chunks existentes"
```

- [ ] **Step 3: Executar o backfill em produção via Azure CLI**

O backend está em Azure Container Apps sem acesso direto. Execute o script via `az containerapp exec`:

```bash
az containerapp exec \
  --name kyotech-backend \
  --resource-group rg-kyotech-ai \
  --command "python scripts/backfill_equipment_mentions.py"
```

Expected output (exemplo):
```
10:30:00 │ INFO    │ 5 equipamentos carregados para detecção.
10:30:00 │ INFO    │ 287 chunks para processar.
10:30:01 │ INFO    │   Progresso: 50/287 chunks processados...
...
10:30:05 │ INFO    │ Backfill concluído: 287 processados, 142 atualizados com equipamentos detectados.
```

---

## Task 6: Fix de Segurança — Validação de Ownership de Sessão

**Files:**
- Modify: `backend/app/api/chat.py`
- Modify: `backend/tests/integration/test_chat_api.py`

- [ ] **Step 1: Adicionar teste de segurança**

Em `backend/tests/integration/test_chat_api.py`, adicione ao final:

```python
@pytest.mark.anyio
async def test_ask_with_foreign_session_returns_404(async_client):
    """session_id de outro usuário deve retornar 404."""
    foreign_session_id = str(uuid4())

    with (
        patch(
            "app.api.chat.chat_repository.get_session_with_messages",
            new_callable=AsyncMock,
            return_value=None,  # simula sessão não encontrada para este usuário
        ),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={
                "question": "Pergunta qualquer",
                "session_id": foreign_session_id,
            },
        )

    assert resp.status_code == 404
    assert "Sessão não encontrada" in resp.json()["detail"]
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

```bash
cd backend && python -m pytest tests/integration/test_chat_api.py::test_ask_with_foreign_session_returns_404 -v
```

Expected: `FAILED` — atualmente retorna 200.

- [ ] **Step 3: Aplicar o fix em `chat.py`**

Em `backend/app/api/chat.py`, substitua o bloco de resolução de sessão (linhas 173-177):

```python
    # Resolver sessão
    if body.session_id:
        session_id = UUID(body.session_id)
        owned = await chat_repository.get_session_with_messages(db, session_id, user.id)
        if not owned:
            raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    else:
        title = question[:80] + ("…" if len(question) > 80 else "")
        session_id = await chat_repository.create_session(db, user.id, title)
```

- [ ] **Step 4: Atualizar o teste `test_ask_with_existing_session` que agora precisa mockar `get_session_with_messages`**

O teste `test_ask_with_existing_session` existente passará a falhar porque o endpoint agora chama `get_session_with_messages` quando `session_id` é fornecido. Adicione o mock:

```python
@pytest.mark.anyio
async def test_ask_with_existing_session(async_client):
    session_id = uuid4()

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock) as mock_create,
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock, return_value={"history_summary": None, "last_summarized_at": None}),
        patch("app.api.chat.chat_repository.get_session_with_messages", new_callable=AsyncMock, return_value={"id": str(session_id)}),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={
                "question": "Como trocar o rolo de pressão?",
                "session_id": str(session_id),
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == str(session_id)
    mock_create.assert_not_awaited()
```

- [ ] **Step 5: Rodar todos os testes de integração**

```bash
cd backend && python -m pytest tests/integration/test_chat_api.py -v
```

Expected: todos `PASSED`.

- [ ] **Step 6: Rodar a suite completa**

```bash
cd backend && python -m pytest tests/ -v --tb=short
```

Expected: todos `PASSED`.

- [ ] **Step 7: Commit final**

```bash
git add backend/app/api/chat.py backend/tests/integration/test_chat_api.py
git commit -m "fix(security): validar ownership de session_id no endpoint de chat"
```

---

## Resumo da Ordem de Execução

```
Task 1 → Task 2 → Task 3 → Task 4 → Task 5 (backfill em produção) → Task 6
```

Tasks 1-4 e 6 são código + testes. Task 5 é operacional (execução do backfill no container em produção após deploy).
