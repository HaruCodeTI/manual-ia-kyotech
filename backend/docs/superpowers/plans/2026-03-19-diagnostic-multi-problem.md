# IA-89: RAG Avançado — Diagnóstico Multi-Problema — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detectar perguntas com múltiplos sintomas e retornar resposta diagnóstica estruturada (3 seções) usando buscas híbridas paralelas por sub-problema.

**Architecture:** Novo serviço `diagnostic_analyzer.py` detecta (regex) e decompõe (gpt-4o-mini) multi-problemas. `generator.py` ganha `diagnostic_mode` com prompt estruturado. `chat.py` orquestra o pipeline diagnóstico dentro de `try/except` — sem mudança de contrato da API.

**Tech Stack:** Python 3.11, FastAPI, AsyncIO, OpenAI SDK (Azure), pytest, unittest.mock

---

## Mapa de Arquivos

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `app/services/diagnostic_analyzer.py` | Criar | Detecção regex + decomposição gpt-4o-mini |
| `app/services/generator.py` | Modificar | Adicionar `DIAGNOSTIC_SYSTEM_PROMPT` + `diagnostic_mode` |
| `app/api/chat.py` | Modificar | Orquestrar pipeline diagnóstico com fallback |
| `tests/unit/test_diagnostic_analyzer.py` | Criar | Testes unitários do novo serviço |
| `tests/unit/test_generator.py` | Modificar | Adicionar testes de `diagnostic_mode` |
| `tests/integration/test_chat_api.py` | Modificar | Adicionar testes de integração diagnóstico |

---

## Task 1: `diagnostic_analyzer.py` — Detecção e Decomposição

**Files:**
- Create: `app/services/diagnostic_analyzer.py`
- Create: `tests/unit/test_diagnostic_analyzer.py`

**Contexto:** Este é o coração da feature. Duas funções com responsabilidades distintas: `is_diagnostic_query` (regex puro, sem LLM, roda em toda pergunta) e `decompose_problems` (gpt-4o-mini, só chamado quando detecção confirma multi-problema).

Padrão de mock do LLM usado no projeto (ver `tests/unit/test_query_rewriter.py`):
```python
@pytest.fixture(autouse=True)
def _patch_openai_client():
    mock_client = AsyncMock()
    with patch("app.services.diagnostic_analyzer.get_openai_client", return_value=mock_client):
        yield mock_client
```

---

- [ ] **Step 1: Escrever testes que falham para `is_diagnostic_query`**

Criar `tests/unit/test_diagnostic_analyzer.py`:

```python
"""Tests for app.services.diagnostic_analyzer."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.diagnostic_analyzer import decompose_problems, is_diagnostic_query


class TestIsDiagnosticQuery:
    def test_two_weak_patterns_activates(self):
        # "e também" + "também" → 2 weak matches → True
        assert is_diagnostic_query("Não imprime e também trava, também dá erro") is True

    def test_e_tambem_with_second_weak_activates(self):
        assert is_diagnostic_query("O papel não alimenta e também além disso dá erro") is True

    def test_single_tambem_does_not_activate(self):
        # Apenas 1 padrão fraco → False
        assert is_diagnostic_query("Também quero saber a torque do parafuso") is False

    def test_enumeration_strong_pattern_activates(self):
        # "1. sintoma 2. sintoma" — padrão forte, ativa sozinho
        assert is_diagnostic_query("1. não imprime 2. dá erro E-05") is True

    def test_comma_list_strong_pattern_activates(self):
        # 3+ itens substanciais separados por vírgula
        assert is_diagnostic_query(
            "não alimenta o papel, apresenta erro E-05 na tela, trava no final"
        ) is True

    def test_simple_question_does_not_activate(self):
        assert is_diagnostic_query("Como trocar o rolo de pressão da Frontier 780?") is False

    def test_empty_string_does_not_activate(self):
        assert is_diagnostic_query("") is False

    def test_single_symptom_does_not_activate(self):
        assert is_diagnostic_query("O papel está atolando na entrada") is False
```

- [ ] **Step 2: Rodar e confirmar falha**

```bash
pytest tests/unit/test_diagnostic_analyzer.py -v 2>&1 | head -20
```

Esperado: `ImportError: cannot import name 'is_diagnostic_query' from 'app.services.diagnostic_analyzer'`

- [ ] **Step 3: Implementar `is_diagnostic_query`**

Criar `app/services/diagnostic_analyzer.py`:

```python
"""
Kyotech AI — Diagnóstico Multi-Problema
Detecta perguntas com múltiplos sintomas e decompõe em sub-queries para busca paralela.
"""
from __future__ import annotations

import json
import logging
import re
from typing import List

from app.services.embedder import get_openai_client
from app.core.config import settings

logger = logging.getLogger(__name__)

# Padrões "fracos" — precisam de 2+ matches para ativar
_WEAK_PATTERNS = [
    re.compile(r'\be também\b', re.IGNORECASE),
    re.compile(r'\balém disso\b', re.IGNORECASE),
    re.compile(r'\bao mesmo tempo\b', re.IGNORECASE),
    re.compile(r'\be mais\b', re.IGNORECASE),
    re.compile(r'\btambém\b', re.IGNORECASE),
]

# Padrões "fortes" — ativam sozinhos
_STRONG_PATTERNS = [
    re.compile(r'\b\d+[\.\)]\s+\w.{5,}\b\d+[\.\)]\s+', re.IGNORECASE | re.DOTALL),
    re.compile(r'(?:[^,]{10,},){2,}', re.IGNORECASE),
]

_DECOMPOSE_PROMPT = """You are a technical query decomposer for Fujifilm equipment.
The technician described multiple problems in one message.

Your job: decompose the message into 2–4 independent technical search queries IN ENGLISH.
Each query should be specific and searchable in a Fujifilm service manual.

Respond ONLY with a JSON array of strings, no markdown:
["search query 1", "search query 2"]"""


def is_diagnostic_query(question: str) -> bool:
    """
    Detecta perguntas com múltiplos sintomas via regex (sem LLM).
    Retorna True se:
      - qualquer padrão forte bater, OU
      - 2 ou mais padrões fracos baterem.
    """
    if not question:
        return False
    if any(p.search(question) for p in _STRONG_PATTERNS):
        return True
    weak_count = sum(1 for p in _WEAK_PATTERNS if p.search(question))
    return weak_count >= 2
```

- [ ] **Step 4: Rodar testes de detecção**

```bash
pytest tests/unit/test_diagnostic_analyzer.py::TestIsDiagnosticQuery -v
```

Esperado: todos PASS.

- [ ] **Step 5: Escrever testes que falham para `decompose_problems`**

Adicionar ao final de `tests/unit/test_diagnostic_analyzer.py`:

```python
def _make_chat_response(content: str):
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture(autouse=True)
def _patch_openai_client():
    mock_client = AsyncMock()
    with patch("app.services.diagnostic_analyzer.get_openai_client", return_value=mock_client):
        yield mock_client


class TestDecomposeProblems:
    @pytest.mark.asyncio
    async def test_valid_json_returns_list(self, _patch_openai_client):
        sub_queries = ["paper jam troubleshooting", "E-05 error code diagnosis"]
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(sub_queries))
        )
        result = await decompose_problems("Atola papel e dá erro E-05")
        assert isinstance(result, list)
        assert result == sub_queries

    @pytest.mark.asyncio
    async def test_invalid_json_falls_back_to_original(self, _patch_openai_client):
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response("não é json válido")
        )
        question = "Atola papel e dá erro E-05"
        result = await decompose_problems(question)
        assert result == [question]

    @pytest.mark.asyncio
    async def test_single_item_returned_as_is(self, _patch_openai_client):
        # 1 item → continua em modo diagnóstico (não faz fallback para original)
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(["paper jam troubleshooting"]))
        )
        result = await decompose_problems("Atola papel")
        assert result == ["paper jam troubleshooting"]

    @pytest.mark.asyncio
    async def test_max_4_items_enforced(self, _patch_openai_client):
        many = ["q1", "q2", "q3", "q4", "q5", "q6"]
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(many))
        )
        result = await decompose_problems("pergunta com muitos problemas")
        assert len(result) <= 4

    @pytest.mark.asyncio
    async def test_uses_correct_model(self, _patch_openai_client):
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(["q1"]))
        )
        await decompose_problems("pergunta")
        call_kwargs = _patch_openai_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == settings.azure_openai_mini_deployment
```

- [ ] **Step 6: Rodar e confirmar falha**

```bash
pytest tests/unit/test_diagnostic_analyzer.py::TestDecomposeProblems -v 2>&1 | head -10
```

Esperado: `FAIL` — `decompose_problems` não existe ainda.

- [ ] **Step 7: Implementar `decompose_problems`**

Adicionar ao final de `app/services/diagnostic_analyzer.py`:

```python
async def decompose_problems(question: str) -> List[str]:
    """
    Decompõe uma pergunta multi-problema em 2-4 sub-queries em inglês.
    Usa gpt-4o-mini. Fallback para [question] se parse falhar.
    Propaga exceções de rede/timeout — tratadas pelo caller em chat.py.
    """
    client = get_openai_client()
    response = await client.chat.completions.create(
        model=settings.azure_openai_mini_deployment,
        messages=[
            {"role": "system", "content": _DECOMPOSE_PROMPT},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
        max_tokens=200,
    )
    raw = response.choices[0].message.content.strip()
    logger.info(f"Decomposição: '{question}' → {raw}")

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list) or not parsed:
            return [question]
        return [str(q) for q in parsed[:4]]
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Falha no parse da decomposição: {e}. Usando query original.")
        return [question]
```

- [ ] **Step 8: Rodar todos os testes do arquivo**

```bash
pytest tests/unit/test_diagnostic_analyzer.py -v
```

Esperado: todos PASS.

- [ ] **Step 9: Rodar suite completa para checar regressão**

```bash
pytest tests/unit/ -v --tb=short 2>&1 | tail -20
```

Esperado: todos PASS.

- [ ] **Step 10: Commit**

```bash
git add app/services/diagnostic_analyzer.py tests/unit/test_diagnostic_analyzer.py
git commit -m "feat(IA-89): diagnostic_analyzer.py — detecção regex + decomposição gpt-4o-mini"
```

---

## Task 2: `generator.py` — Modo Diagnóstico

**Files:**
- Modify: `app/services/generator.py`
- Modify: `tests/unit/test_generator.py`

**Contexto:** `generator.py` atual tem `SYSTEM_PROMPT` e `generate_response(question, query_rewritten, search_results, history_messages, history_summary)`. Vamos adicionar `DIAGNOSTIC_SYSTEM_PROMPT` (constante de módulo) e `diagnostic_mode: bool = False` como último parâmetro de `generate_response`. O pipeline existente não é afetado quando `diagnostic_mode=False`.

Leia `app/services/generator.py` antes de modificar. Leia `tests/unit/test_generator.py` para entender o padrão de mock existente (fixture `_patch_openai_client`).

---

- [ ] **Step 1: Escrever testes que falham**

Adicionar ao final de `tests/unit/test_generator.py`. O helper `_make_llm_response` precisa ser definido no arquivo (verifique se já existe um helper similar — se existir use o mesmo nome; se não existir, adicione antes da classe):

```python
def _make_llm_response(content: str):
    """Helper para mockar resposta do LLM em test_generator.py."""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestDiagnosticMode:
    @pytest.mark.asyncio
    async def test_diagnostic_mode_uses_diagnostic_prompt(self, _patch_openai_client):
        """diagnostic_mode=True → system message contém 'Análise dos Sintomas'."""
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_llm_response("## Análise dos Sintomas\nTexto [Fonte 1].\n## Possíveis Causas\nCausas.\n## Próximos Passos\nPassos.")
        )
        await generate_response(
            question="Atola papel e dá erro E-05",
            query_rewritten="paper jam and E-05 error",
            search_results=[_make_result()],
            diagnostic_mode=True,
        )
        call_kwargs = _patch_openai_client.chat.completions.create.call_args[1]
        system_content = call_kwargs["messages"][0]["content"]
        assert "Análise dos Sintomas" in system_content

    @pytest.mark.asyncio
    async def test_diagnostic_mode_uses_2500_tokens(self, _patch_openai_client):
        """diagnostic_mode=True → max_tokens=2500."""
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_llm_response("resposta diagnóstica [Fonte 1]")
        )
        await generate_response(
            question="pergunta",
            query_rewritten="query",
            search_results=[_make_result()],
            diagnostic_mode=True,
        )
        call_kwargs = _patch_openai_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 2500

    @pytest.mark.asyncio
    async def test_normal_mode_uses_1500_tokens(self, _patch_openai_client):
        """diagnostic_mode=False (default) → max_tokens=1500."""
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_llm_response("resposta normal [Fonte 1]")
        )
        await generate_response(
            question="pergunta",
            query_rewritten="query",
            search_results=[_make_result()],
        )
        call_kwargs = _patch_openai_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 1500

    @pytest.mark.asyncio
    async def test_normal_mode_uses_original_prompt(self, _patch_openai_client):
        """diagnostic_mode=False → system message NÃO contém 'Análise dos Sintomas'."""
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_llm_response("resposta normal [Fonte 1]")
        )
        await generate_response(
            question="pergunta",
            query_rewritten="query",
            search_results=[_make_result()],
        )
        call_kwargs = _patch_openai_client.chat.completions.create.call_args[1]
        system_content = call_kwargs["messages"][0]["content"]
        assert "Análise dos Sintomas" not in system_content
```

Nota: o fixture `_patch_openai_client` já existe em `test_generator.py` — não duplicar.

- [ ] **Step 2: Rodar e confirmar falha**

```bash
pytest tests/unit/test_generator.py::TestDiagnosticMode -v 2>&1 | head -15
```

Esperado: `FAIL` — `generate_response` não aceita `diagnostic_mode`.

- [ ] **Step 3: Adicionar `DIAGNOSTIC_SYSTEM_PROMPT` em `generator.py`**

Após a constante `SYSTEM_PROMPT` existente, adicionar:

```python
DIAGNOSTIC_SYSTEM_PROMPT = """Você é o assistente técnico da Kyotech, especializado em diagnóstico de equipamentos Fujifilm.
O técnico relatou múltiplos sintomas. Analise cada um separadamente antes de sugerir causas.

PERSONALIDADE:
- Tom profissional mas acolhedor — trate o técnico como um colega
- Seja direto e estruturado — diagnósticos precisam de clareza

REGRAS OBRIGATÓRIAS:
1. Responda SEMPRE em português brasileiro
2. Use APENAS as informações dos trechos fornecidos — NUNCA invente
3. Para cada afirmação, cite a fonte usando EXATAMENTE o formato [Fonte N] com colchetes
4. Se a informação não está nos trechos, diga explicitamente
5. Se houver conflito entre fontes, mencione ambas versões e indique a mais recente

FORMATO OBRIGATÓRIO DA RESPOSTA:
## Análise dos Sintomas
[Aborde cada sintoma individualmente com citações [Fonte N]]

## Possíveis Causas
[Causas em comum entre os sintomas, ou causas independentes com citações [Fonte N]]

## Próximos Passos
[Procedimentos em ordem de prioridade com citações [Fonte N]]

NÃO liste as fontes ao final — o sistema exibe as fontes automaticamente."""
```

- [ ] **Step 4: Modificar assinatura de `generate_response`**

Localizar a linha de definição da função `generate_response` e adicionar o parâmetro `diagnostic_mode`:

```python
async def generate_response(
    question: str,
    query_rewritten: str,
    search_results: List[SearchResult],
    history_messages: Optional[List[Dict[str, str]]] = None,
    history_summary: Optional[str] = None,
    diagnostic_mode: bool = False,
) -> RAGResponse:
```

- [ ] **Step 5: Usar o prompt e tokens corretos conforme `diagnostic_mode`**

Dentro de `generate_response`, localizar onde `messages` é montado e onde `max_tokens` é passado. Substituir:

```python
    # Antes:
    messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    # ...
    response = await client.chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=messages,
        temperature=0.2,
        max_tokens=1500,
    )

    # Depois:
    system_prompt = DIAGNOSTIC_SYSTEM_PROMPT if diagnostic_mode else SYSTEM_PROMPT
    max_tokens = 2500 if diagnostic_mode else 1500
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    # ... (resto da montagem das mensagens inalterado)
    response = await client.chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=messages,
        temperature=0.2,
        max_tokens=max_tokens,
    )
```

- [ ] **Step 6: Rodar testes de `diagnostic_mode`**

```bash
pytest tests/unit/test_generator.py -v
```

Esperado: todos PASS (incluindo os testes anteriores que não devem regredir).

- [ ] **Step 7: Rodar suite completa**

```bash
pytest tests/unit/ -v --tb=short 2>&1 | tail -20
```

Esperado: todos PASS.

- [ ] **Step 8: Commit**

```bash
git add app/services/generator.py tests/unit/test_generator.py
git commit -m "feat(IA-89): generator.py — DIAGNOSTIC_SYSTEM_PROMPT + diagnostic_mode"
```

---

## Task 3: `chat.py` — Orquestração do Pipeline Diagnóstico

**Files:**
- Modify: `app/api/chat.py`
- Modify: `tests/integration/test_chat_api.py`

**Contexto:** Esta task integra tudo. Leia `app/api/chat.py` completo antes de modificar — especialmente o bloco após o early exit de clarificação e antes do `hybrid_search`. O pipeline diagnóstico vai nesse exato ponto, envolto em `try/except`.

Leia `tests/integration/test_chat_api.py` para entender o padrão de patches usados (múltiplos `patch()` como context managers em `with (...):` aninhados).

---

- [ ] **Step 1: Escrever testes que falham**

Adicionar ao final de `tests/integration/test_chat_api.py`:

```python
@pytest.mark.anyio
async def test_diagnostic_query_calls_hybrid_search_twice(async_client):
    """Pergunta diagnóstica → hybrid_search chamado 2 vezes (uma por sub-query)."""
    session_id = uuid4()

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.is_diagnostic_query", return_value=True),
        patch(
            "app.api.chat.decompose_problems",
            new_callable=AsyncMock,
            return_value=["paper jam diagnosis", "E-05 error code"],
        ),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]) as mock_search,
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock, return_value=uuid4()),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        response = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "Atola papel e também dá erro E-05"},
        )

    assert response.status_code == 200
    assert mock_search.await_count == 2


@pytest.mark.anyio
async def test_simple_query_calls_hybrid_search_once(async_client):
    """Pergunta simples → hybrid_search chamado 1 vez."""
    session_id = uuid4()

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.is_diagnostic_query", return_value=False),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]) as mock_search,
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock, return_value=uuid4()),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        response = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "Como trocar o rolo de pressão?"},
        )

    assert response.status_code == 200
    assert mock_search.await_count == 1


@pytest.mark.anyio
async def test_diagnostic_fallback_on_decompose_exception(async_client):
    """Exceção em decompose_problems → fallback para pipeline normal, HTTP 200."""
    session_id = uuid4()

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.is_diagnostic_query", return_value=True),
        patch(
            "app.api.chat.decompose_problems",
            new_callable=AsyncMock,
            side_effect=RuntimeError("timeout"),
        ),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]) as mock_search,
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock, return_value=uuid4()),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        response = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "Atola papel e também dá erro"},
        )

    assert response.status_code == 200
    # Fallback: hybrid_search chamado 1 vez com query original
    assert mock_search.await_count == 1


@pytest.mark.anyio
async def test_diagnostic_query_rewritten_is_original_rewrite(async_client):
    """query_rewritten no response é sempre rewritten.query_en, não as sub-queries."""
    session_id = uuid4()
    rewritten = _make_rewritten()  # query_en = "how to replace the pressure roller"

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=rewritten),
        patch("app.api.chat.is_diagnostic_query", return_value=True),
        patch(
            "app.api.chat.decompose_problems",
            new_callable=AsyncMock,
            return_value=["sub-query 1", "sub-query 2"],
        ),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock, return_value=uuid4()),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        response = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "Atola papel e também dá erro"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["query_rewritten"] == rewritten.query_en
    assert "sub-query 1" not in data["query_rewritten"]
```

- [ ] **Step 2: Rodar e confirmar falha**

```bash
pytest tests/integration/test_chat_api.py::test_diagnostic_query_calls_hybrid_search_twice -v 2>&1 | head -20
```

Esperado: `FAIL` — `app.api.chat` não tem `is_diagnostic_query` importado.

- [ ] **Step 3: Adicionar imports em `chat.py`**

No topo de `app/api/chat.py`, adicionar as importações:

```python
import asyncio

from app.services.diagnostic_analyzer import decompose_problems, is_diagnostic_query
from app.services.search import hybrid_search, SearchResult
```

**Atenção:** `hybrid_search` já está importado (`from app.services.search import hybrid_search`). Substituir essa linha pela acima para adicionar `SearchResult`. `asyncio` é da biblioteca padrão — verificar se já está importado antes de duplicar.

- [ ] **Step 4: Substituir o bloco `hybrid_search` em `chat.py`**

Localizar o trecho em `ask_question` onde `equipment_filter` é definido e `hybrid_search` é chamado. Substituir por:

```python
    equipment_filter = request.equipment_filter or rewritten.equipment_hint

    diagnostic_mode = False
    try:
        if is_diagnostic_query(question):
            sub_queries = await decompose_problems(question)
            per_query_limit = max(4, 8 // len(sub_queries))
            all_results = await asyncio.gather(*[
                hybrid_search(
                    db=db,
                    query_en=q,
                    query_original=question,
                    limit=per_query_limit,
                    doc_type=rewritten.doc_type,
                    equipment_key=equipment_filter,
                )
                for q in sub_queries
            ])
            merged: dict[str, SearchResult] = {}
            for batch in all_results:
                for r in batch:
                    if r.chunk_id not in merged or r.similarity > merged[r.chunk_id].similarity:
                        merged[r.chunk_id] = r
            results = sorted(merged.values(), key=lambda r: r.similarity, reverse=True)[:8]
            diagnostic_mode = True
            logger.info(f"Pipeline diagnóstico: {len(sub_queries)} sub-queries, {len(results)} resultados fundidos")
        else:
            results = await hybrid_search(
                db=db,
                query_en=rewritten.query_en,
                query_original=question,
                limit=8,
                doc_type=rewritten.doc_type,
                equipment_key=equipment_filter,
            )
    except Exception as exc:
        logger.warning(f"Falha no pipeline diagnóstico, usando pipeline normal: {exc}")
        results = await hybrid_search(
            db=db,
            query_en=rewritten.query_en,
            query_original=question,
            limit=8,
            doc_type=rewritten.doc_type,
            equipment_key=equipment_filter,
        )
        diagnostic_mode = False

    logger.info(f"Resultados encontrados: {len(results)}")
```

- [ ] **Step 5: Remover a linha `results = await hybrid_search(...)` antiga**

Certificar-se de que o `hybrid_search` original (sem diagnóstico) foi removido — não deixar duplicado. Verificar também que `logger.info(f"Resultados encontrados: {len(results)}")` não ficou duplicado.

- [ ] **Step 6: Passar `diagnostic_mode` para `generate_response`**

Localizar a chamada `rag_response = await generate_response(...)` e adicionar o parâmetro:

```python
    rag_response = await generate_response(
        question=question,
        query_rewritten=rewritten.query_en,
        search_results=results,
        history_messages=history_messages,
        history_summary=history_summary,
        diagnostic_mode=diagnostic_mode,
    )
```

- [ ] **Step 7: Rodar os novos testes de integração**

```bash
pytest tests/integration/test_chat_api.py -k "diagnostic" -v
```

Esperado: todos os 4 novos testes PASS.

- [ ] **Step 8: Rodar suite completa de integração**

```bash
pytest tests/integration/test_chat_api.py -v --tb=short 2>&1 | tail -30
```

Esperado: todos PASS (testes anteriores não devem regredir).

- [ ] **Step 9: Rodar suite completa**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Esperado: todos PASS.

- [ ] **Step 10: Commit**

```bash
git add app/api/chat.py tests/integration/test_chat_api.py
git commit -m "feat(IA-89): chat.py — pipeline diagnóstico com fallback + testes de integração"
```

---

## Verificação Final

- [ ] **Rodar suite completa uma última vez**

```bash
pytest tests/ -v 2>&1 | tail -5
```

Esperado: `N passed, 0 failed`.

- [ ] **Push para main**

```bash
git push origin main
```

- [ ] **Testar manualmente em produção**

Perguntar no chat:
1. `"O equipamento não alimenta papel e também dá erro E-05 na tela"` → esperar resposta com 3 seções (Análise / Causas / Próximos Passos)
2. `"Como trocar o rolo de pressão da Frontier 780?"` → esperar resposta normal (sem seções)

Verificar logs: buscar `"Pipeline diagnóstico: N sub-queries"` para confirmar ativação.
