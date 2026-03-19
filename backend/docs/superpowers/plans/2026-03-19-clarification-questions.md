# Clarification Questions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O assistente detecta perguntas ambíguas (via rewriter) ou resultados fracos (via score RAG) e responde com uma pergunta de clarificação ao invés de uma resposta de baixa confiança.

**Architecture:** O `query_rewriter` detecta ambiguidade na mesma chamada LLM existente e retorna `needs_clarification=True`. Se o score do melhor resultado RAG for abaixo de `CLARIFICATION_THRESHOLD=0.45`, retorna clarificação determinística. Ambos os casos salvam a mensagem de clarificação no banco e retornam `ChatResponse(needs_clarification=True)`.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, OpenAI gpt-4o-mini, pytest + AsyncMock

**PRÉ-REQUISITO:** Memória de Conversa (IA-103) deve estar implementada. Em particular: `BackgroundTasks` já injetado em `ask_question`, `_maybe_update_summary` já existe.

---

## Mapa de arquivos

| Arquivo | Ação | Responsabilidade |
|---------|------|-----------------|
| `app/services/query_rewriter.py` | Modificar | `RewrittenQuery` + 2 campos; prompt regras 6-7; `max_tokens` 200→300 |
| `app/services/generator.py` | Modificar | Nova função `build_clarification_from_weak_results` |
| `app/api/chat.py` | Modificar | `CLARIFICATION_THRESHOLD`; 2 pontos de saída; `needs_clarification` em `ChatResponse` |
| `tests/unit/test_query_rewriter.py` | Modificar | 3 novos cenários |
| `tests/unit/test_generator.py` | Modificar | 1 novo cenário |
| `tests/integration/test_chat_api.py` | Modificar | Atualizar `_make_rewritten()`; 4 novos cenários |

---

## Task 1: query_rewriter.py — needs_clarification + clarification_question

**Files:**
- Modify: `backend/app/services/query_rewriter.py`
- Test: `backend/tests/unit/test_query_rewriter.py`

- [ ] **Step 1: Escrever os testes falhando**

**ATENÇÃO:** O arquivo `tests/unit/test_query_rewriter.py` tem uma fixture `autouse=True` (`_patch_openai_client`) que já faz o patch de `get_openai_client`. NÃO usar `with patch(...)` interno. Adicionar ao final da classe `TestRewriteQuery`, usando `_patch_openai_client` como parâmetro e `_make_chat_response` (já definido no arquivo) como helper.

Adicionar ao final da classe `TestRewriteQuery` em `tests/unit/test_query_rewriter.py`:

```python
    @pytest.mark.asyncio
    async def test_rewrite_ambiguous_procedure_no_equipment(self, _patch_openai_client):
        """Pergunta de procedimento sem equipamento → needs_clarification=True."""
        payload = {
            "query_en": "pressure roller replacement",
            "doc_type": "manual",
            "equipment_hint": None,
            "needs_clarification": True,
            "clarification_question": "Para qual equipamento você está buscando essa informação?",
        }
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(payload))
        )
        result = await rewrite_query("Como trocar o rolo de pressão?")
        assert result.needs_clarification is True
        assert result.clarification_question is not None
        assert len(result.clarification_question) > 0

    @pytest.mark.asyncio
    async def test_rewrite_clear_question_no_clarification(self, _patch_openai_client):
        """Pergunta clara com equipamento → needs_clarification=False."""
        payload = {
            "query_en": "pressure roller Frontier-780 replacement",
            "doc_type": "manual",
            "equipment_hint": "frontier-780",
            "needs_clarification": False,
            "clarification_question": None,
        }
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(payload))
        )
        result = await rewrite_query("Como trocar o rolo do Frontier-780?")
        assert result.needs_clarification is False
        assert result.clarification_question is None

    @pytest.mark.asyncio
    async def test_rewrite_parse_error_defaults_to_no_clarification(self, _patch_openai_client):
        """Falha de parse → needs_clarification=False (fallback seguro)."""
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response("resposta inválida não é json")
        )
        result = await rewrite_query("pergunta qualquer")
        assert result.needs_clarification is False
        assert result.clarification_question is None
```

- [ ] **Step 2: Rodar e confirmar que falham**

```bash
cd backend
python -m pytest tests/unit/test_query_rewriter.py::test_rewrite_ambiguous_procedure_no_equipment -v
```

Expected: `AttributeError: 'RewrittenQuery' object has no attribute 'needs_clarification'`

- [ ] **Step 3: Implementar em query_rewriter.py**

**3a. Estender o dataclass:**

```python
@dataclass
class RewrittenQuery:
    original: str
    query_en: str
    doc_type: Optional[str]
    equipment_hint: Optional[str]
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
```

**3b. Atualizar `REWRITE_PROMPT` — adicionar regras 6 e 7 e atualizar o JSON de saída:**

```python
REWRITE_PROMPT = """You are a technical assistant for Fujifilm printing equipment.
Your job is to rewrite a technician's question (in Portuguese) into an optimized English search query.

Rules:
1. Translate to English
2. Use technical terms that would appear in Fujifilm service manuals
3. Keep the query focused and specific (max 2-3 sentences)
4. Classify the query as "manual" (procedures, specs, parts) or "informativo" (bulletins, updates, known issues)
5. If the question mentions a specific equipment model, extract it
6. Determine if the question needs clarification before searching.
   Set needs_clarification to true if ANY of these apply:
   - Procedure question (how to replace, torque spec, part location) with no equipment model mentioned
   - Symptom too generic to search (e.g. "doesn't work", "gives error", "stopped working")
   - Error code without any equipment or context
   If the question is clear enough to search, or if conversation history already provides
   the missing context, set needs_clarification to false.
7. If needs_clarification is true, write a short clarification question in Brazilian Portuguese.
   Be specific: ask for the missing information (equipment model, error code, symptom details).
   Keep it under 20 words. Example: "Para qual equipamento você está buscando essa informação?"

Respond ONLY with this JSON format, no markdown:
{"query_en": "...", "doc_type": "manual" or "informativo" or "both", "equipment_hint": "model name or null", "needs_clarification": false, "clarification_question": null}"""
```

**3c. Aumentar `max_tokens` de 200 para 300:**

```python
    response = await client.chat.completions.create(
        model=settings.azure_openai_mini_deployment,
        messages=[...],
        temperature=0.1,
        max_tokens=300,  # era 200
    )
```

**3d. Atualizar o parse para incluir os novos campos:**

```python
        return RewrittenQuery(
            original=question,
            query_en=parsed.get("query_en", question),
            doc_type=doc_type,
            equipment_hint=equipment,
            needs_clarification=parsed.get("needs_clarification", False),
            clarification_question=parsed.get("clarification_question"),
        )
```

O fallback `except (json.JSONDecodeError, KeyError)` já usa os defaults do dataclass → `needs_clarification=False` automaticamente.

- [ ] **Step 4: Rodar todos os testes do rewriter**

```bash
cd backend
python -m pytest tests/unit/test_query_rewriter.py -v
```

Expected: todos PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/query_rewriter.py tests/unit/test_query_rewriter.py
git commit -m "feat(rewriter): detecção de ambiguidade — needs_clarification + clarification_question"
```

---

## Task 2: generator.py + chat.py — clarificação por score + ChatResponse

**Files:**
- Modify: `backend/app/services/generator.py`
- Modify: `backend/app/api/chat.py`
- Test: `backend/tests/unit/test_generator.py`
- Test: `backend/tests/integration/test_chat_api.py`

- [ ] **Step 1: Escrever o teste unitário falhando**

Adicionar ao final de `tests/unit/test_generator.py`:

```python
def test_build_clarification_from_weak_results():
    from app.services.generator import build_clarification_from_weak_results
    result = build_clarification_from_weak_results("pergunta qualquer")
    assert isinstance(result, str)
    assert len(result) > 0
    # Deve ser em português
    assert any(word in result.lower() for word in ["encontrei", "detalhes", "equipamento", "precisas"])
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd backend
python -m pytest tests/unit/test_generator.py::test_build_clarification_from_weak_results -v
```

Expected: `ImportError: cannot import name 'build_clarification_from_weak_results'`

- [ ] **Step 3: Implementar `build_clarification_from_weak_results` em generator.py**

Adicionar após `build_context`:

```python
def build_clarification_from_weak_results(question: str) -> str:
    """
    Retorna pergunta de clarificação quando resultados RAG têm score fraco.
    Determinístico — não chama LLM.
    """
    return (
        "Não encontrei informações suficientemente precisas para responder com confiança. "
        "Poderia fornecer mais detalhes? Por exemplo: qual equipamento, "
        "código de erro exibido, ou em qual etapa do processo ocorre o problema?"
    )
```

- [ ] **Step 4: Rodar teste unitário**

```bash
cd backend
python -m pytest tests/unit/test_generator.py::test_build_clarification_from_weak_results -v
```

Expected: PASS

- [ ] **Step 5: Escrever os testes de integração falhando**

**5a. Atualizar `_make_rewritten` em `tests/integration/test_chat_api.py`** para incluir os novos campos:

```python
def _make_rewritten(question: str = "test question") -> RewrittenQuery:
    return RewrittenQuery(
        original=question,
        query_en="how to replace the pressure roller",
        doc_type="manual",
        equipment_hint=None,
        needs_clarification=False,
        clarification_question=None,
    )
```

**5b. Adicionar os 4 novos cenários ao final do arquivo:**

```python
@pytest.mark.anyio
async def test_clarification_from_rewriter(async_client):
    """rewrite_query retorna needs_clarification=True → retorna clarificação sem RAG."""
    from app.services.query_rewriter import RewrittenQuery
    clarification_rewritten = RewrittenQuery(
        original="Como trocar o rolo?",
        query_en="pressure roller replacement",
        doc_type="manual",
        equipment_hint=None,
        needs_clarification=True,
        clarification_question="Para qual equipamento você está buscando essa informação?",
    )
    session_id = uuid4()

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=clarification_rewritten),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock) as mock_search,
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "Como trocar o rolo?"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_clarification"] is True
    assert data["citations"] == []
    assert "equipamento" in data["answer"].lower()
    # RAG não deve ter sido chamado
    mock_search.assert_not_awaited()


@pytest.mark.anyio
async def test_clarification_from_weak_score(async_client):
    """Score do melhor resultado < 0.45 → retorna clarificação."""
    from app.services.search import SearchResult
    from datetime import date as dt

    weak_result = SearchResult(
        chunk_id="c1", content="texto", page_number=1, similarity=0.3,
        document_id="d1", doc_type="manual", equipment_key="equip-a",
        published_date=dt(2024, 1, 1), source_filename="f.pdf",
        storage_path="container/blob", search_type="vector",
        document_version_id="v1", quality_score=0.0,
    )
    session_id = uuid4()

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[weak_result]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock) as mock_gen,
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "não funciona"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_clarification"] is True
    assert data["citations"] == []
    # generate_response não deve ter sido chamado
    mock_gen.assert_not_awaited()


@pytest.mark.anyio
async def test_good_score_proceeds_normally(async_client):
    """Score >= 0.45 → pipeline normal, needs_clarification=False."""
    session_id = uuid4()

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()) as mock_gen,
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "Como trocar o rolo do Frontier-780?"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_clarification"] is False
    mock_gen.assert_awaited_once()


@pytest.mark.anyio
async def test_clarification_answer_proceeds_normally(async_client):
    """Sessão com clarificação anterior → resposta do técnico → RAG normal."""
    session_id = uuid4()
    history_with_clarification = [
        {"role": "user", "content": "Como trocar o rolo?"},
        {"role": "assistant", "content": "Para qual equipamento você está buscando essa informação?"},
        {"role": "user", "content": "Frontier-780"},
    ]

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()) as mock_rewrite,
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=history_with_clarification),
        patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock, return_value={"history_summary": None, "last_summarized_at": None}),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "Frontier-780", "session_id": str(session_id)},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_clarification"] is False
    # Verificar que rewrite_query recebeu o contexto da conversa
    call_kwargs = mock_rewrite.call_args.kwargs
    assert call_kwargs.get("conversation_context") is not None
```

- [ ] **Step 6: Rodar e confirmar que os novos testes falham**

```bash
cd backend
python -m pytest tests/integration/test_chat_api.py::test_clarification_from_rewriter -v
```

Expected: FAIL (`needs_clarification` não existe em `ChatResponse`)

- [ ] **Step 7: Implementar em chat.py**

**7a. Adicionar import:**
```python
from app.services.generator import generate_response, Citation, build_clarification_from_weak_results
```

**7b. Adicionar constante após os imports:**
```python
CLARIFICATION_THRESHOLD = 0.45
```

**7c. Adicionar `needs_clarification` ao `ChatResponse`:**
```python
class ChatResponse(BaseModel):
    answer: str
    citations: List[CitationResponse]
    query_original: str
    query_rewritten: str
    total_sources: int
    model_used: str
    session_id: str
    message_id: str
    needs_clarification: bool = False  # ← NOVO
```

**7d. Após `rewrite_query()` em `ask_question`, adicionar ponto de saída:**
```python
    rewritten = await rewrite_query(question, conversation_context=conversation_context)
    logger.info(
        f"Query reescrita: '{rewritten.query_en}' "
        f"(tipo: {rewritten.doc_type}, equip: {rewritten.equipment_hint}, "
        f"clarification: {rewritten.needs_clarification})"
    )

    # Ponto de saída 1: rewriter detectou ambiguidade
    if rewritten.needs_clarification and rewritten.clarification_question:
        clarification_msg_id = await chat_repository.add_message(
            db, session_id, "assistant", rewritten.clarification_question,
            metadata={"is_clarification": True},
        )
        background_tasks.add_task(_maybe_update_summary, session_id)
        return ChatResponse(
            answer=rewritten.clarification_question,
            citations=[],
            query_original=question,
            query_rewritten=rewritten.query_en,
            total_sources=0,
            model_used=settings.azure_openai_mini_deployment,
            session_id=str(session_id),
            message_id=str(clarification_msg_id),
            needs_clarification=True,
        )
```

**7e. Após `hybrid_search()`, adicionar ponto de saída por score fraco:**
```python
    results = await hybrid_search(
        db=db,
        query_en=rewritten.query_en,
        query_original=question,
        limit=8,
        doc_type=rewritten.doc_type,
        equipment_key=equipment_filter,
    )
    logger.info(f"Resultados encontrados: {len(results)}")

    # Ponto de saída 2: resultados fracos
    top_score = max((r.similarity for r in results), default=0.0)
    if results and top_score < CLARIFICATION_THRESHOLD:
        clarification = build_clarification_from_weak_results(question)
        clarification_msg_id = await chat_repository.add_message(
            db, session_id, "assistant", clarification,
            metadata={"is_clarification": True},
        )
        background_tasks.add_task(_maybe_update_summary, session_id)
        return ChatResponse(
            answer=clarification,
            citations=[],
            query_original=question,
            query_rewritten=rewritten.query_en,
            total_sources=0,
            model_used="deterministic",
            session_id=str(session_id),
            message_id=str(clarification_msg_id),
            needs_clarification=True,
        )
```

**7f. Nos retornos existentes (RAG normal e cache HIT), garantir `needs_clarification=False`** (já é o default — não precisa alterar, mas confirmar que `needs_clarification` está presente em todos os `ChatResponse(...)` usados).

- [ ] **Step 8: Rodar todos os testes**

```bash
cd backend
python -m pytest tests/ -v --tb=short
```

Expected: todos PASS

- [ ] **Step 9: Commit**

```bash
git add app/services/generator.py app/api/chat.py tests/unit/test_generator.py tests/integration/test_chat_api.py
git commit -m "feat(IA-104): perguntas de clarificação — detecção de ambiguidade + score fraco"
```

---

## Verificação final

- [ ] **Suite completa**

```bash
cd backend
python -m pytest tests/ -v
```

Expected: todos PASS, sem regressões nos testes existentes

- [ ] **Verificar que `_make_rewritten` foi atualizado** em `test_chat_api.py` e que os testes antigos continuam passando com os novos campos do dataclass.
