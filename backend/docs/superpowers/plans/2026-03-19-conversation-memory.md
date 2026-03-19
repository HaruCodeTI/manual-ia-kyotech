# Conversation Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O assistente usa o histórico da sessão como contexto — tanto na busca RAG quanto na geração da resposta — corrigindo o problema onde o modelo "esquece" o que foi dito na mesma conversa.

**Architecture:** Histórico é buscado antes de inserir a mensagem do usuário, passado como array multi-turn para o LLM e como `conversation_context` para o query rewriter. Sumarização incremental via FastAPI BackgroundTasks persiste o histórico antigo compactado em `chat_sessions.history_summary`.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, OpenAI API (gpt-4o + gpt-4o-mini), pytest + AsyncMock

---

## Mapa de arquivos

| Arquivo | Ação | Responsabilidade |
|---------|------|-----------------|
| `migrations/006_conversation_memory.sql` | Criar | Adiciona `history_summary` e `last_summarized_at` em `chat_sessions` |
| `app/services/chat_repository.py` | Modificar | 5 novos métodos de histórico |
| `app/services/query_rewriter.py` | Modificar | Parâmetro `conversation_context` opcional |
| `app/services/generator.py` | Modificar | Parâmetros `history_messages` e `history_summary` opcionais |
| `app/api/chat.py` | Modificar | Orquestração completa: busca histórico, BackgroundTasks, sumarização |
| `tests/unit/test_chat_repository.py` | Modificar | Testes dos 5 novos métodos |
| `tests/unit/test_generator.py` | Modificar | Testes multi-turn (4 cenários) |
| `tests/integration/test_chat_api.py` | Modificar | Testes de contexto na sessão |

---

## Task 1: Migration — history_summary + last_summarized_at

**Files:**
- Create: `backend/migrations/006_conversation_memory.sql`

- [ ] **Step 1: Criar o arquivo de migration**

```sql
-- Kyotech AI — Fase 6: Memória de Conversa
-- Executar após migrations 001–005
-- Adiciona suporte a histórico persistido e sumarização incremental

ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS history_summary TEXT;
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS last_summarized_at TIMESTAMPTZ;
```

- [ ] **Step 2: Verificar que a migration roda sem erro**

```bash
cd backend
# A migration será aplicada automaticamente no próximo startup (migration runner em main.py)
# Para testar manualmente, verificar que o SQL é válido:
python -c "
import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal
async def run():
    async with AsyncSessionLocal() as db:
        await db.execute(text('ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS history_summary TEXT'))
        await db.execute(text('ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS last_summarized_at TIMESTAMPTZ'))
        await db.commit()
        print('OK')
asyncio.run(run())
"
```

Expected: `OK` sem erros

- [ ] **Step 3: Commit**

```bash
git add migrations/006_conversation_memory.sql
git commit -m "feat(migration): 006 — history_summary + last_summarized_at em chat_sessions"
```

---

## Task 2: chat_repository.py — 5 novos métodos

**Files:**
- Modify: `backend/app/services/chat_repository.py`
- Test: `backend/tests/unit/test_chat_repository.py`

**Contexto:** O arquivo atual usa `AsyncMock` para `db.execute` nos testes. `make_mock_result(rows=[...])` retorna um mock com `.fetchone()`, `.fetchall()`, `.rowcount`. Padrão: escrever o teste antes da implementação.

- [ ] **Step 1: Escrever os testes falhando**

Adicionar ao final de `tests/unit/test_chat_repository.py`:

```python
from datetime import datetime, timezone
from app.services.chat_repository import (
    get_recent_messages,
    get_session_summary,
    count_messages_since,
    get_messages_before_recent,
    update_history_summary,
)


# ── get_recent_messages ──

@pytest.mark.asyncio
async def test_get_recent_messages_returns_last_n(mock_db, make_mock_result):
    now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    sid = uuid4()
    rows = [
        (uuid4(), "user", "pergunta 1", now),
        (uuid4(), "assistant", "resposta 1", now),
    ]
    mock_db.execute = AsyncMock(return_value=make_mock_result(rows=rows))
    result = await get_recent_messages(mock_db, sid, limit=6)
    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "pergunta 1"
    assert result[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_get_recent_messages_empty(mock_db, make_mock_result):
    mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[]))
    result = await get_recent_messages(mock_db, uuid4())
    assert result == []


# ── get_session_summary ──

@pytest.mark.asyncio
async def test_get_session_summary_returns_dict(mock_db, make_mock_result):
    now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[("resumo anterior", now)])
    )
    result = await get_session_summary(mock_db, uuid4())
    assert result["history_summary"] == "resumo anterior"
    assert result["last_summarized_at"] == now


@pytest.mark.asyncio
async def test_get_session_summary_no_summary(mock_db, make_mock_result):
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[(None, None)])
    )
    result = await get_session_summary(mock_db, uuid4())
    assert result["history_summary"] is None
    assert result["last_summarized_at"] is None


# ── count_messages_since ──

@pytest.mark.asyncio
async def test_count_messages_since_no_date(mock_db, make_mock_result):
    mock_result = make_mock_result(rows=[])
    mock_result.scalar.return_value = 5
    mock_db.execute = AsyncMock(return_value=mock_result)
    count = await count_messages_since(mock_db, uuid4(), since=None)
    assert count == 5


@pytest.mark.asyncio
async def test_count_messages_since_with_date(mock_db, make_mock_result):
    mock_result = make_mock_result(rows=[])
    mock_result.scalar.return_value = 3
    mock_db.execute = AsyncMock(return_value=mock_result)
    since = datetime(2024, 6, 1, tzinfo=timezone.utc)
    count = await count_messages_since(mock_db, uuid4(), since=since)
    assert count == 3
    # Verificar que o SQL inclui filtro de data
    sql_text = str(mock_db.execute.call_args[0][0].text)
    assert "created_at" in sql_text


# ── get_messages_before_recent ──

@pytest.mark.asyncio
async def test_get_messages_before_recent_returns_old(mock_db, make_mock_result):
    now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    rows = [
        (uuid4(), "user", "msg antiga", now),
    ]
    mock_db.execute = AsyncMock(return_value=make_mock_result(rows=rows))
    result = await get_messages_before_recent(mock_db, uuid4(), skip_last=6)
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "msg antiga"


# ── update_history_summary ──

@pytest.mark.asyncio
async def test_update_history_summary_commits(mock_db, make_mock_result):
    mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[]))
    await update_history_summary(mock_db, uuid4(), "novo resumo")
    mock_db.execute.assert_awaited_once()
    mock_db.commit.assert_awaited_once()
    # Verificar que o SQL atualiza last_summarized_at
    sql_text = str(mock_db.execute.call_args[0][0].text)
    assert "last_summarized_at" in sql_text
    assert "history_summary" in sql_text
```

- [ ] **Step 2: Rodar e confirmar que falham**

```bash
cd backend
python -m pytest tests/unit/test_chat_repository.py::test_get_recent_messages_returns_last_n -v
```

Expected: `ImportError: cannot import name 'get_recent_messages'`

- [ ] **Step 3: Implementar os 5 métodos em chat_repository.py**

Adicionar após `update_session_title` e antes de `delete_session`:

```python
async def get_recent_messages(
    db: AsyncSession,
    session_id: UUID,
    limit: int = 6,
) -> List[Dict[str, str]]:
    """Retorna as últimas N mensagens em ordem cronológica. Chamar ANTES de add_message."""
    result = await db.execute(
        text("""
            SELECT id, role, content, created_at
            FROM chat_messages
            WHERE session_id = :sid
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"sid": str(session_id), "limit": limit},
    )
    rows = result.fetchall()
    # Retorna em ordem cronológica (mais antiga primeiro)
    return [
        {"role": row[1], "content": row[2]}
        for row in reversed(rows)
    ]


async def get_session_summary(
    db: AsyncSession,
    session_id: UUID,
) -> Dict[str, Any]:
    """Retorna history_summary e last_summarized_at da sessão."""
    result = await db.execute(
        text("""
            SELECT history_summary, last_summarized_at
            FROM chat_sessions
            WHERE id = :id
        """),
        {"id": str(session_id)},
    )
    row = result.fetchone()
    if not row:
        return {"history_summary": None, "last_summarized_at": None}
    return {"history_summary": row[0], "last_summarized_at": row[1]}


async def count_messages_since(
    db: AsyncSession,
    session_id: UUID,
    since: Optional[Any] = None,
) -> int:
    """Conta mensagens da sessão. Se since fornecido, conta apenas após essa data."""
    if since is not None:
        result = await db.execute(
            text("""
                SELECT COUNT(*) FROM chat_messages
                WHERE session_id = :sid AND created_at > :since
            """),
            {"sid": str(session_id), "since": since},
        )
    else:
        result = await db.execute(
            text("SELECT COUNT(*) FROM chat_messages WHERE session_id = :sid"),
            {"sid": str(session_id)},
        )
    return result.scalar() or 0


async def get_messages_before_recent(
    db: AsyncSession,
    session_id: UUID,
    skip_last: int = 6,
    since: Optional[Any] = None,
) -> List[Dict[str, str]]:
    """
    Retorna mensagens antigas exceto as últimas skip_last.
    Se since fornecido, considera apenas mensagens após essa data.
    Usado para gerar summary incremental.
    """
    if since is not None:
        result = await db.execute(
            text("""
                SELECT role, content FROM (
                    SELECT role, content, created_at,
                           ROW_NUMBER() OVER (ORDER BY created_at DESC) as rn
                    FROM chat_messages
                    WHERE session_id = :sid AND created_at > :since
                ) sub
                WHERE rn > :skip
                ORDER BY created_at
            """),
            {"sid": str(session_id), "since": since, "skip": skip_last},
        )
    else:
        result = await db.execute(
            text("""
                SELECT role, content FROM (
                    SELECT role, content, created_at,
                           ROW_NUMBER() OVER (ORDER BY created_at DESC) as rn
                    FROM chat_messages
                    WHERE session_id = :sid
                ) sub
                WHERE rn > :skip
                ORDER BY created_at
            """),
            {"sid": str(session_id), "skip": skip_last},
        )
    return [{"role": row[0], "content": row[1]} for row in result.fetchall()]


async def update_history_summary(
    db: AsyncSession,
    session_id: UUID,
    summary: str,
) -> None:
    """Persiste o summary e atualiza last_summarized_at = NOW()."""
    await db.execute(
        text("""
            UPDATE chat_sessions
            SET history_summary = :summary,
                last_summarized_at = NOW()
            WHERE id = :id
        """),
        {"summary": summary, "id": str(session_id)},
    )
    await db.commit()
```

Adicionar `Optional` ao import se não estiver:
```python
from typing import Any, Dict, List, Optional
```

- [ ] **Step 4: Rodar todos os testes do arquivo**

```bash
cd backend
python -m pytest tests/unit/test_chat_repository.py -v
```

Expected: todos PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/chat_repository.py tests/unit/test_chat_repository.py
git commit -m "feat(repository): 5 novos métodos de histórico de conversa"
```

---

## Task 3: query_rewriter.py — parâmetro conversation_context

**Files:**
- Modify: `backend/app/services/query_rewriter.py`
- Test: `backend/tests/unit/test_query_rewriter.py` (já existe — adicionar testes à classe `TestRewriteQuery`)

- [ ] **Step 1: Escrever o teste falhando**

**ATENÇÃO:** O arquivo `tests/unit/test_query_rewriter.py` **já existe** com uma fixture `autouse=True` que faz o patch de `get_openai_client`. NÃO recriar o arquivo. Adicionar os testes abaixo ao final da classe `TestRewriteQuery` existente, usando `_patch_openai_client` como parâmetro — jamais usar `with patch(...)` interno.

Adicionar ao final da classe `TestRewriteQuery` em `tests/unit/test_query_rewriter.py`:

```python
    @pytest.mark.asyncio
    async def test_rewrite_without_context_omits_history_header(self, _patch_openai_client):
        payload = {
            "query_en": "pressure roller replacement",
            "doc_type": "manual",
            "equipment_hint": None,
        }
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(payload))
        )
        result = await rewrite_query("Como trocar o rolo?")
        assert result.query_en == "pressure roller replacement"
        assert result.equipment_hint is None
        # conversation_context não deve aparecer no prompt quando omitido
        call_messages = _patch_openai_client.chat.completions.create.call_args[1]["messages"]
        user_content = call_messages[-1]["content"]
        assert "Previous conversation" not in user_content

    @pytest.mark.asyncio
    async def test_rewrite_with_context_injects_history(self, _patch_openai_client):
        payload = {
            "query_en": "cleaning procedure Frontier-780",
            "doc_type": "manual",
            "equipment_hint": "frontier-780",
        }
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(payload))
        )
        context = "User: Como funciona o Frontier-780?\nAssistant: O Frontier-780 funciona assim..."
        result = await rewrite_query("E o procedimento de limpeza?", conversation_context=context)
        assert result.equipment_hint == "frontier-780"
        # Contexto deve estar no prompt enviado ao LLM
        call_messages = _patch_openai_client.chat.completions.create.call_args[1]["messages"]
        user_content = call_messages[-1]["content"]
        assert "Previous conversation context" in user_content
        assert "Frontier-780" in user_content
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd backend
python -m pytest tests/unit/test_query_rewriter.py -v
```

Expected: `ImportError` ou `TypeError` (função não aceita `conversation_context`)

- [ ] **Step 3: Implementar em query_rewriter.py**

Alterar a assinatura de `rewrite_query`:

```python
async def rewrite_query(
    question: str,
    conversation_context: Optional[str] = None,
) -> RewrittenQuery:
```

Alterar o conteúdo da mensagem do usuário:

```python
    if conversation_context:
        user_content = (
            f"Previous conversation context:\n{conversation_context}\n\n"
            f"Current question: {question}"
        )
    else:
        user_content = question

    response = await client.chat.completions.create(
        model=settings.azure_openai_mini_deployment,
        messages=[
            {"role": "system", "content": REWRITE_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        max_tokens=200,
    )
```

- [ ] **Step 4: Rodar os testes**

```bash
cd backend
python -m pytest tests/unit/test_query_rewriter.py -v
```

Expected: todos PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/query_rewriter.py tests/unit/test_query_rewriter.py
git commit -m "feat(rewriter): parâmetro conversation_context para busca ciente do histórico"
```

---

## Task 4: generator.py — array multi-turn

**Files:**
- Modify: `backend/app/services/generator.py`
- Test: `backend/tests/unit/test_generator.py`

- [ ] **Step 1: Escrever os testes falhando**

Adicionar ao final de `tests/unit/test_generator.py`:

```python
class TestGenerateResponseWithHistory:
    @pytest.mark.asyncio
    async def test_no_history_uses_simple_array(self):
        """Sem histórico: messages = [system, user]"""
        mock_client = AsyncMock()
        choice = MagicMock()
        choice.message.content = "Resposta [Fonte 1]."
        chat_resp = MagicMock()
        chat_resp.choices = [choice]
        mock_client.chat.completions.create = AsyncMock(return_value=chat_resp)

        with patch("app.services.generator.get_openai_client", return_value=mock_client):
            await generate_response(
                question="pergunta",
                query_rewritten="question",
                search_results=[_make_result()],
            )

        messages = mock_client.chat.completions.create.call_args[1]["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user"]

    @pytest.mark.asyncio
    async def test_with_history_uses_multiturn_array(self):
        """Com histórico: messages = [system, user1, assistant1, user_atual]"""
        mock_client = AsyncMock()
        choice = MagicMock()
        choice.message.content = "Resposta [Fonte 1]."
        chat_resp = MagicMock()
        chat_resp.choices = [choice]
        mock_client.chat.completions.create = AsyncMock(return_value=chat_resp)

        history = [
            {"role": "user", "content": "pergunta anterior"},
            {"role": "assistant", "content": "resposta anterior"},
        ]

        with patch("app.services.generator.get_openai_client", return_value=mock_client):
            await generate_response(
                question="nova pergunta",
                query_rewritten="new question",
                search_results=[_make_result()],
                history_messages=history,
            )

        messages = mock_client.chat.completions.create.call_args[1]["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user", "assistant", "user"]
        assert messages[1]["content"] == "pergunta anterior"
        assert messages[2]["content"] == "resposta anterior"

    @pytest.mark.asyncio
    async def test_with_summary_adds_system_message(self):
        """Com summary: messages = [system, system(summary), user]"""
        mock_client = AsyncMock()
        choice = MagicMock()
        choice.message.content = "Resposta [Fonte 1]."
        chat_resp = MagicMock()
        chat_resp.choices = [choice]
        mock_client.chat.completions.create = AsyncMock(return_value=chat_resp)

        with patch("app.services.generator.get_openai_client", return_value=mock_client):
            await generate_response(
                question="pergunta",
                query_rewritten="question",
                search_results=[_make_result()],
                history_summary="Técnico perguntou sobre Frontier-780.",
            )

        messages = mock_client.chat.completions.create.call_args[1]["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "system", "user"]
        assert "Resumo do contexto anterior" in messages[1]["content"]
        assert "Frontier-780" in messages[1]["content"]

    @pytest.mark.asyncio
    async def test_with_summary_and_history(self):
        """Com summary e histórico: [system, system(summary), user1, assistant1, user]"""
        mock_client = AsyncMock()
        choice = MagicMock()
        choice.message.content = "Resposta [Fonte 1]."
        chat_resp = MagicMock()
        chat_resp.choices = [choice]
        mock_client.chat.completions.create = AsyncMock(return_value=chat_resp)

        history = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]

        with patch("app.services.generator.get_openai_client", return_value=mock_client):
            await generate_response(
                question="pergunta",
                query_rewritten="question",
                search_results=[_make_result()],
                history_messages=history,
                history_summary="Resumo.",
            )

        messages = mock_client.chat.completions.create.call_args[1]["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "system", "user", "assistant", "user"]
```

- [ ] **Step 2: Rodar e confirmar que falham**

```bash
cd backend
python -m pytest tests/unit/test_generator.py::TestGenerateResponseWithHistory -v
```

Expected: `TypeError: generate_response() got unexpected keyword argument 'history_messages'`

- [ ] **Step 3: Implementar em generator.py**

Alterar a assinatura de `generate_response`:

```python
async def generate_response(
    question: str,
    query_rewritten: str,
    search_results: List[SearchResult],
    history_messages: Optional[List[Dict[str, str]]] = None,
    history_summary: Optional[str] = None,
) -> RAGResponse:
```

Substituir a construção de `messages` dentro de `generate_response` (após `context = build_context(search_results)`):

```python
    messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history_summary:
        messages.append({
            "role": "system",
            "content": f"Resumo do contexto anterior:\n{history_summary}",
        })

    if history_messages:
        messages.extend(history_messages)

    messages.append({
        "role": "user",
        "content": (
            f"Pergunta do técnico: {question}\n\n"
            f"Trechos encontrados:\n\n{context}"
        ),
    })

    client = get_openai_client()
    response = await client.chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=messages,
        temperature=0.2,
        max_tokens=1500,
    )
```

Adicionar ao import no topo:
```python
from typing import Dict, List, Optional
```

- [ ] **Step 4: Rodar todos os testes do generator**

```bash
cd backend
python -m pytest tests/unit/test_generator.py -v
```

Expected: todos PASS (incluindo os testes existentes)

- [ ] **Step 5: Commit**

```bash
git add app/services/generator.py tests/unit/test_generator.py
git commit -m "feat(generator): array multi-turn com history_messages e history_summary"
```

---

## Task 5: chat.py — orquestração completa

**Files:**
- Modify: `backend/app/api/chat.py`
- Test: `backend/tests/integration/test_chat_api.py`

**Contexto crítico:**
- `BackgroundTasks` é injetado como parâmetro FastAPI — não precisa importar manualmente, só adicionar ao parâmetro da função
- `_maybe_update_summary` abre sua própria sessão DB (`AsyncSessionLocal`) — nunca usa a sessão da request que será fechada
- `get_recent_messages` deve ser chamado **antes** de `add_message`
- `background_tasks.add_task` deve ser chamado em **ambos os branches** (cache HIT e RAG normal) — os branches de clarificação são adicionados na feature Clarification Questions

- [ ] **Step 1: Escrever os testes de integração falhando**

Adicionar ao final de `tests/integration/test_chat_api.py`:

```python
@pytest.mark.anyio
async def test_ask_second_message_fetches_history(async_client):
    """Segunda pergunta na mesma sessão deve buscar histórico."""
    session_id = uuid4()

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=[]) as mock_history,
        patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock, return_value={"history_summary": None, "last_summarized_at": None}),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "E o procedimento?", "session_id": str(session_id)},
        )

    assert resp.status_code == 200
    mock_history.assert_awaited_once()


@pytest.mark.anyio
async def test_ask_first_message_no_history_fetch(async_client):
    """Primeira pergunta (sem session_id) não busca histórico."""
    session_id = uuid4()

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=[]) as mock_history,
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "Como trocar o rolo?"},
        )

    assert resp.status_code == 200
    mock_history.assert_not_awaited()


@pytest.mark.anyio
async def test_ask_passes_history_to_generate_response(async_client):
    """Com histórico, generate_response deve receber history_messages."""
    session_id = uuid4()
    history = [
        {"role": "user", "content": "Frontier-780"},
        {"role": "assistant", "content": "Sim, tenho informações."},
    ]

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()) as mock_gen,
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=history),
        patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock, return_value={"history_summary": None, "last_summarized_at": None}),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "E a manutenção?", "session_id": str(session_id)},
        )

    assert resp.status_code == 200
    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs.get("history_messages") == history
```

- [ ] **Step 2: Rodar e confirmar que falham**

```bash
cd backend
python -m pytest tests/integration/test_chat_api.py::test_ask_second_message_fetches_history -v
```

Expected: FAIL (get_recent_messages não existe no chat.py)

- [ ] **Step 3: Implementar as mudanças em chat.py**

**3a. Adicionar imports:**
```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
```

```python
from app.core.database import AsyncSessionLocal  # adicionar este import
from app.services.embedder import get_openai_client  # adicionar este import
from app.core.config import settings  # adicionar este import (se não existir)
```

**3b. Adicionar helper `_build_conversation_context` antes de `ask_question`:**

```python
def _build_conversation_context(
    history_messages: list,
    history_summary: Optional[str],
) -> Optional[str]:
    """Formata histórico como string para o query rewriter."""
    if not history_messages and not history_summary:
        return None
    parts = []
    if history_summary:
        parts.append(f"Resumo anterior: {history_summary}")
    for m in history_messages:
        role = "User" if m["role"] == "user" else "Assistant"
        parts.append(f"{role}: {m['content']}")
    return "\n".join(parts)
```

**3c. Adicionar `_generate_summary` antes de `ask_question`:**

```python
async def _generate_summary(
    messages: list,
    existing_summary: Optional[str] = None,
) -> str:
    """Gera summary incremental usando gpt-4o-mini."""
    formatted = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in messages
    )

    if existing_summary:
        prompt = (
            f"Você tem um resumo existente de uma conversa técnica e novas mensagens para incorporar.\n"
            f"Atualize o resumo incluindo os novos tópicos. Máximo 5 frases. Português brasileiro.\n\n"
            f"Resumo existente:\n{existing_summary}\n\n"
            f"Novas mensagens:\n{formatted}"
        )
    else:
        prompt = (
            f"Resuma em 3-5 frases os principais tópicos técnicos discutidos.\n"
            f"Inclua: equipamentos mencionados, problemas identificados, soluções discutidas.\n"
            f"Seja conciso e factual. Responda em português brasileiro.\n\n"
            f"Conversa:\n{formatted}"
        )

    client = get_openai_client()
    response = await client.chat.completions.create(
        model=settings.azure_openai_mini_deployment,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=300,
    )
    return response.choices[0].message.content.strip()
```

**3d. Adicionar `_maybe_update_summary` antes de `ask_question`:**

```python
async def _maybe_update_summary(session_id) -> None:
    """
    Verifica se precisa sumarizar e persiste o resultado.
    Abre sua própria sessão DB — NÃO reutiliza a sessão da request.
    """
    from uuid import UUID
    if not isinstance(session_id, UUID):
        session_id = UUID(str(session_id))

    async with AsyncSessionLocal() as db:
        try:
            session_info = await chat_repository.get_session_summary(db, session_id)
            last_summarized = session_info.get("last_summarized_at")
            unsummarized_count = await chat_repository.count_messages_since(
                db, session_id, since=last_summarized
            )
            if unsummarized_count < 6:
                return
            new_messages = await chat_repository.get_messages_before_recent(
                db, session_id, skip_last=6, since=last_summarized
            )
            if not new_messages:
                return
            summary = await _generate_summary(
                new_messages,
                existing_summary=session_info.get("history_summary"),
            )
            await chat_repository.update_history_summary(db, session_id, summary)
            logger.info(f"Summary atualizado para sessão {session_id}")
        except Exception as e:
            logger.error(f"Erro ao atualizar summary da sessão {session_id}: {e}")
```

**3e. Alterar a assinatura de `ask_question`:**

```python
@router.post("/ask", response_model=ChatResponse)
async def ask_question(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
```

**3f. Atualizar o corpo de `ask_question` — buscar histórico ANTES de add_message:**

Após resolver a sessão (bloco `if request.session_id`) e **antes** de `await chat_repository.add_message(...)`:

```python
    # Buscar histórico ANTES de inserir a mensagem atual
    history_messages = []
    history_summary = None
    if request.session_id:
        history_messages = await chat_repository.get_recent_messages(db, session_id, limit=6)
        session_info = await chat_repository.get_session_summary(db, session_id)
        history_summary = session_info.get("history_summary")

    # Persistir mensagem do usuário
    await chat_repository.add_message(db, session_id, "user", question)
```

**3g. Adicionar `background_tasks.add_task` no branch de cache HIT:**

Após `assistant_msg_id = await chat_repository.add_message(...)` no bloco de cache HIT:
```python
        background_tasks.add_task(_maybe_update_summary, session_id)
        return ChatResponse(...)
```

**3h. Construir contexto e passar para o pipeline RAG:**

```python
    # Construir contexto para o rewriter
    conversation_context = _build_conversation_context(history_messages, history_summary)

    # RAG pipeline
    rewritten = await rewrite_query(question, conversation_context=conversation_context)
```

**3i. Passar histórico para `generate_response`:**

```python
    rag_response = await generate_response(
        question=question,
        query_rewritten=rewritten.query_en,
        search_results=results,
        history_messages=history_messages,
        history_summary=history_summary,
    )
```

**3j. Adicionar `background_tasks.add_task` no branch RAG normal (após salvar resposta):**

```python
    assistant_msg_id = await chat_repository.add_message(
        db, session_id, "assistant", rag_response.answer,
        citations=citations_json, metadata=metadata_json,
    )

    background_tasks.add_task(_maybe_update_summary, session_id)

    return ChatResponse(...)
```

**3k. Atualizar os 3 testes de integração existentes** para mockar `_maybe_update_summary`:

Os 3 testes existentes — `test_ask_creates_new_session`, `test_ask_with_existing_session`, `test_ask_with_equipment_filter` — passarão a falhar porque `_maybe_update_summary` abre uma sessão real no BD. Adicionar `patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock)` ao bloco `with (...)` de cada um:

```python
# Exemplo: test_ask_creates_new_session
with (
    patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
    patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
    patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
    patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
    patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
    patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
    patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),  # ← ADICIONAR
):
```

Aplicar o mesmo para `test_ask_with_existing_session` e `test_ask_with_equipment_filter`.

- [ ] **Step 4: Rodar todos os testes de integração**

```bash
cd backend
python -m pytest tests/integration/test_chat_api.py -v
```

Expected: todos PASS

- [ ] **Step 5: Rodar a suite completa**

```bash
cd backend
python -m pytest tests/ -v
```

Expected: todos PASS

- [ ] **Step 6: Commit**

```bash
git add app/api/chat.py tests/integration/test_chat_api.py
git commit -m "feat(chat): memória de conversa — histórico multi-turn + sumarização incremental"
```

---

## Verificação final

- [ ] **Rodar a suite completa uma vez mais**

```bash
cd backend
python -m pytest tests/ -v --tb=short
```

Expected: todos PASS, sem regressões

- [ ] **Commit final se necessário**

```bash
git add -A
git commit -m "feat(IA-103): memória de conversa completa — testes, implementação, sumarização"
```
