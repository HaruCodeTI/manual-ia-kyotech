# Clarification Questions — Design Spec

> **For agentic workers:** Use superpowers:writing-plans to create the implementation plan from this spec.

**Goal:** O assistente detecta quando uma pergunta é ambígua ou os resultados são fracos e pergunta ao técnico por mais contexto antes de entregar uma resposta de baixa confiança.

**Status:** Aprovado para implementação

**Dependência obrigatória:** A feature de Memória de Conversa (`2026-03-19-conversation-memory-design.md`) deve estar **completamente implementada** antes desta. Em particular:
- `BackgroundTasks` já deve estar injetado como parâmetro em `ask_question`
- `_maybe_update_summary` já deve existir em `chat.py`
- O histórico de sessão já deve ser carregado no início do endpoint

---

## Problema

O assistente responde mesmo quando a pergunta é vaga demais para encontrar resultados precisos. Dois casos problemáticos:

1. Técnico pergunta "Como trocar o rolo de pressão?" sem especificar o equipamento — o modelo busca em todos e retorna resultados genéricos ou do equipamento errado
2. Técnico pergunta "Não funciona" — o modelo não tem dados suficientes para buscar nada útil

---

## Arquitetura

### Dois gatilhos, um único ponto de saída

```
pergunta
    ↓
[semantic cache check — se HIT: retorna resposta cacheada + agenda summary]
    ↓
rewrite_query(question, conversation_context)  ← estendido: detecta ambiguidade
    ↓
needs_clarification == true?
    → SIM: salvar clarificação no banco → agenda summary → retornar ChatResponse(needs_clarification=true)
    → NÃO: hybrid_search()
                ↓
           top_score < CLARIFICATION_THRESHOLD (0.45)?
           [top_score já >= MIN_SCORE_THRESHOLD=0.15 por construção — híbrido filtra internamente]
                → SIM: salvar clarificação no banco → agenda summary → retornar ChatResponse(needs_clarification=true)
                → NÃO: generate_response() → agenda summary → resposta normal
```

### Preservação de contexto via Memória de Conversa

A mensagem de clarificação é sempre salva como `role: assistant` com `metadata: {"is_clarification": true}`. A resposta do técnico chega com o mesmo `session_id`. A Memória de Conversa carrega o histórico — incluindo a clarificação anterior — e o `rewrite_query` recebe esse contexto via `conversation_context`. Quando o técnico responde "Frontier-780", o rewriter vê no histórico que estava sendo pedido o equipamento e classifica a nova mensagem como `needs_clarification=False`, prosseguindo com o RAG normalmente.

**Não há lógica especial para "resposta à clarificação"** — o contexto flui naturalmente pelo histórico de sessão.

---

## Constantes

```python
# app/api/chat.py
CLARIFICATION_THRESHOLD = 0.45
```

Contexto: `MIN_SCORE_THRESHOLD = 0.15` em `search.py` filtra ruído absoluto (removido dentro do `hybrid_search`). `CLARIFICATION_THRESHOLD = 0.45` captura o range "resultado encontrado mas impreciso demais" — por construção, qualquer resultado em `results` já tem `similarity >= 0.15`.

---

## Componentes

### 1. `query_rewriter.py` — detecção de ambiguidade sem custo extra

**Dataclass estendido:**
```python
@dataclass
class RewrittenQuery:
    original: str
    query_en: str
    doc_type: Optional[str]
    equipment_hint: Optional[str]
    needs_clarification: bool = False           # ← NOVO
    clarification_question: Optional[str] = None  # ← NOVO
```

**`REWRITE_PROMPT` — regras adicionadas (mesma chamada gpt-4o-mini):**
```
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
{
  "query_en": "...",
  "doc_type": "manual" | "informativo" | "both",
  "equipment_hint": "model name or null",
  "needs_clarification": false,
  "clarification_question": null
}
```

**`max_tokens` aumentado de 200 → 300** para acomodar os dois campos novos no JSON de saída.

**Parse atualizado em `rewrite_query()`:**
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

Fallback de parse (`except json.JSONDecodeError`) mantém `needs_clarification=False` — comportamento seguro.

---

### 2. `generator.py` — função determinística para score fraco

Nova função pública (sem chamada LLM):

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

`generate_response()` não muda — a decisão de clarificar é tomada em `chat.py` antes de chamar o generator.

---

### 3. `chat.py` — dois pontos de saída antecipada

**Após `rewrite_query()`:**
```python
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

**Após `hybrid_search()`:**
```python
# top_score já >= MIN_SCORE_THRESHOLD por construção (hybrid_search filtra internamente)
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
        model_used="deterministic",  # sem LLM neste branch
        session_id=str(session_id),
        message_id=str(clarification_msg_id),
        needs_clarification=True,
    )
```

**`background_tasks.add_task(_maybe_update_summary, session_id)` é chamado em TODOS os quatro branches:**
1. Clarificação via rewriter
2. Clarificação via score fraco
3. Resposta RAG normal
4. Cache HIT (já especificado na Conversation Memory spec — confirmar na implementação)

---

### 4. `ChatResponse` — campo adicional

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
    needs_clarification: bool = False  # ← NOVO, default False
```

Frontend quando `needs_clarification=true`:
- Não renderiza seção de citações
- Não exibe widget de feedback (👍👎)
- Tudo mais idêntico — o técnico digita a resposta no input normal

---

## Compatibilidade

- `needs_clarification` tem default `False` — clientes existentes não quebram
- `RewrittenQuery` tem `needs_clarification=False` e `clarification_question=None` por default — fallback de parse seguro
- Clarificações não entram no semantic cache (total_sources=0, citations=[])
- `_make_rewritten()` nos testes existentes deve ser atualizado para incluir os novos campos com defaults

---

## Testes

### Unitários

**`tests/unit/test_query_rewriter.py`**
- Pergunta de procedimento sem equipamento → `needs_clarification=True`, `clarification_question` não-nulo
- Pergunta clara com equipamento → `needs_clarification=False`
- Falha de parse JSON → `needs_clarification=False` (fallback seguro)

**`tests/unit/test_generator.py`**
- `build_clarification_from_weak_results("qualquer pergunta")` retorna string não-vazia em português

### Integração

**`tests/integration/test_chat_api.py`**

Atualizar `_make_rewritten()` helper para incluir novos campos:
```python
def _make_rewritten(question: str = "test question") -> RewrittenQuery:
    return RewrittenQuery(
        original=question,
        query_en="how to replace the pressure roller",
        doc_type="manual",
        equipment_hint=None,
        needs_clarification=False,      # ← NOVO
        clarification_question=None,    # ← NOVO
    )
```

Novos cenários:
1. `rewrite_query` mockado retornando `needs_clarification=True` → `needs_clarification=True` na resposta, `citations=[]`, `hybrid_search` **não é chamado**
2. `hybrid_search` mockado retornando resultado com `similarity=0.3` (abaixo de 0.45) → `needs_clarification=True`, `generate_response` **não é chamado**
3. `hybrid_search` mockado retornando resultado com `similarity=0.8` → pipeline normal, `needs_clarification=False`
4. Sessão com clarificação anterior no histórico: `get_recent_messages` retorna `[{role: assistant, content: "Para qual equipamento?", metadata: {is_clarification: true}}, {role: user, content: "Frontier-780"}]` → `rewrite_query` chamado com contexto → `needs_clarification=False`, RAG prossegue normalmente

---

## Arquivos modificados

| Arquivo | Tipo | Mudança |
|---------|------|---------|
| `app/services/query_rewriter.py` | Modificar | `RewrittenQuery` + 2 campos; `REWRITE_PROMPT` + regras 6-7; `max_tokens` 200→300; parse dos novos campos |
| `app/services/generator.py` | Modificar | Nova função `build_clarification_from_weak_results` |
| `app/api/chat.py` | Modificar | Constante `CLARIFICATION_THRESHOLD`; 2 pontos de saída antecipada; `background_tasks` em todos os 4 branches |
| `app/api/chat.py` — `ChatResponse` | Modificar | Campo `needs_clarification: bool = False` |
| `tests/unit/test_query_rewriter.py` | Modificar | 3 novos cenários |
| `tests/unit/test_generator.py` | Modificar | 1 novo cenário |
| `tests/integration/test_chat_api.py` | Modificar | Atualizar `_make_rewritten()`; 4 novos cenários |
