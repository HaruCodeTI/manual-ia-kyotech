# Design: Segurança de Sessão + Qualidade de Busca para Docs Misc

**Data:** 2026-03-26
**Status:** Aprovado
**Escopo:** Correção de falha de segurança no endpoint de chat + melhoria estrutural da busca para documentos sem equipamento vinculado

---

## Contexto

Durante testes com o cliente Kyotech, dois problemas foram identificados:

1. **Segurança:** o endpoint `POST /api/v1/chat/ask` aceita qualquer `session_id` sem validar se pertence ao usuário autenticado. Um usuário poderia enviar mensagens para sessões de outros usuários.

2. **Qualidade de busca:** 12 documentos foram upados como `misc` (sem `equipment_key`). A busca encontra 8 resultados via threshold semântico, mas o gerador retorna 0 citações porque os chunks do documento com a resposta não chegam ao top 8 — nenhum deles recebe o equipment boost por não terem `equipment_key` definido. A abordagem de vincular documentos a um único equipamento não faz sentido pois um manual pode referenciar vários equipamentos.

---

## Decisões de Design

- **Equipment detection por chunk**, não por documento — resolve a limitação de 1 equipamento por doc
- **Regex sobre a tabela `equipments`** (incluindo aliases) — sem LLM, sem custo extra, < 50ms por upload
- **Campo `equipment_mentions jsonb`** na tabela `chunks` — sem JOIN extra, índice GIN, zero impacto em escrita
- **Pool de busca individual: 30** — cobre o volume atual (~240-480 chunks) sem pesar na geração
- **Resultado final mantém top 8** — nenhuma mudança na interface com o gerador
- **Backfill via script standalone** — sem re-upload, sem re-indexação de embeddings, sem toque no Blob

---

## Arquitetura das Mudanças

```
Upload flow (novo):
  [1] Extração → [2] Registro → [3] Upload Blob → [4] Versão DB
  [5] Chunking → [6] Embeddings → [7] Detecção de equipamentos ← NOVO

Busca (atualizada):
  vector_search(limit=30) + text_search(limit=30)
    → fusão → threshold 0.15 → boost por equipment_key OU equipment_mentions
    → top 8 final
```

---

## Seção 1 — Correção de Segurança

**Arquivo:** `backend/app/api/chat.py`

Quando `body.session_id` é fornecido, validar ownership antes de usar:

```python
if body.session_id:
    session_id = UUID(body.session_id)
    owned = await chat_repository.get_session_with_messages(db, session_id, user.id)
    if not owned:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
```

`get_session_with_messages` já filtra por `user_id`, nenhuma query nova necessária.

---

## Seção 2 — Migration SQL

**Novo arquivo:** `backend/migrations/004_chunk_equipment_mentions.sql`

```sql
ALTER TABLE chunks
ADD COLUMN IF NOT EXISTS equipment_mentions jsonb NOT NULL DEFAULT '[]';

CREATE INDEX IF NOT EXISTS idx_chunks_equipment_mentions
ON chunks USING gin(equipment_mentions);
```

- Não destrutivo: chunks existentes ficam com `[]`
- Índice GIN: busca eficiente dentro do array JSON
- Aplicado automaticamente na inicialização da app (mecanismo existente de migrations)

---

## Seção 3 — Equipment Detector Service

**Novo arquivo:** `backend/app/services/equipment_detector.py`

**Interface:**
```python
async def detect_equipment_mentions(
    content: str,
    db: AsyncSession,
) -> list[str]:
    """
    Retorna lista de equipment_keys encontrados no texto do chunk.
    Carrega equipment_keys + aliases do banco, aplica regex case-insensitive.
    """
```

**Lógica:**
1. Query `SELECT equipment_key, aliases FROM equipments`
2. Para cada equipment, compila pattern: `r'\b' + re.escape(key) + r'\b'` + aliases
3. Busca no `content` (case-insensitive)
4. Retorna lista de equipment_keys detectados (deduplicado)

A lista de equipments é carregada uma vez por chamada de ingestão (não por chunk) para minimizar hits no banco.

---

## Seção 4 — Atualização do Ingestion Service

**Arquivo:** `backend/app/services/ingestion.py`

Após inserção dos chunks no banco, adicionar passo `[7/7]`:

```
[7/7] Detectando equipamentos nos chunks
```

- Carrega lista de equipments do banco (1 query)
- Para cada chunk inserido: roda `detect_equipment_mentions(chunk.content)`
- `UPDATE chunks SET equipment_mentions = :mentions WHERE id = :id`
- Loga: `{N} chunks com equipamentos detectados: {equipment_keys_encontrados}`

**Novo arquivo:** `backend/scripts/backfill_equipment_mentions.py`

Script standalone para processar os 12 docs existentes:

```
python scripts/backfill_equipment_mentions.py
```

- Busca todos os chunks com `equipment_mentions = '[]'`
- Roda detector em cada chunk
- UPDATE apenas nos chunks onde algo foi detectado
- Loga progresso `Chunk X/N — Y equipamentos detectados`
- Idempotente: pode ser rodado mais de uma vez sem efeito colateral

---

## Seção 5 — Atualização da Busca

**Arquivo:** `backend/app/services/search.py`

**Pool aumentado:**
```python
# Antes: limit=8 nas buscas individuais
# Depois: limit=30
vector_results = await vector_search(db, query_en, limit=30, ...)
text_results = await text_search(db, query_original, limit=30, ...)
```

**SearchResult atualizado:** incluir `equipment_mentions: list[str]` vindo do SELECT.

**Boost atualizado em `hybrid_search`:**
```python
if equipment_key:
    for chunk_id, result in merged.items():
        # boost existente: tag do documento
        if result.equipment_key == equipment_key:
            scores[chunk_id] += EQUIPMENT_BOOST
        # boost novo: menção detectada no chunk
        elif equipment_key in (result.equipment_mentions or []):
            scores[chunk_id] += EQUIPMENT_BOOST
```

Resultado final mantém top 8 após threshold e ranking.

---

## Ordem de Implementação

1. Migration SQL (`004_chunk_equipment_mentions.sql`)
2. `equipment_detector.py`
3. Atualização do `search.py` (SearchResult + pool + boost)
4. Atualização do `ingestion.py` (passo [7/7])
5. Script de backfill + execução nos docs existentes
6. Fix de segurança no `chat.py`

---

## O que NÃO muda

- Embeddings existentes — não re-indexados
- Blob Storage — não tocado
- Interface do gerador — recebe os mesmos top 8
- Endpoint de upload — mesma API, mesmo fluxo
- Documentos existentes — não re-upados
- `equipment_key` do documento — mantido, ainda usado para boost
