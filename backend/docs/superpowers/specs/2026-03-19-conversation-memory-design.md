# Conversation Memory — Design Spec

> **For agentic workers:** Use superpowers:writing-plans to create the implementation plan from this spec.

**Goal:** Fazer o assistente usar o histórico da sessão como contexto — tanto na busca RAG quanto na geração da resposta — corrigindo o problema onde o modelo "esquece" o que foi dito na mesma conversa.

**Status:** Aprovado para implementação

---

## Problema

O histórico de mensagens já é persistido em `chat_messages`, mas nunca é enviado ao LLM. Cada pergunta é tratada de forma isolada. O técnico precisa repetir contexto a cada turno (ex: "E o Frontier-780?" após já ter mencionado o equipamento).

---

## Arquitetura

### Fluxo atual
```
pergunta → rewrite → search → generate → salvar
```

### Fluxo com memória
```
pergunta + session_id
    ↓
buscar últimas 6 mensagens (ANTES de inserir a nova) + history_summary da sessão
    ↓
inserir mensagem do usuário no banco
    ↓
rewrite_query(pergunta, conversation_context)   ← contexto influencia busca
    ↓
hybrid_search(query reescrita com contexto de equipamento/tópico)
    ↓
[semantic cache check — usa histórico para persistir mas não para buscar cache]
    ↓
generate_response(pergunta, results, history_messages, history_summary)  ← array multi-turn
    ↓
salvar resposta do assistente
    ↓
[BackgroundTask] se unsummarized_count >= 6 → gerar summary → persistir
```

### Janela de contexto
- **Últimas 6 mensagens** (3 turnos de ida e volta) enviadas ao LLM como multi-turn
- **Summary persistido** das mensagens mais antigas, injetado como mensagem `system`
- **Trigger de sumarização:** quando `unsummarized_count >= 6` (re-sumariza a cada 6 novas mensagens após a primeira sumarização)

---

## Banco de Dados

**Migration 006:**
```sql
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS history_summary TEXT;
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS last_summarized_at TIMESTAMPTZ;
```

`last_summarized_at` permite calcular `unsummarized_count` sem contar todas as mensagens.

---

## Componentes

### 1. `chat_repository.py` — novos métodos

```python
async def get_recent_messages(
    db: AsyncSession,
    session_id: UUID,
    limit: int = 6,
) -> List[Dict[str, str]]:
    """
    Retorna as últimas N mensagens (role + content) em ordem cronológica.
    Deve ser chamado ANTES de inserir a mensagem atual do usuário.
    Retorna: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
    """

async def get_session_summary(
    db: AsyncSession,
    session_id: UUID,
) -> Dict[str, Any]:
    """
    Retorna history_summary e last_summarized_at da sessão.
    Retorna: {"history_summary": str | None, "last_summarized_at": datetime | None}
    """

async def count_messages_since(
    db: AsyncSession,
    session_id: UUID,
    since: Optional[datetime] = None,
) -> int:
    """
    Conta mensagens da sessão após `since` (ou total se since=None).
    Usado para calcular unsummarized_count.
    """

async def get_messages_before_recent(
    db: AsyncSession,
    session_id: UUID,
    skip_last: int = 6,
    since: Optional[datetime] = None,
) -> List[Dict[str, str]]:
    """
    Retorna mensagens exceto as últimas N.
    Se `since` fornecido, retorna apenas mensagens após essa data (exceto as últimas N).
    Usado para gerar o summary incremental das mensagens ainda não sumarizadas.
    Retorna: [{"role": "...", "content": "..."}, ...]
    """

async def update_history_summary(
    db: AsyncSession,
    session_id: UUID,
    summary: str,
) -> None:
    """
    Persiste o summary e atualiza last_summarized_at = NOW().
    """
```

`get_session_with_messages()` existente permanece inalterado (usado pela API de histórico do frontend).

---

### 2. `query_rewriter.py` — aceita contexto da conversa

Assinatura nova:
```python
async def rewrite_query(
    question: str,
    conversation_context: Optional[str] = None,
) -> RewrittenQuery:
```

Quando `conversation_context` está presente, é injetado no prompt de reescrita:
```
Previous conversation context:
{conversation_context}

Current question: {question}
```

O `conversation_context` é uma string formatada como:
```
User: Como funciona o rolo de pressão do Frontier-780?
Assistant: O rolo de pressão do Frontier-780 funciona assim...
User: E o procedimento de limpeza?
```

Isso permite que "E o procedimento de limpeza?" seja reescrito como "cleaning procedure for Frontier-780 pressure roller".

---

### 3. `generator.py` — array multi-turn

Assinatura nova:
```python
async def generate_response(
    question: str,
    query_rewritten: str,
    search_results: List[SearchResult],
    history_messages: Optional[List[Dict[str, str]]] = None,
    history_summary: Optional[str] = None,
) -> RAGResponse:
```

Montagem do array de mensagens:
```python
messages = [{"role": "system", "content": SYSTEM_PROMPT}]

if history_summary:
    messages.append({
        "role": "system",
        "content": f"Resumo do contexto anterior:\n{history_summary}"
    })

if history_messages:
    messages.extend(history_messages)  # [{"role": "user", ...}, {"role": "assistant", ...}, ...]

messages.append({
    "role": "user",
    "content": f"Pergunta do técnico: {question}\n\nTrechos encontrados:\n\n{context}"
})
```

---

### 4. `chat.py` — orquestração principal

**Helper `_build_conversation_context`:**
```python
def _build_conversation_context(
    history_messages: List[Dict[str, str]],
    history_summary: Optional[str],
) -> Optional[str]:
    """
    Formata histórico como string para o rewriter.
    Retorna None se não há contexto.
    Formato:
        User: <content>
        Assistant: <content>
        ...
    Se há summary, prepende: "Resumo anterior: <summary>\n\n"
    """
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

**Fluxo com histórico em `ask_question`:**

```python
# 1. Resolver sessão
if request.session_id:
    session_id = UUID(request.session_id)
else:
    title = question[:80] + ("…" if len(question) > 80 else "")
    session_id = await chat_repository.create_session(db, user_id, title)

# 2. Buscar histórico ANTES de inserir a mensagem atual
history_messages = []
history_summary = None
if request.session_id:
    history_messages = await chat_repository.get_recent_messages(db, session_id, limit=6)
    session_info = await chat_repository.get_session_summary(db, session_id)
    history_summary = session_info.get("history_summary")

# 3. Inserir mensagem do usuário
await chat_repository.add_message(db, session_id, "user", question)

# 4. Verificar semantic cache (cache hit não usa histórico para busca,
#    mas a resposta cacheada é salva na sessão normalmente)
cached = await get_cached_response(db, question)
if cached:
    # ... retorno cacheado (comportamento atual preservado)
    pass

# 5. Construir contexto textual para o rewriter
conversation_context = _build_conversation_context(history_messages, history_summary)

# 6. Rewrite com contexto
rewritten = await rewrite_query(question, conversation_context=conversation_context)

# 7. Search + Generate com histórico
rag_response = await generate_response(
    question=question,
    query_rewritten=rewritten.query_en,
    search_results=results,
    history_messages=history_messages,
    history_summary=history_summary,
)
```

**Sumarização via FastAPI `BackgroundTasks`:**

```python
@router.post("/ask", response_model=ChatResponse)
async def ask_question(
    request: ChatRequest,
    background_tasks: BackgroundTasks,   # ← adicionar parâmetro
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # ... pipeline ...

    # Após salvar resposta do assistente:
    background_tasks.add_task(_maybe_update_summary, session_id)
    return ChatResponse(...)
```

`BackgroundTasks` do FastAPI executa após a resposta ser enviada mas **dentro do ciclo de vida da request**, então uma nova sessão de DB deve ser aberta dentro da task:

```python
async def _maybe_update_summary(session_id: UUID) -> None:
    """Abre sua própria sessão de DB — NÃO reutiliza a sessão da request."""
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        session_info = await chat_repository.get_session_summary(db, session_id)
        last_summarized = session_info.get("last_summarized_at")
        unsummarized_count = await chat_repository.count_messages_since(db, session_id, since=last_summarized)
        if unsummarized_count < 6:
            return
        # Busca apenas mensagens NÃO sumarizadas ainda (após last_summarized_at)
        # exceto as últimas 6 (que ficam como contexto recente no array multi-turn)
        new_messages = await chat_repository.get_messages_before_recent(
            db, session_id, skip_last=6, since=last_summarized
        )
        if not new_messages:
            return
        # Sumarização incremental: combina summary anterior com novas mensagens
        summary = await _generate_summary(new_messages, existing_summary=session_info.get("history_summary"))
        await chat_repository.update_history_summary(db, session_id, summary)
```

**Lógica de re-trigger:** sumariza quando `unsummarized_count >= 6` — ou seja, a cada 6 novas mensagens após a última sumarização. Não re-sumariza a cada turno.

---

### 5. Sumarização

Prompt de sumarização incremental (modelo: `gpt-4o-mini`):

Quando há summary anterior:
```
Você tem um resumo existente de uma conversa técnica e novas mensagens para incorporar.
Atualize o resumo incluindo os novos tópicos. Máximo 5 frases. Português brasileiro.

Resumo existente:
{existing_summary}

Novas mensagens:
{new_messages formatadas como "User: ...\nAssistant: ..."}
```

Quando é a primeira sumarização (sem summary anterior):
```
Resuma em 3-5 frases os principais tópicos técnicos discutidos.
Inclua: equipamentos mencionados, problemas identificados, soluções discutidas.
Seja conciso e factual. Responda em português brasileiro.

Conversa:
{mensagens formatadas como "User: ...\nAssistant: ..."}
```

`_generate_summary(messages, existing_summary=None)` é uma função privada em `chat.py` que chama a OpenAI diretamente (não passa por `generate_response`). O prompt varia dependendo se `existing_summary` está presente.

---

## Tratamento do Semantic Cache

Quando há cache HIT:
- O histórico é buscado normalmente (para consistência)
- A resposta cacheada é salva na sessão como de costume
- `background_tasks.add_task(_maybe_update_summary, session_id)` **deve ser chamado antes do `return`** no branch de cache hit — igual ao branch RAG
- A resposta cacheada **não** usa histórico no LLM (foi gerada anteriormente) — isso é aceitável: o cache responde a perguntas idênticas, e perguntas idênticas em contextos diferentes são raras

---

## Compatibilidade

- `history_messages=[]` e `history_summary=None` por padrão → comportamento atual preservado para novas sessões
- Sessões existentes sem `history_summary` funcionam normalmente (campo nullable)
- Nenhum endpoint de API muda sua interface pública

---

## Testes

### Unitários

**`tests/unit/test_generator.py`**
- Sem histórico → `messages` array tem exatamente `[system, user]`
- Com histórico → `messages` array tem `[system, user1, assistant1, ..., userN]`
- Com summary → summary aparece como segunda mensagem `system`
- Com summary e histórico → `[system, system(summary), user1, assistant1, ..., userN]`

**`tests/unit/test_chat_repository.py`**
- `get_recent_messages` retorna as últimas N em ordem cronológica
- `get_recent_messages` retorna menos que N quando há menos mensagens
- `update_history_summary` atualiza `history_summary` e `last_summarized_at`
- `count_messages_since(since=None)` retorna total de mensagens
- `count_messages_since(since=datetime)` retorna apenas mensagens após a data

### Integração

**`tests/integration/test_chat_api.py`**
- Segunda pergunta na mesma sessão: `get_recent_messages` é chamado com `session_id`
- Primeira pergunta (sem session_id): `get_recent_messages` não é chamado
- Mock de `get_recent_messages` retornando histórico → `generate_response` recebe `history_messages` correto

---

## Arquivos modificados

| Arquivo | Tipo | Mudança |
|---------|------|---------|
| `migrations/006_conversation_memory.sql` | Criar | `ALTER TABLE` adiciona `history_summary` e `last_summarized_at` |
| `app/services/chat_repository.py` | Modificar | 5 novos métodos: `get_recent_messages`, `get_session_summary`, `count_messages_since`, `get_messages_before_recent`, `update_history_summary` |
| `app/services/query_rewriter.py` | Modificar | Parâmetro `conversation_context: Optional[str] = None` + injeção no prompt |
| `app/services/generator.py` | Modificar | Parâmetros `history_messages` e `history_summary` opcionais + array multi-turn |
| `app/api/chat.py` | Modificar | Busca de histórico, `_build_conversation_context`, `BackgroundTasks`, `_maybe_update_summary`, `_generate_summary` |
| `tests/unit/test_generator.py` | Modificar | Testes multi-turn (4 cenários) |
| `tests/unit/test_chat_repository.py` | Modificar | Testes dos 5 novos métodos |
| `tests/integration/test_chat_api.py` | Modificar | Testes de contexto na sessão |
