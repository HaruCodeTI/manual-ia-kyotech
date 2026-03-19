# Spec: Comparação de Versões de Documentos

**Data:** 2026-03-19
**Projeto:** Kyotech AI
**Status:** Aprovado para implementação

---

## 1. Contexto e Problema

Técnicos da Kyotech frequentemente têm manuais e informativos da Fujifilm em múltiplas versões (por exemplo, manual do Frontier-780 de julho/2024 e janeiro/2025). O sistema RAG atual já ingere e versiona esses documentos via `document_versions`, mas o chat não identifica nem comenta diferenças entre versões nos resultados de busca.

O objetivo é que o bot:
1. Identifique automaticamente quando os resultados de busca contêm versões diferentes do mesmo documento
2. Identifique e liste de forma granular o que mudou (adicionado, removido, modificado)
3. Responda a perguntas explícitas de comparação entre versões já ingeridas

---

## 2. Escopo

**Dentro do escopo:**
- Detecção implícita: busca RAG retorna chunks de ≥2 versões do mesmo documento → comparativo incluído na resposta
- Detecção explícita: usuário pergunta diretamente sobre diferenças entre versões → busca direcionada + comparativo
- Comparação em cascata: todas as versões encontradas nos resultados (v1→v2→v3)
- Documentos referenciados por nome/data/equipamento (já ingeridos)
- Formato adaptativo: integrado ao texto para perguntas técnicas, seção separada para perguntas explícitas de comparação

**Fora do escopo:**
- Upload ad-hoc de PDFs no chat para comparação pontual
- Pré-computação de diffs no momento de ingestion
- Interface visual de diff (highlight de texto)

---

## 3. Arquitetura

O pipeline de comparação se encaixa como etapa opcional entre `hybrid_search` e `generate_response`:

```
POST /chat/ask
    │
    ├─ rewrite_query()          → detecta intenção "comparison" (is_comparison_query: bool)
    │
    ├─ hybrid_search()          → retorna chunks (potencialmente multi-versão)
    │
    ├─ detect_multi_version()   → bool: há ≥2 versões distintas do mesmo documento?
    │        │
    │        └─ se True: compare_versions() → VersionDiff (via gpt-4o-mini)
    │
    └─ generate_response()      → recebe version_diff: Optional[VersionDiff] → resposta final
```

---

## 4. Componentes

### 4.1 Novo: `services/version_comparator.py`

**Funções públicas:**

```python
def group_chunks_by_version(results: List[SearchResult]) -> Dict[str, List[SearchResult]]
```
Agrupa chunks por `(document_id, document_version_id, published_date)`.

```python
def detect_multi_version(results: List[SearchResult]) -> bool
```
Retorna `True` se há ≥2 versões distintas do mesmo `document_id` nos resultados.

```python
async def compare_versions(grouped: Dict[str, List[SearchResult]]) -> VersionDiff
```
Chama gpt-4o-mini com os chunks agrupados por versão e retorna diff estruturado.

**Estruturas de dados:**

```python
@dataclass
class DiffItem:
    change_type: str        # "added" | "removed" | "modified" | "unchanged"
    topic: str              # ex: "Torque do parafuso de ajuste"
    old_value: str          # conteúdo da versão mais antiga (vazio se "added")
    new_value: str          # conteúdo da versão mais recente (vazio se "removed")
    versions: List[str]     # datas das versões envolvidas

@dataclass
class VersionDiff:
    versions_compared: List[str]   # ex: ["2024-07-01", "2025-01-15"]
    diff_items: List[DiffItem]
    has_changes: bool
```

**Prompt para gpt-4o-mini:** Recebe chunks de cada versão separados por data, instrui o modelo a identificar diferenças semânticas (não diff de texto literal), retorna JSON estruturado com os `DiffItem`s.

### 4.2 Atualização: `services/query_rewriter.py`

Adicionar campo `is_comparison_query: bool = False` ao retorno do rewriter. O gpt-4o-mini detecta intenções como "o que mudou", "compara", "diferença entre versões", "versão mais nova".

### 4.3 Atualização: `services/generator.py`

- `generate_response()` recebe `version_diff: Optional[VersionDiff] = None`
- Novo system prompt mode `COMPARISON_SYSTEM_PROMPT` para perguntas explícitas de comparação
- `build_context_with_diff()`: quando `version_diff` presente, injeta o diff estruturado no contexto antes dos chunks
- Formato adaptativo: integrado ao texto se `is_comparison_query = False`, seção `## Diferenças entre versões` se `True`

### 4.4 Atualização: `api/chat.py`

Orquestração da nova etapa no pipeline:

```python
version_diff = None
try:
    if detect_multi_version(results):
        grouped = group_chunks_by_version(results)
        version_diff = await compare_versions(grouped)
except Exception as exc:
    logger.warning(f"Comparação de versões falhou, seguindo sem diff: {exc}")
    version_diff = None
```

---

## 5. Compatibilidade e Isolamento

Toda a lógica nova é **aditiva** — nenhuma assinatura existente é alterada:

| Componente | Mudança | Impacto em código existente |
|---|---|---|
| `query_rewriter.py` | Campo `is_comparison_query: bool = False` adicionado | Zero — default `False` |
| `generator.py` | Parâmetro `version_diff: Optional[VersionDiff] = None` | Zero — default `None` |
| `chat.py` | Bloco try/except isolado antes de `generate_response` | Zero — fallback explícito |
| Testes existentes | Não passam `version_diff` | Continuam passando sem alteração |

Se `compare_versions()` falhar por qualquer motivo (timeout, JSON malformado, exceção inesperada), `version_diff = None` e a resposta é gerada exatamente como hoje.

---

## 6. Tratamento de Erros

| Cenário | Comportamento |
|---|---|
| gpt-4o-mini retorna JSON malformado | `try/except` → `version_diff = None` → resposta normal |
| Chunks sem sobreposição semântica entre versões | `has_changes = False` → modelo não menciona diff |
| Usuário pede comparação de documento não ingerido | `query_rewriter` detecta → clarification question |
| Apenas 1 versão encontrada na busca | `detect_multi_version()` retorna `False` → pipeline normal |
| Timeout na chamada ao gpt-4o-mini | `asyncio.TimeoutError` capturado → fallback sem diff |

---

## 7. Testes

**Unitários — `tests/test_version_comparator.py`:**
- `test_group_chunks_by_version_single_version` — um grupo, sem multi-versão
- `test_group_chunks_by_version_multi_version` — dois grupos distintos
- `test_detect_multi_version_false` — chunks do mesmo documento, mesma versão
- `test_detect_multi_version_true` — chunks do mesmo documento, versões diferentes
- `test_compare_versions_has_changes` — mock OpenAI retorna diff com mudanças
- `test_compare_versions_no_changes` — mock retorna diff sem mudanças
- `test_compare_versions_malformed_json` — mock retorna JSON inválido → exceção

**Integração — `tests/test_chat_version_comparison.py`:**
- `test_chat_returns_diff_when_multi_version_detected` — busca retorna chunks multi-versão → resposta contém diff
- `test_chat_fallback_when_comparator_raises` — comparador levanta exceção → resposta gerada normalmente
- `test_chat_explicit_comparison_query` — pergunta explícita de comparação → seção separada no formato

---

## 8. Métricas de Validação (Experimento)

Por se tratar de um estudo/validação antes de produção:

- **Acurácia de detecção:** `versions_compared` bate com os metadados reais dos chunks?
- **Qualidade do diff:** `has_changes = True` quando há mudança real; `False` quando documentos são idênticos?
- **Latência adicional:** chamada extra ao gpt-4o-mini deve adicionar < 2s ao tempo de resposta total
- **Taxa de fallback:** quantas vezes o comparador falha e cai no pipeline normal? (target: < 5%)

---

## 9. Ordem de Implementação

1. `version_comparator.py` + testes unitários (TDD)
2. Atualização `query_rewriter.py` + testes
3. Atualização `generator.py` + testes
4. Orquestração em `chat.py` + testes de integração
5. Validação manual com documentos reais (2 versões do mesmo manual)
