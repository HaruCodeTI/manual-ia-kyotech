# Spec: Comparação de Versões de Documentos

**Data:** 2026-03-19
**Projeto:** Kyotech AI
**Status:** Aprovado para implementação

---

## 1. Contexto e Problema

Técnicos da Kyotech frequentemente têm manuais e informativos da Fujifilm em múltiplas versões (por exemplo, manual do Frontier-780 de julho/2024 e janeiro/2025). O sistema RAG atual já ingere e versiona esses documentos via `document_versions`, mas o chat não identifica nem comenta diferenças entre versões nos resultados de busca.

O objetivo é que o bot:
1. Identifique quando os resultados de busca contêm versões diferentes do mesmo documento
2. Identifique e liste de forma granular o que mudou (adicionado, removido, modificado)
3. Responda a perguntas explícitas de comparação entre versões já ingeridas

---

## 2. Escopo

**Dentro do escopo:**
- Detecção implícita: `query_rewriter` detecta sinais de comparação na pergunta → busca em todas as versões → comparativo na resposta
- Detecção explícita: usuário pergunta diretamente sobre diferenças ("o que mudou?", "compara versões") → mesmo pipeline da detecção implícita com intenção confirmada
- Comparação pairwise entre a versão mais antiga e mais recente encontradas (v1→vN); comparação em cascata (v1→v2→v3) fora do escopo desta iteração
- Documentos referenciados por nome/data/equipamento (já ingeridos no banco)
- Formato adaptativo: integrado ao texto para perguntas técnicas com divergência detectada, seção `## Diferenças entre versões` para perguntas explícitas de comparação

**Fora do escopo:**
- Upload ad-hoc de PDFs no chat para comparação pontual
- Pré-computação de diffs no momento de ingestion
- Interface visual de diff (highlight de texto)
- Comparação em cascata com N>2 versões (iteração futura)

---

## 3. Decisão Arquitetural Central: `search_all_versions`

O `hybrid_search` atual faz JOIN com a view `current_versions`, retornando apenas a versão mais recente de cada documento. Isso impossibilita a detecção de multi-versão no pipeline padrão.

**Solução:** Novo parâmetro `include_all_versions: bool = False` em `vector_search`, `text_search` e `hybrid_search`. Quando `True`, o JOIN é feito com `document_versions` em vez de `current_versions`. Esta flag é acionada apenas quando `is_comparison_query = True`.

Custo: execução ligeiramente mais lenta (mais chunks no corpus), mas isolada ao pipeline de comparação. O pipeline padrão não é afetado.

---

## 4. Arquitetura — Pipeline Completo

```
POST /chat/ask
    │
    ├─ [EXISTENTE] semantic_cache check
    │   └─ se HIT e is_comparison_query=False → retorna cacheado
    │   └─ se is_comparison_query=True → BYPASS do cache (ver Seção 8)
    │
    ├─ [EXISTENTE] rewrite_query()
    │   └─ NOVO campo: is_comparison_query: bool = False
    │
    ├─ [EXISTENTE] hybrid_search()
    │   └─ NOVO parâmetro: include_all_versions=is_comparison_query
    │       → se True: JOIN com document_versions (todas as versões)
    │       → se False: JOIN com current_versions (comportamento atual)
    │
    ├─ [NOVO] detect_multi_version(results) → bool
    │   └─ agrupa por document_id; True se ≥2 document_version_id distintos
    │
    ├─ [NOVO] se detect_multi_version=True:
    │   └─ group_chunks_by_version(results) → Dict[version_date, List[SearchResult]]
    │   └─ compare_versions(grouped, db) → VersionDiff (via gpt-4o-mini)
    │
    └─ [EXISTENTE] generate_response()
        └─ NOVO parâmetro: version_diff: Optional[VersionDiff] = None
            → se None: comportamento atual inalterado
            → se presente: injeta diff no contexto + adapta system prompt
```

---

## 5. Componentes

### 5.1 Novo: `services/version_comparator.py`

**API pública:**

```python
def detect_multi_version(results: List[SearchResult]) -> bool:
    """
    Retorna True se há ≥2 document_version_id distintos
    para o mesmo document_id nos resultados.
    Agrupamento por document_id (campo já presente em SearchResult).
    """

def group_chunks_by_version(
    results: List[SearchResult],
) -> Dict[str, List[SearchResult]]:
    """
    Retorna dict keyed por published_date (ISO string).
    Ex: {"2024-07-01": [...chunks...], "2025-01-15": [...chunks...]}
    Ordenado cronologicamente (mais antigo primeiro).
    """

async def compare_versions(
    grouped: Dict[str, List[SearchResult]],
) -> VersionDiff:
    """
    Compara a versão mais antiga e a mais recente do grouped.
    Usa gpt-4o-mini com JSON mode para retornar VersionDiff.
    Raises: json.JSONDecodeError, openai.APIError (tratados em chat.py)
    """
```

**Estruturas de dados:**

```python
@dataclass
class DiffItem:
    change_type: str   # "added" | "removed" | "modified"
    topic: str         # ex: "Torque do parafuso de ajuste"
    old_value: str     # conteúdo da versão mais antiga (vazio se "added")
    new_value: str     # conteúdo da versão mais recente (vazio se "removed")

@dataclass
class VersionDiff:
    version_old: str       # published_date ISO da versão mais antiga
    version_new: str       # published_date ISO da versão mais recente
    diff_items: List[DiffItem]
    has_changes: bool      # False quando documentos são semanticamente idênticos
```

**Mecanismo de comparação — LLM diff semântico:**

O `compare_versions` monta um prompt com os chunks das duas versões separados por data e instrui o gpt-4o-mini a identificar diferenças **semânticas** (não diff de texto literal). O modelo retorna JSON estruturado com os `DiffItem`s.

Limite de tokens: chunks enviados ao comparador são truncados a 6.000 tokens por versão (≈ 4–5 chunks). Se houver mais chunks, os de maior `similarity` são priorizados.

**Prompt base:**
```
Você recebe trechos de duas versões do mesmo documento técnico.
Compare-os e identifique o que mudou semanticamente entre as versões.
Ignore diferenças de formatação. Foque em valores, procedimentos e peças.

Versão antiga ({version_old}):
{chunks_old}

Versão nova ({version_new}):
{chunks_new}

Retorne JSON com o schema:
{"diff_items": [{"change_type": "added|removed|modified", "topic": "...", "old_value": "...", "new_value": "..."}], "has_changes": true|false}
```

### 5.2 Atualização: `services/query_rewriter.py`

Campo adicional no dataclass de retorno:

```python
@dataclass
class RewrittenQuery:
    query_en: str
    doc_type: Optional[str]
    equipment_hint: Optional[str]
    needs_clarification: bool
    clarification_question: Optional[str]
    is_comparison_query: bool = False  # NOVO — default False
```

O gpt-4o-mini detecta intenções: "o que mudou", "compara", "diferença entre versões", "versão mais nova vs antiga", "atualização do manual".

### 5.3 Atualização: `services/search.py`

Parâmetro adicional em `vector_search`, `text_search` e `hybrid_search`:

```python
async def hybrid_search(
    ...
    include_all_versions: bool = False,  # NOVO — default False
) -> List[SearchResult]:
```

Quando `include_all_versions=True`, o JOIN usa `document_versions` no lugar de `current_versions`. Nenhuma outra lógica muda.

### 5.4 Atualização: `services/generator.py`

```python
async def generate_response(
    ...
    version_diff: Optional[VersionDiff] = None,  # NOVO — default None
    is_comparison_query: bool = False,            # NOVO — default False
) -> RAGResponse:
```

- Se `version_diff is None`: comportamento atual inalterado
- Se `version_diff.has_changes is False`: responde normalmente, sem mencionar diff
- Se `version_diff` presente e `is_comparison_query=True`: usa `COMPARISON_SYSTEM_PROMPT` + seção `## Diferenças entre versões`
- Se `version_diff` presente e `is_comparison_query=False`: integra divergências ao texto da resposta com citações [Fonte N]

**Token budget para comparison mode:** `max_tokens=2500` (igual ao `diagnostic_mode`).

Overflow de contexto: se `version_diff` + chunks excederem 12.000 tokens de contexto, os `DiffItem`s são incluídos inteiros e os chunks são truncados para caber no limite.

**`COMPARISON_SYSTEM_PROMPT`** adicionado ao lado de `SYSTEM_PROMPT` e `DIAGNOSTIC_SYSTEM_PROMPT` existentes.

### 5.5 Atualização: `api/chat.py`

```python
version_diff = None
try:
    if rewritten.is_comparison_query and detect_multi_version(results):
        grouped = group_chunks_by_version(results)
        version_diff = await compare_versions(grouped)
except Exception as exc:
    logger.warning(f"Comparação de versões falhou, seguindo sem diff: {exc}")
    version_diff = None

rag_response = await generate_response(
    ...
    version_diff=version_diff,
    is_comparison_query=rewritten.is_comparison_query,
)
```

---

## 6. Compatibilidade e Isolamento

Toda lógica nova é **aditiva** — nenhuma assinatura existente quebra:

| Componente | Mudança | Impacto em código existente |
|---|---|---|
| `query_rewriter.py` | Campo `is_comparison_query: bool = False` adicionado ao dataclass | Zero — default `False` |
| `search.py` | Parâmetro `include_all_versions: bool = False` | Zero — default `False`, comportamento idêntico |
| `generator.py` | Parâmetros `version_diff=None`, `is_comparison_query=False` | Zero — defaults preservam comportamento atual |
| `chat.py` | Bloco try/except isolado antes de `generate_response` | Zero — fallback explícito para `None` |
| `ChatResponse` | Sem alteração — diff embutido em `answer` | Zero — contrato da API inalterado |
| `RAGResponse` / `Citation` | Sem alteração | Zero |
| Testes existentes | Não passam os novos parâmetros | Continuam passando sem alteração |

**Fallback garantido:** se `compare_versions()` falhar (timeout, JSON malformado, qualquer exceção) → `version_diff = None` → `generate_response()` executa exatamente como hoje.

---

## 7. Semantic Cache — Bypass para Comparação

Queries de comparação devem **bypassar o cache**, pois:
- Uma resposta "o que mudou?" cacheada fica desatualizada ao ingerir uma nova versão
- O conteúdo do diff depende de quais versões estão disponíveis no momento da query

Implementação: checar `is_comparison_query` antes da lógica de cache em `chat.py`:

```python
cached = None
if not rewritten.is_comparison_query:
    cached = await get_cached_response(db, question)
```

O bypass ocorre **após** o `rewrite_query` e **antes** do cache lookup — sem alterar o fluxo para queries normais.

---

## 8. Tratamento de Erros

| Cenário | Comportamento |
|---|---|
| gpt-4o-mini retorna JSON malformado | `json.JSONDecodeError` capturado → `version_diff = None` → resposta normal |
| Chunks sem sobreposição semântica | `has_changes = False` → modelo não menciona diff |
| Usuário pede comparação de doc não ingerido | `rewriter` detecta → clarification question pedindo nome/data corretos |
| `is_comparison_query=True` mas apenas 1 versão encontrada | `detect_multi_version()` retorna `False` → pipeline normal + log warning |
| Timeout na chamada ao gpt-4o-mini | `asyncio.TimeoutError` capturado → fallback sem diff |
| Overflow de contexto | Chunks truncados para caber; `DiffItem`s têm prioridade |

---

## 9. Testes

**Unitários — `tests/test_version_comparator.py`:**
- `test_detect_multi_version_false_single_version` — todos os chunks do mesmo `document_version_id`
- `test_detect_multi_version_false_different_docs` — chunks de doc_ids diferentes (sem comparação)
- `test_detect_multi_version_true` — chunks do mesmo `document_id`, `document_version_id`s distintos
- `test_group_chunks_by_version_ordering` — resultado ordenado cronologicamente
- `test_compare_versions_has_changes` — mock gpt-4o-mini retorna diff com mudanças
- `test_compare_versions_no_changes` — mock retorna `has_changes: false`
- `test_compare_versions_malformed_json` — mock retorna JSON inválido → levanta exceção

**Integração — `tests/test_chat_version_comparison.py`:**
- `test_chat_explicit_comparison_bypasses_cache` — `is_comparison_query=True` → cache não é consultado
- `test_chat_returns_diff_section_on_explicit_query` — resposta contém `## Diferenças entre versões`
- `test_chat_fallback_when_comparator_raises` — comparador levanta exceção → resposta gerada normalmente
- `test_chat_normal_query_unaffected` — query sem comparison intent → `include_all_versions=False`, `version_diff=None`

---

## 10. Métricas de Validação (Experimento)

Por se tratar de um estudo/validação antes de produção:

- **Acurácia de detecção:** `versions_compared` bate com os metadados reais dos chunks?
- **Qualidade do diff:** `has_changes = True` quando há mudança real; `False` quando documentos são idênticos?
- **Latência adicional:** chamada extra ao gpt-4o-mini deve adicionar < 2s ao tempo de resposta total
- **Taxa de fallback:** quantas vezes o comparador falha e cai no pipeline normal? (target: < 5%)

---

## 11. Ordem de Implementação

1. `search.py` — adicionar `include_all_versions` + testes
2. `query_rewriter.py` — adicionar `is_comparison_query` + testes
3. `version_comparator.py` + testes unitários (TDD)
4. `generator.py` — novos parâmetros + `COMPARISON_SYSTEM_PROMPT` + testes
5. `chat.py` — orquestração completa + bypass de cache + testes de integração
6. Validação manual com documentos reais (2 versões do mesmo manual)
