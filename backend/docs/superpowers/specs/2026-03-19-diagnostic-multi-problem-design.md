# IA-89: RAG Avançado — Diagnóstico Multi-Problema

## Visão Geral

Permitir que o técnico descreva múltiplos problemas em uma única pergunta (ex: "Não imprime e também dá erro E-05") e receber uma resposta diagnóstica estruturada que analisa cada sintoma individualmente antes de sugerir causas e próximos passos.

## Motivação

Técnicos de campo frequentemente descrevem equipamentos com múltiplos sintomas simultâneos. O pipeline atual trata tudo como uma única query, perdendo especificidade. O cliente aceitou tradeoff de latência e custo maiores em troca de respostas muito mais úteis para diagnóstico complexo.

## Escopo

**Inclui:**
- Detecção automática de perguntas multi-problema (regex, sem LLM)
- Decomposição em sub-queries via gpt-4o-mini
- Buscas híbridas paralelas por sub-problema
- Fusão de resultados por chunk_id
- Prompt diagnóstico estruturado (3 seções)
- Fallback automático se decomposição falhar

**Não inclui:**
- Mudanças no contrato da API (`/chat/ask`)
- Mudanças no frontend
- Novo endpoint ou novo modelo de dados

## Arquitetura

### Fluxo Completo

```
Pergunta do técnico
        │
        ▼
rewrite_query()  ← já existente
        │ needs_clarification=True → early exit (clarificação)
        │ needs_clarification=False ↓
        ▼
is_diagnostic_query(question)  ← regex, sem LLM
        │
    ┌───┴───┐
    │ False │──→ pipeline normal (hybrid_search + generate_response)
    └───────┘
        │ True
        ▼
decompose_problems(question)  ← gpt-4o-mini
→ ["sub-query EN 1", "sub-query EN 2", ...]  (max 4)
        │
        ▼
asyncio.gather(
  hybrid_search(db, q1, ...),
  hybrid_search(db, q2, ...),
)
        │
        ▼
fusão por chunk_id — best score ganha, top 8
        │
        ▼
generate_response(..., diagnostic_mode=True)
→ resposta com 3 seções + [Fonte N] inline
        │
        ▼
ChatResponse — mesmo contrato, mesmo endpoint
```

### Interação com Clarificação (IA-104)

As duas lógicas são independentes e sequenciais:
1. Rewriter detecta `needs_clarification=True` → sai antes de `is_diagnostic_query`
2. `needs_clarification=False` → `is_diagnostic_query` decide se é diagnóstico ou pipeline normal

Não há conflito entre os dois sistemas.

## Componentes

### 1. `app/services/diagnostic_analyzer.py` (novo)

**Responsabilidade:** detectar multi-problema e decompor em sub-queries.

```python
MULTI_PROBLEM_PATTERNS = [
    r'\be também\b',
    r'\balém disso\b',
    r'\bao mesmo tempo\b',
    r'\be mais\b',
    r'\btambém\b',
    r'\b\d+[\.\)]\s+.+\b\d+[\.\)]\s+',  # "1. X 2. Y"
    r'(?:[^,]+,){2,}',                    # 3+ itens separados por vírgula
]

def is_diagnostic_query(question: str) -> bool:
    """Regex sem LLM. Roda em toda pergunta que passou pela clarificação."""

async def decompose_problems(question: str) -> List[str]:
    """
    Usa gpt-4o-mini para decompor em 2-4 sub-queries em inglês.
    Retorna JSON: ["sub-query EN 1", "sub-query EN 2"]
    Fallback: [question] se parse falhar ou retornar 1 item.
    Se decomposição retornar 1 item: continua em modo diagnóstico
    (prompt estruturado aplicado mesmo assim).
    """
```

**Dependências:** `embedder.get_openai_client()`, `settings.azure_openai_mini_deployment`

### 2. `app/services/generator.py` (modificar)

Adicionar `DIAGNOSTIC_SYSTEM_PROMPT` e parâmetro `diagnostic_mode: bool = False` em `generate_response`.

**`DIAGNOSTIC_SYSTEM_PROMPT`:**
```
Você é o assistente técnico da Kyotech, especializado em diagnóstico de equipamentos Fujifilm.
O técnico relatou múltiplos sintomas. Analise cada um separadamente antes de sugerir causas.

REGRAS OBRIGATÓRIAS:
1. Responda SEMPRE em português brasileiro
2. Use APENAS as informações dos trechos fornecidos — NUNCA invente
3. Cite fontes com EXATAMENTE o formato [Fonte N] com colchetes
4. Se informação não consta nos trechos, diga explicitamente

FORMATO OBRIGATÓRIO DA RESPOSTA:
## Análise dos Sintomas
[Aborde cada sintoma individualmente com citações [Fonte N]]

## Possíveis Causas
[Causas em comum entre os sintomas, ou causas independentes]

## Próximos Passos
[Procedimentos em ordem de prioridade com citações [Fonte N]]

NÃO liste as fontes ao final — o sistema exibe automaticamente.
```

**Parâmetro `diagnostic_mode`:**
- `True` → `DIAGNOSTIC_SYSTEM_PROMPT` + `max_tokens=2500`
- `False` → `SYSTEM_PROMPT` atual + `max_tokens=1500` (sem mudança)

Lógica de parse de citações `[Fonte N]` é compartilhada — sem duplicação.

### 3. `app/api/chat.py` (modificar)

Inserir bloco diagnóstico após o early exit de clarificação e antes do `hybrid_search` do pipeline normal:

```python
equipment_filter = request.equipment_filter or rewritten.equipment_hint

if is_diagnostic_query(question):
    sub_queries = await decompose_problems(question)
    all_results = await asyncio.gather(*[
        hybrid_search(
            db=db,
            query_en=q,
            query_original=question,
            limit=8,
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
else:
    results = await hybrid_search(
        db=db,
        query_en=rewritten.query_en,
        query_original=question,
        limit=8,
        doc_type=rewritten.doc_type,
        equipment_key=equipment_filter,
    )
    diagnostic_mode = False

# Threshold de clarificação por score fraco — igual ao atual
top_score = max((r.similarity for r in results), default=0.0)
if results and top_score < CLARIFICATION_THRESHOLD:
    ...  # early exit — sem mudança

rag_response = await generate_response(
    question=question,
    query_rewritten=rewritten.query_en,
    search_results=results,
    history_messages=history_messages,
    history_summary=history_summary,
    diagnostic_mode=diagnostic_mode,
)
```

**O que não muda:** `ChatResponse`, lógica de cache, persistência de mensagem, `_maybe_update_summary`, contrato da API.

## Testes

### Unitários

**`tests/unit/test_diagnostic_analyzer.py`**
- `test_is_diagnostic_query_conjunction` — "e também" detectado
- `test_is_diagnostic_query_enumeration` — "1. X 2. Y" detectado
- `test_is_diagnostic_query_comma_list` — 3+ itens com vírgula detectado
- `test_is_diagnostic_query_simple_question` — pergunta simples retorna False
- `test_decompose_problems_returns_list` — mock LLM, verifica List[str]
- `test_decompose_problems_fallback` — mock LLM com JSON inválido, retorna [question]

**`tests/unit/test_generator.py`** (adicionar)
- `test_diagnostic_mode_uses_diagnostic_prompt` — mock LLM, verifica system prompt
- `test_diagnostic_mode_uses_more_tokens` — verifica max_tokens=2500
- `test_normal_mode_unchanged` — diagnostic_mode=False mantém comportamento atual

### Integração

**`tests/integration/test_chat_api.py`** (adicionar)
- `test_diagnostic_query_uses_decomposition` — mock de `is_diagnostic_query=True`, verifica múltiplas chamadas a `hybrid_search`
- `test_simple_query_skips_diagnostic` — mock de `is_diagnostic_query=False`, verifica chamada única
- `test_diagnostic_fallback_on_decompose_error` — `decompose_problems` lança exceção, pipeline continua normalmente

## Tradeoffs Aceitos pelo Cliente

- Respostas ~2-3x mais lentas para perguntas diagnósticas (buscas paralelas + mais tokens)
- ~3x mais cara por token na geração (2500 vs 1500 tokens)
- Compensado pela qualidade diagnóstica para sintomas complexos

## Critérios de Sucesso

- [ ] Perguntas com múltiplos sintomas detectadas automaticamente sem LLM
- [ ] Resposta diagnóstica contém as 3 seções obrigatórias (Análise / Causas / Próximos Passos)
- [ ] Citações [Fonte N] presentes dentro das seções
- [ ] Perguntas simples continuam no pipeline original sem impacto
- [ ] Fallback funcional: exceção em decompose_problems → pipeline normal
- [ ] Fallback gracioso: decompose retorna 1 item → modo diagnóstico mantido
- [ ] Todos os testes unitários e de integração passando
