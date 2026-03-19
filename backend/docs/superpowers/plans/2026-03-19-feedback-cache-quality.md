# Feedback + Semantic Cache + Chunk Quality Scoring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar coleta de feedback (👍/👎) que alimenta automaticamente um loop de melhoria contínua do RAG: semantic cache para respostas aprovadas (velocidade + custo) e chunk quality scoring para re-ranking automático (precisão).

**Architecture:** Feedback de uma mensagem dispara dois efeitos automáticos — 👍 armazena a resposta no cache semântico (pgvector, threshold 0.92) e ajusta quality_score dos chunks citados (+0.05); 👎 penaliza os chunks citados (-0.03). O pipeline RAG verifica o cache antes de chamar OpenAI, e a busca híbrida incorpora quality_score como boost adicional. O cache é invalidado automaticamente após novos uploads.

**Tech Stack:** PostgreSQL + pgvector, FastAPI, SQLAlchemy async, Next.js, TypeScript, Lucide React

---

## Mapa de Arquivos

**Criar:**
- `backend/migrations/004_feedback_cache.sql` — tabelas `message_feedback` e `semantic_cache`, coluna `quality_score` em `chunks`
- `backend/app/services/feedback_repository.py` — salvar feedback + atualizar quality_score dos chunks
- `backend/app/services/semantic_cache.py` — get/set/invalidate do cache semântico
- `backend/app/api/feedback.py` — endpoint `POST /api/v1/chat/feedback`
- `frontend/src/components/chat/FeedbackWidget.tsx` — botões 👍/👎 com estado local

**Modificar:**
- `backend/app/api/chat.py` — retornar `message_id` no ChatResponse + checar cache antes do RAG
- `backend/app/services/search.py` — incorporar `quality_score` no score híbrido
- `backend/app/services/ingestion.py` — invalidar cache após ingestion bem-sucedida
- `backend/app/main.py` — registrar feedback router
- `frontend/src/types/index.ts` — adicionar `message_id` em `Message` e `ChatResponse`
- `frontend/src/lib/api.ts` — adicionar `submitFeedback()`
- `frontend/src/components/chat/MessageBubble.tsx` — integrar FeedbackWidget
- `frontend/src/components/chat/ChatWindow.tsx` — passar message_id para Message

---

## Task 1: Migration DB — feedback, quality_score, semantic_cache

**Files:**
- Create: `backend/migrations/004_feedback_cache.sql`
- Modify: `backend/app/services/repository.py` — preservar `quality_score` no ON CONFLICT

> **⚠ Comportamento conhecido:** `quality_score` é resetado para 0.0 quando um documento é **re-ingerido com uma versão nova** (novo `published_date` + novo `version_id`). Isso é intencional — chunks de uma nova versão ainda não têm histórico de feedback. O quality_score é acumulado por versão, não por documento.

- [ ] **Step 1: Criar o arquivo de migration**

```sql
-- Kyotech AI — Fase 4: Feedback, quality_score e semantic cache
-- Executar após migrations 001, 002, 003

-- Tabela de feedback por mensagem
CREATE TABLE IF NOT EXISTS message_feedback (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    message_id  UUID NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    rating      VARCHAR(10) NOT NULL CHECK (rating IN ('thumbs_up', 'thumbs_down')),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (message_id)  -- um feedback por mensagem
);

CREATE INDEX IF NOT EXISTS idx_feedback_message ON message_feedback(message_id);

-- Coluna quality_score nos chunks (começa em 0, sobe/desce com feedback)
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS quality_score FLOAT DEFAULT 0.0;

-- Cache semântico: pergunta → resposta aprovada (👍)
CREATE TABLE IF NOT EXISTS semantic_cache (
    id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    question_embedding VECTOR(1536) NOT NULL,
    question_original  TEXT NOT NULL,
    answer             TEXT NOT NULL,
    citations          JSONB,
    query_rewritten    TEXT,
    model_used         TEXT,
    hit_count          INTEGER DEFAULT 0,
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

-- Índice HNSW para busca rápida por similaridade
CREATE INDEX IF NOT EXISTS idx_cache_embedding
    ON semantic_cache USING hnsw (question_embedding vector_cosine_ops);
```

- [ ] **Step 2: Verificar que a migration será executada no startup**

O `main.py` já executa todos os `.sql` de `migrations/` em ordem alfabética no startup (lifespan). Nenhuma mudança necessária — o arquivo `004_feedback_cache.sql` será executado automaticamente.

- [ ] **Step 2: Verificar ON CONFLICT em repository.py — nenhuma mudança necessária**

Abrir `backend/app/services/repository.py` e localizar `insert_chunks_with_embeddings`. A cláusula atual é:

```python
ON CONFLICT (document_version_id, page_number, chunk_index) DO UPDATE
SET content = EXCLUDED.content, embedding = EXCLUDED.embedding
```

**Nenhuma alteração de código é necessária.** A cláusula já não menciona `quality_score`, então a coluna nova (adicionada pela migration) é automaticamente preservada em re-ingesções. Verificar apenas que o código é exatamente como acima — nada mais.

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/004_feedback_cache.sql backend/app/services/repository.py
git commit -m "feat(db): migration 004 — message_feedback, quality_score, semantic_cache; preserva quality_score no ON CONFLICT"
```

---

## Task 2: feedback_repository.py — salvar feedback e atualizar quality_score

**Files:**
- Create: `backend/app/services/feedback_repository.py`

**Contexto:** As citações de uma mensagem são armazenadas como JSONB em `chat_messages.citations`. O JSON de citação tem: `source_index`, `source_filename`, `page_number`, `equipment_key`, `doc_type`, `published_date`, `storage_path`, `document_version_id`. Usamos `document_version_id + page_number` para localizar os chunks.

> **Design de transação:** `save_feedback` e `update_chunk_quality` são consolidados em uma única função `record_feedback` que usa **uma única transação**. Isso evita falha parcial onde o feedback é gravado mas o quality_score não é atualizado.

- [ ] **Step 1: Criar o arquivo**

```python
"""
Kyotech AI — Repositório de Feedback e Quality Scoring
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

QUALITY_DELTA_UP = 0.05    # incremento por 👍
QUALITY_DELTA_DOWN = 0.03  # decremento por 👎 (menor para não suprimir conteúdo novo)
QUALITY_MIN = -1.0
QUALITY_MAX = 2.0


async def record_feedback(
    db: AsyncSession,
    message_id: UUID,
    rating: str,  # "thumbs_up" ou "thumbs_down"
) -> bool:
    """
    Salva feedback E atualiza quality_score dos chunks citados em uma única transação.
    Retorna False se já existe feedback para a mensagem (idempotente).

    Usar uma única transação garante que o feedback não seja gravado
    sem que o quality_score seja atualizado (sem falha parcial).
    """
    # Buscar citações da mensagem
    msg_result = await db.execute(
        text("SELECT citations FROM chat_messages WHERE id = :msg_id"),
        {"msg_id": str(message_id)},
    )
    msg_row = msg_result.fetchone()
    citations = msg_row[0] if msg_row and msg_row[0] else []

    # INSERT-first: ON CONFLICT DO NOTHING é atômico — elimina race condition TOCTOU.
    # Se rowcount == 0, outra requisição já registrou o feedback (idempotente).
    insert_result = await db.execute(
        text("""
            INSERT INTO message_feedback (message_id, rating)
            VALUES (:message_id, :rating)
            ON CONFLICT (message_id) DO NOTHING
        """),
        {"message_id": str(message_id), "rating": rating},
    )
    if insert_result.rowcount == 0:
        logger.info(f"Feedback já existente para mensagem {message_id}, ignorando")
        await db.rollback()
        return False

    # Atualizar quality_score dos chunks citados (na mesma transação)
    delta = QUALITY_DELTA_UP if rating == "thumbs_up" else -QUALITY_DELTA_DOWN
    total_updated = 0

    pairs = [
        (c["document_version_id"], c["page_number"])
        for c in citations
        if c.get("document_version_id") and c.get("page_number") is not None
    ]

    for version_id, page_number in pairs:
        result = await db.execute(
            text("""
                UPDATE chunks
                SET quality_score = GREATEST(:min, LEAST(:max, quality_score + :delta))
                WHERE document_version_id = :version_id
                  AND page_number = :page_number
            """),
            {
                "delta": delta,
                "min": QUALITY_MIN,
                "max": QUALITY_MAX,
                "version_id": version_id,
                "page_number": page_number,
            },
        )
        total_updated += result.rowcount

    # Commit único — feedback + quality_score juntos ou nenhum
    await db.commit()
    logger.info(
        f"Feedback '{rating}' gravado + {total_updated} chunks atualizados "
        f"(delta={delta:+.2f}, mensagem {message_id})"
    )
    return True


async def get_feedback(
    db: AsyncSession,
    message_id: UUID,
) -> Optional[str]:
    """Retorna o rating atual de uma mensagem, ou None se não há feedback."""
    result = await db.execute(
        text("SELECT rating FROM message_feedback WHERE message_id = :id"),
        {"id": str(message_id)},
    )
    row = result.fetchone()
    return row[0] if row else None
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/feedback_repository.py
git commit -m "feat(feedback): feedback_repository — record_feedback em transação única (feedback + quality_score atômicos)"
```

---

## Task 3: semantic_cache.py — get/set/invalidate

**Files:**
- Create: `backend/app/services/semantic_cache.py`

**Contexto:** O cache semântico usa pgvector (`<=>` = distância cosseno). Similarity = 1 - distância. Threshold 0.92 significa que somente perguntas muito similares são servidas do cache. TTL de 7 dias — respostas antigas podem referenciar documentos que não existem mais. O cache é limpo completamente no invalidate (scale pequeno, simplicidade > granularidade).

- [ ] **Step 1: Criar o arquivo**

```python
"""
Kyotech AI — Semantic Cache
Armazena respostas aprovadas (👍) indexadas pelo embedding da pergunta.
Perguntas similares (cosine similarity >= 0.92) recebem resposta cacheada
sem chamar OpenAI nem fazer busca vetorial.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedder import generate_single_embedding

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.92
CACHE_TTL_DAYS = 7


async def get_cached_response(
    db: AsyncSession,
    question: str,
) -> Optional[Dict[str, Any]]:
    """
    Busca uma resposta cacheada para a pergunta.
    Retorna None se não há cache válido (threshold ou TTL não atingidos).
    """
    embedding = await generate_single_embedding(question)
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    result = await db.execute(
        text(f"""
            SELECT
                id,
                answer,
                citations,
                question_original,
                query_rewritten,
                model_used,
                1 - (question_embedding <=> CAST(:emb AS vector)) AS similarity
            FROM semantic_cache
            WHERE created_at > NOW() - INTERVAL '{CACHE_TTL_DAYS} days'
            ORDER BY question_embedding <=> CAST(:emb AS vector)
            LIMIT 1
        """),
        # Nota: CACHE_TTL_DAYS é uma constante inteira do módulo (valor=7), não input do usuário.
        # PostgreSQL INTERVAL não aceita bind parameter, então f-string é segura aqui.
        {"emb": embedding_str},
    )
    row = result.fetchone()

    if not row:
        return None

    similarity = float(row[6])
    if similarity < SIMILARITY_THRESHOLD:
        logger.debug(f"Cache miss: melhor similaridade={similarity:.3f} < {SIMILARITY_THRESHOLD}")
        return None

    # Incrementa hit_count
    await db.execute(
        text("UPDATE semantic_cache SET hit_count = hit_count + 1 WHERE id = :id"),
        {"id": row[0]},
    )
    await db.commit()

    logger.info(f"Cache HIT: similarity={similarity:.3f}, pergunta='{question[:60]}'")
    return {
        "answer": row[1],
        "citations": row[2] or [],
        "query_original": row[3],
        "query_rewritten": row[4] or "",
        "model_used": (row[5] or "") + " (cached)",
    }


async def cache_response(
    db: AsyncSession,
    question: str,
    answer: str,
    citations: List[Dict],
    query_rewritten: str,
    model_used: str,
) -> None:
    """
    Armazena uma resposta aprovada (👍) no cache semântico.
    Chamado pelo endpoint de feedback quando rating == 'thumbs_up'.
    """
    embedding = await generate_single_embedding(question)
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    import json
    await db.execute(
        text("""
            INSERT INTO semantic_cache
                (question_embedding, question_original, answer, citations, query_rewritten, model_used)
            VALUES
                (CAST(:emb AS vector), :question, :answer, :citations, :query_rewritten, :model_used)
        """),
        {
            "emb": embedding_str,
            "question": question,
            "answer": answer,
            "citations": json.dumps(citations),
            "query_rewritten": query_rewritten,
            "model_used": model_used,
        },
    )
    await db.commit()
    logger.info(f"Resposta cacheada: '{question[:60]}'")


async def invalidate_cache(db: AsyncSession) -> int:
    """
    Limpa todo o cache semântico.
    Chamado após upload de novos documentos — respostas antigas podem estar incompletas.
    Retorna número de entradas removidas.
    """
    result = await db.execute(text("DELETE FROM semantic_cache"))
    await db.commit()
    count = result.rowcount
    if count:
        logger.info(f"Cache semântico invalidado: {count} entradas removidas")
    return count
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/semantic_cache.py
git commit -m "feat(cache): semantic_cache — get/set/invalidate com pgvector (threshold 0.92, TTL 7d)"
```

---

## Task 4: API endpoint POST /chat/feedback

**Files:**
- Create: `backend/app/api/feedback.py`
- Modify: `backend/app/main.py`

**Contexto:** O endpoint recebe `{message_id, rating}`, verifica que a mensagem pertence ao usuário logado (segurança), salva o feedback, atualiza quality_score, e se for 👍 popula o cache semântico. Precisa buscar o conteúdo da mensagem (question do usuário + answer do assistente) para cachear.

- [ ] **Step 1: Criar backend/app/api/feedback.py**

```python
"""
Kyotech AI — API de Feedback
"""
from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.auth import CurrentUser, get_current_user
from app.core.database import get_db
from app.services.feedback_repository import record_feedback, get_feedback
from app.services.semantic_cache import cache_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Feedback"])


class FeedbackRequest(BaseModel):
    message_id: str
    rating: Literal["thumbs_up", "thumbs_down"]


class FeedbackResponse(BaseModel):
    accepted: bool
    message: str


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        message_id = UUID(request.message_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="message_id inválido")

    # Verifica que a mensagem pertence a uma sessão do usuário (segurança)
    ownership = await db.execute(
        text("""
            SELECT cm.id, cm.content, cm.citations, cm.metadata,
                   -- busca a pergunta do usuário (mensagem anterior)
                   (SELECT content FROM chat_messages
                    WHERE session_id = cm.session_id
                      AND role = 'user'
                      AND created_at < cm.created_at
                    ORDER BY created_at DESC LIMIT 1) AS user_question
            FROM chat_messages cm
            JOIN chat_sessions cs ON cm.session_id = cs.id
            WHERE cm.id = :msg_id
              AND cs.user_id = :user_id
              AND cm.role = 'assistant'
        """),
        {"msg_id": str(message_id), "user_id": user.id},
    )
    row = ownership.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail="Mensagem não encontrada ou sem permissão"
        )

    answer = row[1]
    citations = row[2] or []
    metadata = row[3] or {}
    user_question = row[4]

    # Salvar feedback + atualizar quality_score em transação única
    inserted = await record_feedback(db, message_id, request.rating)
    if not inserted:
        return FeedbackResponse(
            accepted=False,
            message="Feedback já registrado para esta mensagem"
        )

    # Se 👍 e há pergunta do usuário: cachear a resposta
    if request.rating == "thumbs_up" and user_question:
        query_rewritten = metadata.get("query_rewritten", "")
        model_used = metadata.get("model_used", "")
        try:
            await cache_response(
                db=db,
                question=user_question,
                answer=answer,
                citations=citations,
                query_rewritten=query_rewritten,
                model_used=model_used,
            )
        except Exception as e:
            # Não falha o feedback se o cache falhar
            logger.error(f"Erro ao cachear resposta: {e}")

    logger.info(
        f"[{user.id}] Feedback '{request.rating}' registrado para mensagem {message_id}"
    )
    return FeedbackResponse(accepted=True, message="Feedback registrado com sucesso")
```

- [ ] **Step 2: Registrar o router em main.py**

Abrir `backend/app/main.py` e adicionar logo após os outros imports de router:

```python
from app.api.feedback import router as feedback_router
```

E logo após os outros `app.include_router(...)`:

```python
app.include_router(feedback_router, prefix="/api/v1")
```

- [ ] **Step 3: Testar manualmente (opcional antes do commit)**

```bash
cd backend
uvicorn app.main:app --reload
# POST /api/v1/chat/feedback com {"message_id": "<uuid>", "rating": "thumbs_up"}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/feedback.py backend/app/main.py
git commit -m "feat(feedback): endpoint POST /chat/feedback — salva rating, quality_score e cache semântico"
```

---

## Task 5: chat.py — retornar message_id + integrar semantic cache

**Files:**
- Modify: `backend/app/api/chat.py`

**Contexto:** Duas mudanças independentes:
1. O `message_id` da mensagem do assistente (gerado por `add_message`) deve ser retornado no `ChatResponse` para que o frontend possa vincular o feedback.
2. Antes de rodar o pipeline RAG completo, checar o semantic cache. Se hit, retornar direto sem chamar OpenAI.

- [ ] **Step 1: Editar chat.py**

Adicionar `message_id` em `ChatResponse`:

```python
class ChatResponse(BaseModel):
    answer: str
    citations: List[CitationResponse]
    query_original: str
    query_rewritten: str
    total_sources: int
    model_used: str
    session_id: str
    message_id: str  # ID da mensagem do assistente para vincular feedback
```

No endpoint `ask_question`, adicionar import do cache no topo do arquivo:

```python
from app.services.semantic_cache import get_cached_response
```

Após a linha que resolve a sessão (após `await chat_repository.add_message(db, session_id, "user", question)`), adicionar verificação de cache **antes** do pipeline RAG:

```python
# Verificar semantic cache (respostas aprovadas anteriormente)
cached = await get_cached_response(db, question)
if cached:
    logger.info(f"[{user.id}] Cache HIT — retornando resposta cacheada")
    # Persistir mensagem do assistente (cacheada)
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
        CitationResponse(**c) for c in cached["citations"]
    ] if cached["citations"] else []
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

E no retorno final do pipeline RAG, capturar o `message_id` retornado por `add_message` e incluí-lo:

```python
# add_message já retorna UUID — capturar
assistant_msg_id = await chat_repository.add_message(
    db, session_id, "assistant", rag_response.answer,
    citations=citations_json, metadata=metadata_json,
)

return ChatResponse(
    answer=rag_response.answer,
    citations=citations,
    query_original=rag_response.query_original,
    query_rewritten=rag_response.query_rewritten,
    total_sources=rag_response.total_sources,
    model_used=rag_response.model_used,
    session_id=str(session_id),
    message_id=str(assistant_msg_id),
)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/chat.py
git commit -m "feat(chat): retornar message_id no ChatResponse + semantic cache check antes do pipeline RAG"
```

---

## Task 6: search.py — incorporar quality_score no ranking

**Files:**
- Modify: `backend/app/services/search.py`

**Contexto:** O `quality_score` nos chunks é um float que começa em 0 e varia entre -1.0 e +2.0 (clamp definido em feedback_repository.py). Ele deve ser recuperado junto com os chunks na busca e aplicado como boost adicional no score híbrido. O peso `QUALITY_WEIGHT = 0.15` foi escolhido para ser significativo mas não dominar o score semântico.

- [ ] **Step 1: Modificar vector_search para retornar quality_score**

No `SearchResult` dataclass, adicionar campo:

```python
@dataclass
class SearchResult:
    chunk_id: str
    content: str
    page_number: int
    similarity: float
    document_id: str
    doc_type: str
    equipment_key: str
    published_date: date
    source_filename: str
    storage_path: str
    search_type: str
    document_version_id: str = ""
    quality_score: float = 0.0  # ← novo campo
```

Em `vector_search`, adicionar `c.quality_score` no SELECT:

```sql
SELECT
    c.id AS chunk_id,
    c.content,
    c.page_number,
    1 - (c.embedding <=> cast(:embedding AS vector)) AS similarity,
    d.id AS document_id,
    d.doc_type,
    d.equipment_key,
    cv.published_date,
    cv.source_filename,
    cv.storage_path,
    cv.id AS version_id,
    c.quality_score          -- ← novo
FROM chunks c
...
```

E no mapeamento do resultado (índice 11 para quality_score):

```python
SearchResult(
    ...
    document_version_id=str(row[10]),
    quality_score=float(row[11] or 0.0),  # ← novo
    search_type="vector",
)
```

Fazer o mesmo em `text_search` (adicionar `c.quality_score` no SELECT, índice 11).

- [ ] **Step 2: Aplicar quality_score boost em hybrid_search**

Após a constante existente, adicionar:

```python
QUALITY_WEIGHT = 0.15
```

No loop de fusão de resultados de `hybrid_search`, adicionar o boost de quality_score **após os boosts de equipment e doc_type e ANTES da linha `sorted_ids = sorted(...)`**:

```python
# Boost por quality_score acumulado via feedback
# ATENÇÃO: deve ficar antes de "sorted_ids = sorted(scores, ...)" para afetar o ranking
for chunk_id, result in merged.items():
    if result.quality_score != 0.0:
        scores[chunk_id] += result.quality_score * QUALITY_WEIGHT

# Ordena por score combinado  ← esta linha já existe, não duplicar
sorted_ids = sorted(scores, key=lambda k: scores[k], reverse=True)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/search.py
git commit -m "feat(search): quality_score como boost no ranking híbrido (weight=0.15)"
```

---

## Task 7: ingestion.py — invalidar cache após upload bem-sucedido

**Files:**
- Modify: `backend/app/services/ingestion.py`

**Contexto:** Quando novos documentos são adicionados, respostas cacheadas podem estar incompletas (não incluem o novo conteúdo). Invalidar o cache garante que a próxima pergunta similar passe pelo pipeline completo e potencialmente seja melhor.

- [ ] **Step 1: Adicionar chamada de invalidação ao final da ingestion bem-sucedida**

No topo de `ingestion.py`, adicionar import:

```python
from app.services.semantic_cache import invalidate_cache
```

Logo após o log `✅ Ingestion completa`, antes do `return IngestionResult(...)`, envolver em try/except isolado para que falha no cache não mascare ingestion bem-sucedida:

```python
# Invalidar cache semântico — novo documento pode melhorar respostas futuras
# try/except isolado: falha no cache não deve retornar erro de ingestion
try:
    await invalidate_cache(db)
except Exception as cache_err:
    logger.warning(f"Falha ao invalidar cache semântico (não crítico): {cache_err}")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/ingestion.py
git commit -m "feat(ingestion): invalidar semantic cache após upload bem-sucedido"
```

---

## Task 8: Frontend — tipos, api.ts e FeedbackWidget

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/components/chat/FeedbackWidget.tsx`

**Contexto:** O `message_id` vem do backend no `ChatResponse`. Precisa ser armazenado no tipo `Message` para que o `FeedbackWidget` possa enviá-lo. O widget exibe 👍/👎, gerencia estado local (idle → loading → done/error) e não bloqueia o UI — é fire-and-forget do ponto de vista do usuário.

- [ ] **Step 1: Atualizar frontend/src/types/index.ts**

Adicionar `message_id` em `Message` e `ChatResponse`:

```typescript
export interface Message {
  id: string;           // UUID frontend (React key)
  message_id?: string;  // UUID do backend — usado para feedback
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  isLoading?: boolean;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  query_original: string;
  query_rewritten: string;
  total_sources: number;
  model_used: string;
  session_id: string;
  message_id: string;  // ← novo
}

// Tipo para o rating
export type FeedbackRating = "thumbs_up" | "thumbs_down";
```

- [ ] **Step 2: Adicionar submitFeedback em frontend/src/lib/api.ts**

```typescript
export async function submitFeedback(
  messageId: string,
  rating: "thumbs_up" | "thumbs_down",
): Promise<void> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/chat/feedback`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ message_id: messageId, rating }),
      },
      10_000,
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
}
```

- [ ] **Step 3: Criar frontend/src/components/chat/FeedbackWidget.tsx**

```tsx
"use client";

import { useState } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { submitFeedback } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { FeedbackRating } from "@/types";

type FeedbackState = "idle" | "loading" | "done" | "error";

interface FeedbackWidgetProps {
  messageId: string;
}

export function FeedbackWidget({ messageId }: FeedbackWidgetProps) {
  const [feedbackState, setFeedbackState] = useState<FeedbackState>("idle");
  const [selected, setSelected] = useState<FeedbackRating | null>(null);

  async function handleFeedback(rating: FeedbackRating) {
    if (feedbackState !== "idle") return;
    setFeedbackState("loading");
    setSelected(rating);
    try {
      await submitFeedback(messageId, rating);
      setFeedbackState("done");
    } catch {
      setFeedbackState("error");
      setSelected(null);
    }
  }

  if (feedbackState === "done") {
    return (
      <div className="flex items-center gap-1 text-xs text-muted-foreground/60">
        {selected === "thumbs_up" ? (
          <ThumbsUp className="h-3.5 w-3.5 text-green-500" />
        ) : (
          <ThumbsDown className="h-3.5 w-3.5 text-red-400" />
        )}
        <span>Obrigado pelo feedback</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => handleFeedback("thumbs_up")}
        disabled={feedbackState === "loading"}
        title="Resposta útil"
        className={cn(
          "rounded p-1 transition-colors hover:bg-green-500/10 hover:text-green-500",
          "text-muted-foreground/40 disabled:cursor-not-allowed",
          feedbackState === "error" && "text-muted-foreground/20",
        )}
      >
        <ThumbsUp className="h-3.5 w-3.5" />
      </button>
      <button
        onClick={() => handleFeedback("thumbs_down")}
        disabled={feedbackState === "loading"}
        title="Resposta incorreta ou incompleta"
        className={cn(
          "rounded p-1 transition-colors hover:bg-red-500/10 hover:text-red-400",
          "text-muted-foreground/40 disabled:cursor-not-allowed",
          feedbackState === "error" && "text-muted-foreground/20",
        )}
      >
        <ThumbsDown className="h-3.5 w-3.5" />
      </button>
      {feedbackState === "error" && (
        <span className="text-xs text-destructive">Erro ao registrar</span>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts \
        frontend/src/components/chat/FeedbackWidget.tsx
git commit -m "feat(frontend): tipos message_id, submitFeedback API, FeedbackWidget thumbs up/down"
```

---

## Task 9: MessageBubble.tsx + ChatWindow.tsx — integrar FeedbackWidget

**Files:**
- Modify: `frontend/src/components/chat/MessageBubble.tsx`
- Modify: `frontend/src/components/chat/ChatWindow.tsx`

**Contexto:** O `FeedbackWidget` deve aparecer apenas em mensagens do assistente que não estejam carregando e que tenham `message_id` (respostas do backend, não respostas de erro locais). O `ChatWindow` precisa passar o `message_id` da API response para a mensagem.

- [ ] **Step 1: Modificar ChatWindow.tsx para capturar e salvar message_id**

No objeto `assistantMsg`, adicionar `message_id`:

```typescript
const assistantMsg: Message = {
  id: loadingMsg.id,
  message_id: data.message_id,  // ← vem do ChatResponse
  role: "assistant",
  content: data.answer,
  citations: data.citations,
};
```

Ao carregar mensagens de sessões existentes (`getSessionMessages`), o `message_id` não vem da API de sessões — os botões de feedback ficam ocultos nesses casos (apenas `message_id` presente ativa o widget).

- [ ] **Step 2: Modificar MessageBubble.tsx para renderizar FeedbackWidget**

Adicionar import:

```typescript
import { FeedbackWidget } from "./FeedbackWidget";
```

Dentro do bubble, após o bloco de citações (footer), adicionar o widget para mensagens do assistente com `message_id`:

```tsx
{/* Feedback — apenas em respostas do assistente com message_id */}
{!isUser && !message.isLoading && message.message_id && (
  <div className="mt-2 flex justify-end">
    <FeedbackWidget messageId={message.message_id} />
  </div>
)}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/chat/ChatWindow.tsx \
        frontend/src/components/chat/MessageBubble.tsx
git commit -m "feat(chat): integrar FeedbackWidget nas respostas do assistente"
```

---

## Task 10: Push e validação em produção

- [ ] **Step 1: Push**

```bash
git push origin main
```

- [ ] **Step 2: Aguardar deploy (~3 min) e validar**

Checklist de validação:
1. Fazer uma pergunta no chat → resposta aparece com 👍/👎 no canto inferior direito da bubble
2. Clicar 👍 → botões desaparecem, aparece "Obrigado pelo feedback"
3. Fazer a mesma pergunta novamente → deve vir mais rápido (cache hit — `model_used` terá sufixo `(cached)`)
4. Fazer upload de um novo PDF → fazer a mesma pergunta → cache invalidado, pipeline completo rodou
5. Logs do backend devem mostrar: `Cache HIT: similarity=0.9X` na segunda pergunta

- [ ] **Step 3: Mover cards Jira**

Mover IA-96, IA-97, IA-98, IA-99 e IA-88 para **Concluído**.

---

## Notas Adicionais

**Por que o quality_score usa delta assimétrico (+0.05 / -0.03)?**
Um conteúdo novo (quality_score = 0) compete em pé de igualdade. Penalizar menos evita que chunks legítimos sejam suprimidos por um ou dois feedbacks negativos isolados. Com o tempo, chunks consistentemente ruins acumulam penalidade suficiente para cair no ranking.

**Por que o cache é invalidado completamente e não por pergunta?**
Dado o volume atual (~10-100 documentos, dezenas de usuários), a simplicidade supera a granularidade. Uma resposta cacheada sobre "limpeza de sensor" pode estar incompleta se um novo manual foi carregado. Limpar tudo garante frescor.

**Feedback em sessões antigas (histórico):**
Mensagens carregadas via `getSessionMessages` não têm `message_id` no frontend (a API de sessões não o retorna). O FeedbackWidget só aparece em mensagens da sessão atual. Isso é intencional — feedback em respostas antigas sem contexto pode ser impreciso.
