# Document Version Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Habilitar o bot a identificar e descrever diferenças semânticas entre versões de documentos, tanto quando o usuário perguntar explicitamente quanto quando a busca RAG retornar chunks de versões diferentes.

**Architecture:** Um novo serviço `version_comparator.py` faz diff semântico via gpt-4o-mini entre versões de chunks encontrados na busca. O pipeline RAG existente ganha o parâmetro `include_all_versions` para buscar em todas as versões (não só a mais recente), e o `generator.py` recebe o diff estruturado para montar a resposta no formato adequado. Toda a lógica nova tem fallback explícito — se falhar, o pipeline volta ao comportamento atual sem quebrar.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async, Azure OpenAI (gpt-4o-mini JSON mode), pytest + pytest-asyncio, AsyncMock/MagicMock

**Spec:** `docs/superpowers/specs/2026-03-19-document-version-comparison-design.md`

---

## Mapa de Arquivos

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `backend/app/services/version_comparator.py` | **Criar** | Detecção de multi-versão, agrupamento, diff semântico via LLM |
| `backend/app/services/search.py` | **Modificar** | Flag `include_all_versions` em `vector_search`, `text_search`, `hybrid_search` |
| `backend/app/services/query_rewriter.py` | **Modificar** | Campo `is_comparison_query` em `RewrittenQuery` + detecção no prompt |
| `backend/app/services/generator.py` | **Modificar** | `COMPARISON_SYSTEM_PROMPT`, novos parâmetros em `generate_response` |
| `backend/app/api/chat.py` | **Modificar** | Orquestração do comparador + bypass de cache semântico |
| `backend/tests/unit/test_version_comparator.py` | **Criar** | Testes unitários do novo serviço |
| `backend/tests/unit/test_search.py` | **Modificar** | Testes para `include_all_versions` |
| `backend/tests/unit/test_query_rewriter.py` | **Modificar** | Testes para `is_comparison_query` |
| `backend/tests/unit/test_generator.py` | **Modificar** | Testes para `version_diff` e `is_comparison_query` |
| `backend/tests/integration/test_chat_version_comparison.py` | **Criar** | Testes de integração do pipeline completo |

---

## Task 1: Flag `include_all_versions` no search.py

O `hybrid_search` atual faz JOIN com a view `current_versions` — isso retorna só a versão mais recente de cada documento. Precisamos de um modo que busque em `document_versions` (todas as versões) para o pipeline de comparação.

**Files:**
- Modify: `backend/app/services/search.py`
- Modify: `backend/tests/unit/test_search.py`

- [ ] **Step 1.1: Escrever o teste que verifica que `include_all_versions=False` usa `current_versions`**

Adicionar ao final de `backend/tests/unit/test_search.py`:

```python
class TestIncludeAllVersions:
    @pytest.mark.asyncio
    async def test_vector_search_uses_current_versions_by_default(self, mock_db, make_mock_result):
        mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[]))
        with patch("app.services.search.generate_single_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
            await vector_search(mock_db, "query")
        sql_text = str(mock_db.execute.call_args[0][0].text)
        assert "current_versions" in sql_text
        assert "document_versions" not in sql_text.replace("current_versions", "")

    @pytest.mark.asyncio
    async def test_vector_search_uses_document_versions_when_flag_true(self, mock_db, make_mock_result):
        mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[]))
        with patch("app.services.search.generate_single_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
            await vector_search(mock_db, "query", include_all_versions=True)
        sql_text = str(mock_db.execute.call_args[0][0].text)
        assert "document_versions" in sql_text
        assert "current_versions" not in sql_text

    @pytest.mark.asyncio
    async def test_text_search_uses_document_versions_when_flag_true(self, mock_db, make_mock_result):
        mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[]))
        await text_search(mock_db, "query", include_all_versions=True)
        sql_text = str(mock_db.execute.call_args[0][0].text)
        assert "document_versions" in sql_text
        assert "current_versions" not in sql_text

    @pytest.mark.asyncio
    async def test_hybrid_search_passes_flag_to_sub_searches(self, mock_db, make_mock_result):
        mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[]))
        with patch("app.services.search.vector_search", new_callable=AsyncMock, return_value=[]) as mock_v, \
             patch("app.services.search.text_search", new_callable=AsyncMock, return_value=[]) as mock_t:
            await hybrid_search(mock_db, "q_en", "q_pt", include_all_versions=True)
        mock_v.assert_called_once()
        assert mock_v.call_args.kwargs.get("include_all_versions") is True
        mock_t.assert_called_once()
        assert mock_t.call_args.kwargs.get("include_all_versions") is True
```

- [ ] **Step 1.2: Rodar os testes para confirmar que falham**

```bash
cd /Users/arthurbueno/HaruCode/apps/kyotech-ai/backend
python -m pytest tests/unit/test_search.py::TestIncludeAllVersions -v
```

Esperado: `FAILED` — `TypeError: vector_search() got an unexpected keyword argument 'include_all_versions'`

- [ ] **Step 1.3: Implementar `include_all_versions` em `search.py`**

Em `vector_search`, adicionar parâmetro e adaptar o SQL:

```python
async def vector_search(
    db: AsyncSession,
    query_text: str,
    limit: int = 10,
    doc_type: Optional[str] = None,
    equipment_key: Optional[str] = None,
    include_all_versions: bool = False,  # NOVO
) -> List[SearchResult]:
```

Na query SQL de `vector_search`, substituir:
```sql
-- ANTES:
JOIN current_versions cv ON c.document_version_id = cv.id
-- DEPOIS (dinâmico):
```

Implementar assim (logo antes de `result = await db.execute(...)`):
```python
version_source = "document_versions" if include_all_versions else "current_versions"
```

E na query SQL:
```python
text(f"""
    SELECT
        c.id AS chunk_id,
        ...
    FROM chunks c
    JOIN {version_source} cv ON c.document_version_id = cv.id
    JOIN documents d ON cv.document_id = d.id
    WHERE 1=1
    {where_clause}
    ORDER BY c.embedding <=> cast(:embedding AS vector)
    LIMIT :limit
""")
```

Repetir o mesmo para `text_search` (mesmo parâmetro, mesma substituição do JOIN).

Em `hybrid_search`, adicionar parâmetro e repassar:
```python
async def hybrid_search(
    db: AsyncSession,
    query_en: str,
    query_original: str,
    limit: int = 8,
    doc_type: Optional[str] = None,
    equipment_key: Optional[str] = None,
    vector_weight: float = 0.65,
    text_weight: float = 0.35,
    include_all_versions: bool = False,  # NOVO
) -> List[SearchResult]:
    vector_results = await vector_search(db, query_en, limit=limit, include_all_versions=include_all_versions)
    text_results = await text_search(db, query_original, limit=limit, include_all_versions=include_all_versions)
```

- [ ] **Step 1.4: Rodar os testes**

```bash
python -m pytest tests/unit/test_search.py -v
```

Esperado: todos `PASSED`. Se algum falhar, verifique se a f-string do SQL ficou correta e se os parâmetros dos mocks estão capturando o argumento certo.

- [ ] **Step 1.5: Commit**

```bash
git add backend/app/services/search.py backend/tests/unit/test_search.py
git commit -m "feat(IA-compare): search.py — flag include_all_versions para busca em todas as versões"
```

---

## Task 2: Campo `is_comparison_query` no `query_rewriter.py`

O rewriter precisa detectar quando o técnico está pedindo uma comparação de versões e sinalizar isso ao pipeline.

**Files:**
- Modify: `backend/app/services/query_rewriter.py`
- Modify: `backend/tests/unit/test_query_rewriter.py`

- [ ] **Step 2.1: Escrever os testes**

Adicionar ao final de `backend/tests/unit/test_query_rewriter.py`:

```python
class TestIsComparisonQuery:
    @pytest.mark.asyncio
    async def test_comparison_query_detected(self, _patch_openai_client):
        payload = {
            "query_en": "What changed in the Frontier 780 manual?",
            "doc_type": "manual",
            "equipment_hint": "Frontier 780",
            "needs_clarification": False,
            "clarification_question": None,
            "is_comparison_query": True,
        }
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(payload))
        )
        result = await rewrite_query("O que mudou no manual do Frontier 780?")
        assert result.is_comparison_query is True

    @pytest.mark.asyncio
    async def test_normal_query_not_comparison(self, _patch_openai_client):
        payload = {
            "query_en": "How to replace pressure roller",
            "doc_type": "manual",
            "equipment_hint": None,
            "needs_clarification": False,
            "clarification_question": None,
        }
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(payload))
        )
        result = await rewrite_query("Como trocar o rolo de pressão?")
        assert result.is_comparison_query is False  # default

    @pytest.mark.asyncio
    async def test_is_comparison_query_defaults_false_on_json_without_field(self, _patch_openai_client):
        # JSON sem o campo → default False
        payload = {"query_en": "query", "doc_type": None, "equipment_hint": None}
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(payload))
        )
        result = await rewrite_query("pergunta qualquer")
        assert result.is_comparison_query is False
```

- [ ] **Step 2.2: Rodar os testes para confirmar que falham**

```bash
python -m pytest tests/unit/test_query_rewriter.py::TestIsComparisonQuery -v
```

Esperado: `FAILED` — `RewrittenQuery` não tem campo `is_comparison_query`

- [ ] **Step 2.3: Implementar em `query_rewriter.py`**

**Passo A — Adicionar campo ao dataclass:**
```python
@dataclass
class RewrittenQuery:
    original: str
    query_en: str
    doc_type: Optional[str]
    equipment_hint: Optional[str]
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    is_comparison_query: bool = False  # NOVO
```

**Passo B — Atualizar `REWRITE_PROMPT`** para incluir instrução de detecção de comparação. Adicionar ao final da lista de regras:

```
8. Determine if this is a version comparison query.
   Set is_comparison_query to true if the technician asks to compare versions,
   asks what changed between versions, asks about updates or differences in a document.
   Keywords: "o que mudou", "compara", "diferença entre versões", "versão mais nova",
   "atualização do manual", "nova versão", "changed", "what's new".
```

E atualizar o JSON de saída no prompt:
```
{"query_en": "...", "doc_type": "...", "equipment_hint": "...", "needs_clarification": false, "clarification_question": null, "is_comparison_query": false}
```

**Passo C — Parsear o novo campo no `try` block:**
```python
return RewrittenQuery(
    original=question,
    query_en=parsed.get("query_en", question),
    doc_type=doc_type,
    equipment_hint=equipment,
    needs_clarification=parsed.get("needs_clarification", False),
    clarification_question=parsed.get("clarification_question"),
    is_comparison_query=parsed.get("is_comparison_query", False),  # NOVO
)
```

- [ ] **Step 2.4: Rodar os testes**

```bash
python -m pytest tests/unit/test_query_rewriter.py -v
```

Esperado: todos `PASSED`.

- [ ] **Step 2.5: Commit**

```bash
git add backend/app/services/query_rewriter.py backend/tests/unit/test_query_rewriter.py
git commit -m "feat(IA-compare): query_rewriter.py — detecção de is_comparison_query"
```

---

## Task 3: Novo serviço `version_comparator.py`

O coração da feature. Agrupa chunks por versão, detecta multi-versão, e faz diff semântico via gpt-4o-mini.

**Files:**
- Create: `backend/app/services/version_comparator.py`
- Create: `backend/tests/unit/test_version_comparator.py`

- [ ] **Step 3.1: Criar o arquivo de testes**

Criar `backend/tests/unit/test_version_comparator.py`:

```python
"""Tests for app.services.version_comparator."""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.search import SearchResult
from app.services.version_comparator import (
    DiffItem,
    VersionDiff,
    compare_versions,
    detect_multi_version,
    group_chunks_by_version,
)


# ── Helpers ──

def _make_result(
    chunk_id="c1",
    document_id="doc-a",
    document_version_id="ver-1",
    published_date=date(2024, 7, 1),
    content="texto de teste",
    similarity=0.9,
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        content=content,
        page_number=1,
        similarity=similarity,
        document_id=document_id,
        doc_type="manual",
        equipment_key="frontier-780",
        published_date=published_date,
        source_filename=f"manual_{published_date}.pdf",
        storage_path="container/blob",
        search_type="vector",
        document_version_id=document_version_id,
    )


def _make_chat_response(content: str):
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── detect_multi_version ──

class TestDetectMultiVersion:
    def test_false_when_empty(self):
        assert detect_multi_version([]) is False

    def test_false_when_single_version(self):
        results = [
            _make_result(chunk_id="c1", document_id="doc-a", document_version_id="ver-1"),
            _make_result(chunk_id="c2", document_id="doc-a", document_version_id="ver-1"),
        ]
        assert detect_multi_version(results) is False

    def test_false_when_different_documents(self):
        # Chunks de doc_ids diferentes não ativam comparação
        results = [
            _make_result(chunk_id="c1", document_id="doc-a", document_version_id="ver-1"),
            _make_result(chunk_id="c2", document_id="doc-b", document_version_id="ver-2"),
        ]
        assert detect_multi_version(results) is False

    def test_true_when_same_doc_different_versions(self):
        results = [
            _make_result(chunk_id="c1", document_id="doc-a", document_version_id="ver-1"),
            _make_result(chunk_id="c2", document_id="doc-a", document_version_id="ver-2"),
        ]
        assert detect_multi_version(results) is True

    def test_true_with_three_versions_same_doc(self):
        results = [
            _make_result(chunk_id="c1", document_id="doc-a", document_version_id="ver-1"),
            _make_result(chunk_id="c2", document_id="doc-a", document_version_id="ver-2"),
            _make_result(chunk_id="c3", document_id="doc-a", document_version_id="ver-3"),
        ]
        assert detect_multi_version(results) is True


# ── group_chunks_by_version ──

class TestGroupChunksByVersion:
    def test_groups_by_published_date(self):
        results = [
            _make_result(chunk_id="c1", document_version_id="ver-1", published_date=date(2024, 7, 1)),
            _make_result(chunk_id="c2", document_version_id="ver-2", published_date=date(2025, 1, 15)),
        ]
        grouped = group_chunks_by_version(results)
        assert "2024-07-01" in grouped
        assert "2025-01-15" in grouped
        assert grouped["2024-07-01"][0].chunk_id == "c1"

    def test_ordered_chronologically_oldest_first(self):
        results = [
            _make_result(chunk_id="c2", document_version_id="ver-2", published_date=date(2025, 1, 15)),
            _make_result(chunk_id="c1", document_version_id="ver-1", published_date=date(2024, 7, 1)),
        ]
        grouped = group_chunks_by_version(results)
        keys = list(grouped.keys())
        assert keys[0] == "2024-07-01"
        assert keys[1] == "2025-01-15"

    def test_multiple_chunks_same_version(self):
        results = [
            _make_result(chunk_id="c1", document_version_id="ver-1", published_date=date(2024, 7, 1)),
            _make_result(chunk_id="c2", document_version_id="ver-1", published_date=date(2024, 7, 1)),
            _make_result(chunk_id="c3", document_version_id="ver-2", published_date=date(2025, 1, 15)),
        ]
        grouped = group_chunks_by_version(results)
        assert len(grouped["2024-07-01"]) == 2
        assert len(grouped["2025-01-15"]) == 1


# ── compare_versions ──

@pytest.fixture()
def _patch_openai():
    mock_client = AsyncMock()
    with patch("app.services.version_comparator.get_openai_client", return_value=mock_client):
        yield mock_client


class TestCompareVersions:
    @pytest.mark.asyncio
    async def test_has_changes_returns_diff_items(self, _patch_openai):
        diff_payload = {
            "diff_items": [
                {"change_type": "modified", "topic": "Torque", "old_value": "10 Nm", "new_value": "12 Nm"}
            ],
            "has_changes": True,
        }
        _patch_openai.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(diff_payload))
        )
        grouped = {
            "2024-07-01": [_make_result(chunk_id="c1", published_date=date(2024, 7, 1))],
            "2025-01-15": [_make_result(chunk_id="c2", published_date=date(2025, 1, 15))],
        }
        result = await compare_versions(grouped)
        assert isinstance(result, VersionDiff)
        assert result.has_changes is True
        assert len(result.diff_items) == 1
        assert result.diff_items[0].change_type == "modified"
        assert result.diff_items[0].topic == "Torque"
        assert result.version_old == "2024-07-01"
        assert result.version_new == "2025-01-15"

    @pytest.mark.asyncio
    async def test_no_changes(self, _patch_openai):
        diff_payload = {"diff_items": [], "has_changes": False}
        _patch_openai.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(diff_payload))
        )
        grouped = {
            "2024-07-01": [_make_result(chunk_id="c1", published_date=date(2024, 7, 1))],
            "2025-01-15": [_make_result(chunk_id="c2", published_date=date(2025, 1, 15))],
        }
        result = await compare_versions(grouped)
        assert result.has_changes is False
        assert result.diff_items == []

    @pytest.mark.asyncio
    async def test_malformed_json_raises(self, _patch_openai):
        _patch_openai.chat.completions.create = AsyncMock(
            return_value=_make_chat_response("não é json válido")
        )
        grouped = {
            "2024-07-01": [_make_result(chunk_id="c1", published_date=date(2024, 7, 1))],
            "2025-01-15": [_make_result(chunk_id="c2", published_date=date(2025, 1, 15))],
        }
        with pytest.raises(json.JSONDecodeError):
            await compare_versions(grouped)

    @pytest.mark.asyncio
    async def test_uses_mini_model(self, _patch_openai):
        from app.core.config import settings
        diff_payload = {"diff_items": [], "has_changes": False}
        _patch_openai.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(diff_payload))
        )
        grouped = {
            "2024-07-01": [_make_result(chunk_id="c1", published_date=date(2024, 7, 1))],
            "2025-01-15": [_make_result(chunk_id="c2", published_date=date(2025, 1, 15))],
        }
        await compare_versions(grouped)
        call_kwargs = _patch_openai.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == settings.azure_openai_mini_deployment
```

- [ ] **Step 3.2: Rodar para confirmar que falha**

```bash
python -m pytest tests/unit/test_version_comparator.py -v
```

Esperado: `ImportError` — `version_comparator` não existe ainda.

- [ ] **Step 3.3: Criar `backend/app/services/version_comparator.py`**

```python
"""
Kyotech AI — Comparação Semântica de Versões de Documentos

Detecta quando chunks de busca pertencem a versões diferentes do mesmo documento
e produz um diff semântico via gpt-4o-mini.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List

from app.core.config import settings
from app.services.embedder import get_openai_client
from app.services.search import SearchResult

logger = logging.getLogger(__name__)

VERSION_DIFF_PROMPT = """Você recebe trechos de duas versões do mesmo documento técnico da Fujifilm.
Compare-os e identifique o que mudou semanticamente entre as versões.
Ignore diferenças de formatação ou ordem de palavras. Foque em:
- Valores numéricos (torques, temperaturas, dimensões)
- Procedimentos (passos adicionados, removidos ou modificados)
- Peças ou componentes (substituições, adições)
- Alertas ou avisos de segurança

Versão antiga ({version_old}):
{chunks_old}

Versão nova ({version_new}):
{chunks_new}

Retorne APENAS JSON válido com o schema exato (sem markdown, sem texto adicional):
{{"diff_items": [{{"change_type": "added|removed|modified", "topic": "...", "old_value": "...", "new_value": "..."}}], "has_changes": true}}

Se os documentos forem semanticamente idênticos, retorne:
{{"diff_items": [], "has_changes": false}}"""

MAX_TOKENS_PER_VERSION = 6000  # ~4-5 chunks


@dataclass
class DiffItem:
    change_type: str  # "added" | "removed" | "modified"
    topic: str
    old_value: str
    new_value: str


@dataclass
class VersionDiff:
    version_old: str  # published_date ISO da versão mais antiga
    version_new: str  # published_date ISO da versão mais recente
    diff_items: List[DiffItem] = field(default_factory=list)
    has_changes: bool = False


def detect_multi_version(results: List[SearchResult]) -> bool:
    """
    Retorna True se há ≥2 document_version_id distintos para o mesmo document_id.
    Agrupamento por document_id — campo já presente em SearchResult.
    """
    doc_to_versions: Dict[str, set] = {}
    for r in results:
        doc_to_versions.setdefault(r.document_id, set()).add(r.document_version_id)

    return any(len(versions) >= 2 for versions in doc_to_versions.values())


def group_chunks_by_version(
    results: List[SearchResult],
) -> Dict[str, List[SearchResult]]:
    """
    Agrupa chunks por published_date (ISO string), ordenado cronologicamente.
    Retorna dict com as datas como chave — mais antiga primeiro.
    """
    grouped: Dict[str, List[SearchResult]] = {}
    for r in results:
        date_key = r.published_date.isoformat() if hasattr(r.published_date, "isoformat") else str(r.published_date)
        grouped.setdefault(date_key, []).append(r)

    # Ordenar por data crescente
    return dict(sorted(grouped.items()))


def _build_version_text(chunks: List[SearchResult]) -> str:
    """Constrói texto concatenado dos chunks, priorizando por similarity."""
    sorted_chunks = sorted(chunks, key=lambda c: c.similarity, reverse=True)
    parts = []
    total_chars = 0
    char_limit = MAX_TOKENS_PER_VERSION * 4  # ~4 chars por token

    for chunk in sorted_chunks:
        if total_chars + len(chunk.content) > char_limit:
            break
        parts.append(chunk.content)
        total_chars += len(chunk.content)

    return "\n---\n".join(parts)


async def compare_versions(
    grouped: Dict[str, List[SearchResult]],
) -> VersionDiff:
    """
    Compara a versão mais antiga e a mais recente dos chunks agrupados.
    Usa gpt-4o-mini com JSON mode.

    Raises: json.JSONDecodeError, openai.APIError
    """
    sorted_dates = sorted(grouped.keys())
    version_old = sorted_dates[0]
    version_new = sorted_dates[-1]

    chunks_old = _build_version_text(grouped[version_old])
    chunks_new = _build_version_text(grouped[version_new])

    prompt = VERSION_DIFF_PROMPT.format(
        version_old=version_old,
        version_new=version_new,
        chunks_old=chunks_old,
        chunks_new=chunks_new,
    )

    client = get_openai_client()
    response = await client.chat.completions.create(
        model=settings.azure_openai_mini_deployment,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1000,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    logger.info(f"Version diff: {version_old} → {version_new} | raw: {raw[:200]}")

    parsed = json.loads(raw)  # Raises json.JSONDecodeError se inválido
    diff_items = [
        DiffItem(
            change_type=item.get("change_type", "modified"),
            topic=item.get("topic", ""),
            old_value=item.get("old_value", ""),
            new_value=item.get("new_value", ""),
        )
        for item in parsed.get("diff_items", [])
    ]

    return VersionDiff(
        version_old=version_old,
        version_new=version_new,
        diff_items=diff_items,
        has_changes=parsed.get("has_changes", len(diff_items) > 0),
    )
```

- [ ] **Step 3.4: Rodar os testes**

```bash
python -m pytest tests/unit/test_version_comparator.py -v
```

Esperado: todos `PASSED`.

- [ ] **Step 3.5: Commit**

```bash
git add backend/app/services/version_comparator.py backend/tests/unit/test_version_comparator.py
git commit -m "feat(IA-compare): version_comparator.py — diff semântico entre versões de documentos"
```

---

## Task 4: Atualizar `generator.py` com suporte a `version_diff`

O generator precisa de um novo system prompt para o modo comparação, e de lógica para injetar o diff no contexto quando presente.

**Files:**
- Modify: `backend/app/services/generator.py`
- Modify: `backend/tests/unit/test_generator.py`

- [ ] **Step 4.1: Escrever os testes**

Adicionar ao final de `backend/tests/unit/test_generator.py`:

```python
class TestVersionDiffInGenerator:
    @pytest.mark.asyncio
    async def test_no_diff_uses_default_prompt(self, mock_openai_client):
        """Sem version_diff: comportamento atual preservado."""
        results = [_make_search_result()]  # use helper existente no arquivo
        with patch("app.services.generator.get_openai_client", return_value=mock_openai_client):
            resp = await generate_response(
                question="Como trocar o rolo?",
                query_rewritten="How to replace roller",
                search_results=results,
                version_diff=None,
                is_comparison_query=False,
            )
        assert resp.answer is not None
        # system prompt normal foi usado — header do COMPARISON_SYSTEM_PROMPT não deve aparecer
        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]
        assert "Diferenças entre versões" not in system_msg

    @pytest.mark.asyncio
    async def test_with_diff_explicit_query_uses_comparison_prompt(self, mock_openai_client):
        from app.services.version_comparator import DiffItem, VersionDiff
        diff = VersionDiff(
            version_old="2024-07-01",
            version_new="2025-01-15",
            diff_items=[DiffItem("modified", "Torque", "10 Nm", "12 Nm")],
            has_changes=True,
        )
        results = [_make_search_result()]
        with patch("app.services.generator.get_openai_client", return_value=mock_openai_client):
            resp = await generate_response(
                question="O que mudou?",
                query_rewritten="What changed?",
                search_results=results,
                version_diff=diff,
                is_comparison_query=True,
            )
        assert resp.answer is not None
        call_args = mock_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]
        assert "omparaç" in system_msg or "Diferenças" in system_msg

    @pytest.mark.asyncio
    async def test_no_changes_diff_ignores_diff(self, mock_openai_client):
        from app.services.version_comparator import VersionDiff
        diff = VersionDiff(
            version_old="2024-07-01",
            version_new="2025-01-15",
            diff_items=[],
            has_changes=False,
        )
        results = [_make_search_result()]
        with patch("app.services.generator.get_openai_client", return_value=mock_openai_client):
            resp = await generate_response(
                question="O que mudou?",
                query_rewritten="What changed?",
                search_results=results,
                version_diff=diff,
                is_comparison_query=True,
            )
        assert resp.answer is not None
        # Sem diff real, contexto não inclui "DIFERENÇAS DETECTADAS"
        call_args = mock_openai_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]  # index 0 = system, index 1 = user
        assert "DIFERENÇAS DETECTADAS" not in user_msg
```

Nota: `_make_search_result()` provavelmente já existe no `test_generator.py`. Se não existir, adicione:

```python
def _make_search_result(**kwargs):
    from app.services.search import SearchResult
    from datetime import date
    defaults = dict(
        chunk_id="c1", content="conteúdo de teste", page_number=1,
        similarity=0.9, document_id="doc-a", doc_type="manual",
        equipment_key="frontier-780", published_date=date(2024, 7, 1),
        source_filename="manual.pdf", storage_path="container/blob",
        search_type="vector", document_version_id="ver-1",
    )
    defaults.update(kwargs)
    return SearchResult(**defaults)
```

- [ ] **Step 4.2: Rodar os testes para confirmar que falham**

```bash
python -m pytest tests/unit/test_generator.py::TestVersionDiffInGenerator -v
```

Esperado: `FAILED` — `generate_response()` não aceita `version_diff` ainda.

- [ ] **Step 4.3: Implementar em `generator.py`**

**Passo A — Import do `VersionDiff`** (no topo do arquivo):
```python
from typing import Optional  # já deve existir
# Adicionar import lazy para evitar circular (version_comparator importa de search, não de generator):
```

**Passo B — `COMPARISON_SYSTEM_PROMPT`** (adicionar após `DIAGNOSTIC_SYSTEM_PROMPT`):
```python
COMPARISON_SYSTEM_PROMPT = """Você é o assistente técnico da Kyotech, especializado em equipamentos de endoscopia Fujifilm.
O técnico quer entender o que mudou entre versões de um documento técnico.

PERSONALIDADE:
- Tom profissional mas acolhedor — trate o técnico como um colega
- Seja direto e estruturado — comparações precisam de clareza

REGRAS OBRIGATÓRIAS:
1. Responda SEMPRE em português brasileiro
2. Use APENAS as informações dos trechos e do diff fornecidos — NUNCA invente
3. Para cada afirmação, cite a fonte usando EXATAMENTE o formato [Fonte N]
4. Se não houver diferenças relevantes, diga isso claramente

FORMATO OBRIGATÓRIO DA RESPOSTA:
## Diferenças entre versões ({version_old} → {version_new})
[Liste cada mudança identificada com citações [Fonte N]]

## Resumo
[1-2 frases resumindo o impacto das mudanças para o técnico]

NÃO liste as fontes ao final — o sistema exibe as fontes automaticamente."""
```

**Passo C — Novo helper `build_diff_context`**:
```python
def build_diff_context(version_diff) -> str:
    """Formata o VersionDiff como texto para injetar no contexto do LLM."""
    if not version_diff or not version_diff.has_changes:
        return ""
    lines = [f"DIFERENÇAS DETECTADAS ({version_diff.version_old} → {version_diff.version_new}):"]
    for item in version_diff.diff_items:
        if item.change_type == "modified":
            lines.append(f"- MODIFICADO — {item.topic}: era '{item.old_value}', agora é '{item.new_value}'")
        elif item.change_type == "added":
            lines.append(f"- ADICIONADO — {item.topic}: '{item.new_value}'")
        elif item.change_type == "removed":
            lines.append(f"- REMOVIDO — {item.topic}: era '{item.old_value}'")
    return "\n".join(lines)
```

**Passo D — Atualizar assinatura de `generate_response`**:
```python
async def generate_response(
    question: str,
    query_rewritten: str,
    search_results: List[SearchResult],
    history_messages: Optional[list] = None,
    history_summary: Optional[str] = None,
    diagnostic_mode: bool = False,
    version_diff=None,           # Optional[VersionDiff] — sem import explícito para evitar circular
    is_comparison_query: bool = False,
) -> RAGResponse:
```

**Passo E — Lógica de seleção de system prompt** (logo após a definição de `history_messages`):
```python
if is_comparison_query and version_diff and version_diff.has_changes:
    formatted_prompt = COMPARISON_SYSTEM_PROMPT.format(
        version_old=version_diff.version_old,
        version_new=version_diff.version_new,
    )
    system_prompt = formatted_prompt
elif diagnostic_mode:
    system_prompt = DIAGNOSTIC_SYSTEM_PROMPT
else:
    system_prompt = SYSTEM_PROMPT
```

**Passo F — Injetar diff no contexto** (antes de montar as `messages`):
```python
context = build_context(search_results)
if version_diff and version_diff.has_changes:
    diff_text = build_diff_context(version_diff)
    context = f"{diff_text}\n\n{context}"
```

**Passo G — `max_tokens` para comparison mode**:
```python
max_tokens = 2500 if (is_comparison_query or diagnostic_mode) else 1500
```

- [ ] **Step 4.4: Rodar os testes**

```bash
python -m pytest tests/unit/test_generator.py -v
```

Esperado: todos `PASSED`.

- [ ] **Step 4.5: Commit**

```bash
git add backend/app/services/generator.py backend/tests/unit/test_generator.py
git commit -m "feat(IA-compare): generator.py — COMPARISON_SYSTEM_PROMPT + suporte a version_diff"
```

---

## Task 5: Orquestração em `chat.py` + bypass de cache

Liga todas as peças. O `chat.py` detecta `is_comparison_query`, bypassa o cache semântico, ativa `include_all_versions` na busca e orquestra o comparador com fallback.

**Files:**
- Modify: `backend/app/api/chat.py`
- Create: `backend/tests/integration/test_chat_version_comparison.py`

- [ ] **Step 5.1: Escrever os testes de integração**

Criar `backend/tests/integration/test_chat_version_comparison.py`:

```python
"""
Testes de integração — comparação de versões no pipeline de chat.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.search import SearchResult
from app.services.version_comparator import DiffItem, VersionDiff


def _make_search_result(
    chunk_id="c1",
    document_id="doc-a",
    document_version_id="ver-1",
    published_date=date(2024, 7, 1),
    content="conteúdo de teste",
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        content=content,
        page_number=1,
        similarity=0.9,
        document_id=document_id,
        doc_type="manual",
        equipment_key="frontier-780",
        published_date=published_date,
        source_filename="manual.pdf",
        storage_path="container/blob",
        search_type="vector",
        document_version_id=document_version_id,
    )


def _multi_version_results():
    """Chunks de duas versões diferentes do mesmo documento."""
    return [
        _make_search_result(chunk_id="c1", document_version_id="ver-1", published_date=date(2024, 7, 1)),
        _make_search_result(chunk_id="c2", document_version_id="ver-2", published_date=date(2025, 1, 15)),
    ]


def _make_diff() -> VersionDiff:
    return VersionDiff(
        version_old="2024-07-01",
        version_new="2025-01-15",
        diff_items=[DiffItem("modified", "Torque", "10 Nm", "12 Nm")],
        has_changes=True,
    )


@pytest.mark.asyncio
async def test_comparison_query_bypasses_semantic_cache(async_client):
    """Quando is_comparison_query=True, o cache semântico não é consultado."""
    mock_rewritten = MagicMock()
    mock_rewritten.needs_clarification = False
    mock_rewritten.clarification_question = None
    mock_rewritten.query_en = "What changed?"
    mock_rewritten.doc_type = None
    mock_rewritten.equipment_hint = None
    mock_rewritten.is_comparison_query = True

    with patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=mock_rewritten), \
         patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=_multi_version_results()), \
         patch("app.api.chat.get_cached_response", new_callable=AsyncMock) as mock_cache, \
         patch("app.api.chat.compare_versions", new_callable=AsyncMock, return_value=_make_diff()), \
         patch("app.api.chat.generate_response", new_callable=AsyncMock) as mock_gen, \
         patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock), \
         patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=uuid4()), \
         patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock, return_value=uuid4()), \
         patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=[]), \
         patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock, return_value={}):

        mock_gen.return_value = MagicMock(
            answer="Resposta de comparação",
            citations=[],
            query_original="O que mudou?",
            query_rewritten="What changed?",
            total_sources=0,
            model_used="gpt-4o",
        )

        response = await async_client.post("/api/v1/chat/ask", json={"question": "O que mudou no manual?"})

    assert response.status_code == 200
    # Cache não foi consultado para query de comparação
    mock_cache.assert_not_called()


@pytest.mark.asyncio
async def test_comparison_fallback_when_comparator_raises(async_client):
    """Se compare_versions levanta exceção, resposta é gerada normalmente sem diff."""
    mock_rewritten = MagicMock()
    mock_rewritten.needs_clarification = False
    mock_rewritten.clarification_question = None
    mock_rewritten.query_en = "What changed?"
    mock_rewritten.doc_type = None
    mock_rewritten.equipment_hint = None
    mock_rewritten.is_comparison_query = True

    with patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=mock_rewritten), \
         patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=_multi_version_results()), \
         patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None), \
         patch("app.api.chat.compare_versions", new_callable=AsyncMock, side_effect=ValueError("LLM error")), \
         patch("app.api.chat.generate_response", new_callable=AsyncMock) as mock_gen, \
         patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock), \
         patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=uuid4()), \
         patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock, return_value=uuid4()), \
         patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=[]), \
         patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock, return_value={}):

        mock_gen.return_value = MagicMock(
            answer="Resposta normal sem diff",
            citations=[],
            query_original="O que mudou?",
            query_rewritten="What changed?",
            total_sources=0,
            model_used="gpt-4o",
        )

        response = await async_client.post("/api/v1/chat/ask", json={"question": "O que mudou no manual?"})

    assert response.status_code == 200
    # generate_response foi chamado com version_diff=None (fallback)
    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs.get("version_diff") is None


@pytest.mark.asyncio
async def test_normal_query_unaffected(async_client):
    """Query normal não aciona o pipeline de comparação."""
    mock_rewritten = MagicMock()
    mock_rewritten.needs_clarification = False
    mock_rewritten.clarification_question = None
    mock_rewritten.query_en = "How to replace roller"
    mock_rewritten.doc_type = "manual"
    mock_rewritten.equipment_hint = None
    mock_rewritten.is_comparison_query = False  # Não é comparação

    with patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=mock_rewritten), \
         patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[_make_search_result()]) as mock_search, \
         patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None), \
         patch("app.api.chat.compare_versions", new_callable=AsyncMock) as mock_compare, \
         patch("app.api.chat.generate_response", new_callable=AsyncMock) as mock_gen, \
         patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock), \
         patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=uuid4()), \
         patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock, return_value=uuid4()), \
         patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=[]), \
         patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock, return_value={}):

        mock_gen.return_value = MagicMock(
            answer="Resposta normal",
            citations=[],
            query_original="Como trocar o rolo?",
            query_rewritten="How to replace roller",
            total_sources=0,
            model_used="gpt-4o",
        )

        response = await async_client.post("/api/v1/chat/ask", json={"question": "Como trocar o rolo?"})

    assert response.status_code == 200
    # Comparador nunca chamado para query normal
    mock_compare.assert_not_called()
    # hybrid_search chamado sem include_all_versions=True
    search_kwargs = mock_search.call_args.kwargs
    assert search_kwargs.get("include_all_versions", False) is False
```

- [ ] **Step 5.2: Rodar os testes para confirmar que falham**

```bash
python -m pytest tests/integration/test_chat_version_comparison.py -v
```

Esperado: `FAILED` — `chat.py` ainda não tem a lógica de comparação.

- [ ] **Step 5.3: Implementar em `chat.py`**

**Passo A — Imports** (no topo do arquivo):
```python
from app.services.version_comparator import (
    VersionDiff,
    compare_versions,
    detect_multi_version,
    group_chunks_by_version,
)
```

**Passo B — Bypass de cache** (ATENÇÃO: o bloco de cache em `chat.py` está na linha ~185, ANTES de `rewrite_query()` na linha ~225. É preciso MOVER o bloco de cache para depois do `rewrite_query`, não apenas editar in-place):

Localizar o bloco atual (linha ~184):
```python
    # Verificar semantic cache (respostas aprovadas anteriormente)
    cached = await get_cached_response(db, question)
    if cached:
        ...
        return ChatResponse(...)
```

**1. Deletar esse bloco inteiro** do local atual (antes de `rewrite_query`).

**2. Após** a linha `rewritten = await rewrite_query(...)` e o bloco de `logger.info`, **inserir**:
```python
    # Verificar semantic cache — bypass para queries de comparação (diff muda com novas versões)
    cached = None
    if not rewritten.is_comparison_query:
        cached = await get_cached_response(db, question)
    if cached:
        logger.info(f"[{user.id}] Cache HIT — retornando resposta cacheada")
        cached_metadata = {
            "query_rewritten": cached["query_rewritten"],
            "total_sources": len(cached["citations"]),
            "model_used": cached["model_used"],
        }
        assistant_msg_id = await chat_repository.add_message(
            db, session_id, "assistant", cached["answer"],
            citations=cached["citations"], metadata=cached_metadata,
        )
        cached_citations = [
            CitationResponse(
                source_index=c.get("source_index", 0),
                source_filename=c.get("source_filename", ""),
                page_number=c.get("page_number", 0),
                equipment_key=c.get("equipment_key"),
                doc_type=c.get("doc_type"),
                published_date=c.get("published_date", ""),
                storage_path=c.get("storage_path", ""),
                document_version_id=c.get("document_version_id", ""),
            )
            for c in cached["citations"]
        ] if cached["citations"] else []
        background_tasks.add_task(_maybe_update_summary, session_id)
        return ChatResponse(
            answer=cached["answer"],
            citations=cached_citations,
            query_original=question,
            query_rewritten=cached["query_rewritten"],
            total_sources=len(cached_citations),
            model_used=cached["model_used"],
            session_id=str(session_id),
            message_id=str(assistant_msg_id),
        )
```

**Passo C — Passar `include_all_versions` para `hybrid_search`**:

Encontrar a chamada de `hybrid_search` (no bloco `else:` do diagnóstico):
```python
results = await hybrid_search(
    db=db,
    query_en=rewritten.query_en,
    query_original=question,
    limit=8,
    doc_type=rewritten.doc_type,
    equipment_key=equipment_filter,
)
```

Substituir por:
```python
results = await hybrid_search(
    db=db,
    query_en=rewritten.query_en,
    query_original=question,
    limit=8,
    doc_type=rewritten.doc_type,
    equipment_key=equipment_filter,
    include_all_versions=rewritten.is_comparison_query,
)
```

**Passo D — Orquestração do comparador** (adicionar APÓS o bloco de busca e ANTES de `generate_response`):

```python
# Pipeline de comparação de versões (opcional — fallback se falhar)
version_diff = None
try:
    if rewritten.is_comparison_query and detect_multi_version(results):
        grouped = group_chunks_by_version(results)
        version_diff = await compare_versions(grouped)
        logger.info(
            f"Version diff: {version_diff.version_old} → {version_diff.version_new} | "
            f"has_changes={version_diff.has_changes} | items={len(version_diff.diff_items)}"
        )
except Exception as exc:
    logger.warning(f"Comparação de versões falhou, seguindo sem diff: {exc}")
    version_diff = None
```

**Passo E — Atualizar chamada de `generate_response`**:
```python
rag_response = await generate_response(
    question=question,
    query_rewritten=rewritten.query_en,
    search_results=results,
    history_messages=history_messages,
    history_summary=history_summary,
    diagnostic_mode=diagnostic_mode,
    version_diff=version_diff,                        # NOVO
    is_comparison_query=rewritten.is_comparison_query, # NOVO
)
```

- [ ] **Step 5.4: Rodar todos os testes**

```bash
python -m pytest tests/ -v --tb=short
```

Esperado: todos `PASSED`. Se algum teste de integração existente falhar, verifique se as mocks do `generate_response` incluem os novos parâmetros opcionais — eles não precisam ser passados explicitamente pois têm defaults.

- [ ] **Step 5.5: Commit**

```bash
git add backend/app/api/chat.py backend/tests/integration/test_chat_version_comparison.py
git commit -m "feat(IA-compare): chat.py — orquestração de comparação de versões + bypass de cache"
```

---

## Task 6: Validação da suíte completa

Confirmar que nenhum teste existente quebrou e que todos os novos passam.

**Files:** nenhum

- [ ] **Step 6.1: Rodar a suíte completa**

```bash
cd /Users/arthurbueno/HaruCode/apps/kyotech-ai/backend
python -m pytest tests/ -v --tb=short 2>&1 | tail -40
```

Esperado: todos `PASSED`. Nenhum `FAILED` ou `ERROR`.

- [ ] **Step 6.2: Verificar cobertura dos novos arquivos**

```bash
python -m pytest tests/unit/test_version_comparator.py tests/integration/test_chat_version_comparison.py -v
```

Esperado: 11 testes passando (7 unitários + 3 integração + 1 de cache bypass).

- [ ] **Step 6.3: Commit final**

```bash
git add -A
git commit -m "test(IA-compare): validação completa — todos os testes passando"
```

---

## Observações para Validação Manual (Pós-Implementação)

Após a implementação, validar com documentos reais:

1. Ingerir duas versões do mesmo manual (ex: Frontier-780 julho/2024 e janeiro/2025)
2. Perguntar: *"O que mudou no manual do Frontier 780 entre as versões?"*
3. Verificar que a resposta contém a seção `## Diferenças entre versões`
4. Verificar que as datas de versão batem com os documentos ingeridos
5. Medir a latência adicional com logs: procurar `Version diff:` no log do servidor
