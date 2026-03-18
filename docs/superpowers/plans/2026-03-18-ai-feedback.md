# AI Feedback — Avaliação de Respostas pelo Técnico

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que o técnico avalie cada resposta da IA com thumbs up/down. Se negativo, o usuário pode escrever em uma linha o motivo. Os dados são armazenados para análise e melhoria futura do modelo.

**Architecture:** Nova tabela `message_feedback` vinculada a `chat_messages`. Endpoint `POST /api/v1/chat/feedback` recebe `message_id`, `rating` (positive/negative) e `comment` opcional. No frontend, cada bolha de resposta do assistente ganha os botões de feedback; o input de texto aparece apenas ao selecionar "negativo". A avaliação é salva uma vez por mensagem (upsert).

**Tech Stack:** PostgreSQL (nova tabela), FastAPI (novo endpoint), React (estado por messageId), Shadcn/ui (ThumbsUp/ThumbsDown icons via lucide-react).

---

## Mapa de Arquivos

| Ação | Arquivo |
|---|---|
| Criar | `backend/migrations/004_message_feedback.sql` |
| Criar | `backend/app/api/feedback.py` |
| Modificar | `backend/app/main.py` (registrar router) |
| Modificar | `frontend/src/components/chat/MessageBubble.tsx` |
| Criar | `frontend/src/components/chat/FeedbackWidget.tsx` |
| Modificar | `frontend/src/lib/api.ts` |
| Modificar | `frontend/src/types/index.ts` |
| Criar | `backend/tests/test_feedback.py` |

---

## Task 1: Migration do Banco

**Files:**
- Create: `backend/migrations/004_message_feedback.sql`

- [ ] **Step 1: Escrever a migration**

  ```sql
  -- backend/migrations/004_message_feedback.sql
  -- Kyotech AI — Fase 4: Feedback de respostas da IA

  CREATE TABLE IF NOT EXISTS message_feedback (
      id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
      message_id UUID NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
      user_id VARCHAR(255) NOT NULL,
      rating VARCHAR(10) NOT NULL CHECK (rating IN ('positive', 'negative')),
      comment TEXT,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      UNIQUE (message_id, user_id)  -- um feedback por usuário por mensagem
  );

  CREATE INDEX IF NOT EXISTS idx_feedback_message ON message_feedback(message_id);
  CREATE INDEX IF NOT EXISTS idx_feedback_rating ON message_feedback(rating, created_at DESC);
  ```

- [ ] **Step 2: Executar a migration**

  ```bash
  cd backend
  source .venv/bin/activate
  psql $DATABASE_URL -f migrations/004_message_feedback.sql
  ```

  Esperado: `CREATE TABLE`, `CREATE INDEX`, `CREATE INDEX`

- [ ] **Step 3: Commit**

  ```bash
  git add backend/migrations/004_message_feedback.sql
  git commit -m "feat(db): tabela message_feedback para avaliação de respostas"
  ```

---

## Task 2: Endpoint de Feedback

**Files:**
- Create: `backend/app/api/feedback.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_feedback.py`

- [ ] **Step 1: Escrever os testes**

  ```python
  # backend/tests/test_feedback.py
  from fastapi.testclient import TestClient
  from app.main import app

  client = TestClient(app)

  def test_submit_positive_feedback():
      """Feedback positivo sem comentário deve ser aceito."""
      response = client.post(
          "/api/v1/chat/feedback",
          json={
              "message_id": "00000000-0000-0000-0000-000000000001",
              "rating": "positive",
          },
          headers={"Authorization": "Bearer fake"},
      )
      # Pode retornar 404 se o message_id não existe no DB de teste
      # O importante é que 400 não aparece para payload válido
      assert response.status_code in (200, 404)

  def test_submit_feedback_invalid_rating():
      """Rating inválido deve retornar 422."""
      response = client.post(
          "/api/v1/chat/feedback",
          json={
              "message_id": "00000000-0000-0000-0000-000000000001",
              "rating": "maybe",
          },
          headers={"Authorization": "Bearer fake"},
      )
      assert response.status_code == 422

  def test_submit_negative_feedback_requires_comment_optional():
      """Feedback negativo sem comentário deve ser aceito (comentário é opcional)."""
      response = client.post(
          "/api/v1/chat/feedback",
          json={
              "message_id": "00000000-0000-0000-0000-000000000001",
              "rating": "negative",
          },
          headers={"Authorization": "Bearer fake"},
      )
      assert response.status_code in (200, 404)
  ```

- [ ] **Step 2: Rodar para ver falhar**

  ```bash
  pytest tests/test_feedback.py -v
  ```

  Esperado: FAIL — endpoint não existe

- [ ] **Step 3: Implementar `backend/app/api/feedback.py`**

  ```python
  """
  Kyotech AI — API de Feedback de Respostas
  """
  from __future__ import annotations

  import logging
  from typing import Optional
  from uuid import UUID

  from fastapi import APIRouter, Depends, HTTPException
  from pydantic import BaseModel, field_validator
  from sqlalchemy import text
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.core.auth import CurrentUser, get_current_user
  from app.core.database import get_db

  logger = logging.getLogger(__name__)

  router = APIRouter(prefix="/chat", tags=["Feedback"])


  class FeedbackRequest(BaseModel):
      message_id: str
      rating: str
      comment: Optional[str] = None

      @field_validator("rating")
      @classmethod
      def validate_rating(cls, v: str) -> str:
          if v not in ("positive", "negative"):
              raise ValueError("rating deve ser 'positive' ou 'negative'")
          return v

      @field_validator("comment")
      @classmethod
      def trim_comment(cls, v: Optional[str]) -> Optional[str]:
          if v:
              v = v.strip()
              return v[:500] if len(v) > 500 else v  # max 500 chars
          return None


  @router.post("/feedback", status_code=200)
  async def submit_feedback(
      request: FeedbackRequest,
      user: CurrentUser = Depends(get_current_user),
      db: AsyncSession = Depends(get_db),
  ):
      # Verificar se a mensagem existe
      result = await db.execute(
          text("SELECT id FROM chat_messages WHERE id = :mid"),
          {"mid": request.message_id},
      )
      if not result.fetchone():
          raise HTTPException(status_code=404, detail="Mensagem não encontrada.")

      # Upsert: atualiza se o usuário já avaliou esta mensagem
      await db.execute(
          text("""
              INSERT INTO message_feedback (message_id, user_id, rating, comment)
              VALUES (:message_id, :user_id, :rating, :comment)
              ON CONFLICT (message_id, user_id)
              DO UPDATE SET
                  rating = EXCLUDED.rating,
                  comment = EXCLUDED.comment,
                  created_at = NOW()
          """),
          {
              "message_id": request.message_id,
              "user_id": user.id,
              "rating": request.rating,
              "comment": request.comment,
          },
      )
      await db.commit()

      logger.info(
          f"Feedback: user={user.id} message={request.message_id} rating={request.rating}"
      )
      return {"ok": True}
  ```

- [ ] **Step 4: Registrar o router em `main.py`**

  Em `backend/app/main.py`, localizar onde os routers são registrados e adicionar:

  ```python
  from app.api.feedback import router as feedback_router
  # ...
  app.include_router(feedback_router, prefix="/api/v1")
  ```

- [ ] **Step 5: Rodar os testes**

  ```bash
  pytest tests/test_feedback.py -v
  ```

  Esperado: todos PASS

- [ ] **Step 6: Commit**

  ```bash
  git add backend/app/api/feedback.py backend/app/main.py backend/tests/test_feedback.py
  git commit -m "feat(api): endpoint POST /chat/feedback para avaliação de respostas"
  ```

---

## Task 3: Frontend — FeedbackWidget

**Files:**
- Create: `frontend/src/components/chat/FeedbackWidget.tsx`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Adicionar `submitFeedback` em `lib/api.ts`**

  ```typescript
  export async function submitFeedback(
    messageId: string,
    rating: "positive" | "negative",
    comment?: string
  ): Promise<void> {
    const auth = await authHeaders();
    let res: Response;
    try {
      res = await fetchWithTimeout(
        `${API_BASE}/api/v1/chat/feedback`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...auth },
          body: JSON.stringify({ message_id: messageId, rating, comment }),
        },
        10_000
      );
    } catch (err) {
      handleFetchError(err);
    }
    if (!res.ok) throw new Error(await parseApiError(res));
  }
  ```

- [ ] **Step 2: Criar `FeedbackWidget.tsx`**

  ```tsx
  "use client";

  import { useState } from "react";
  import { ThumbsUp, ThumbsDown } from "lucide-react";
  import { submitFeedback } from "@/lib/api";
  import { cn } from "@/lib/utils";
  import { Textarea } from "@/components/ui/textarea";
  import { Button } from "@/components/ui/button";

  interface FeedbackWidgetProps {
    messageId: string;
  }

  type State = "idle" | "negative_comment" | "submitted";

  export function FeedbackWidget({ messageId }: FeedbackWidgetProps) {
    const [state, setState] = useState<State>("idle");
    const [selected, setSelected] = useState<"positive" | "negative" | null>(null);
    const [comment, setComment] = useState("");
    const [submitting, setSubmitting] = useState(false);

    async function handleRate(rating: "positive" | "negative") {
      setSelected(rating);
      if (rating === "positive") {
        await send(rating);
      } else {
        setState("negative_comment");
      }
    }

    async function send(rating: "positive" | "negative", text?: string) {
      setSubmitting(true);
      try {
        await submitFeedback(messageId, rating, text || undefined);
        setState("submitted");
      } catch {
        // falha silenciosa — feedback é best-effort
      } finally {
        setSubmitting(false);
      }
    }

    if (state === "submitted") {
      return (
        <p className="mt-1 text-xs text-muted-foreground">
          Obrigado pelo feedback!
        </p>
      );
    }

    return (
      <div className="mt-2 space-y-2">
        {state === "idle" && (
          <div className="flex items-center gap-1">
            <span className="text-xs text-muted-foreground mr-1">
              Resposta útil?
            </span>
            <button
              onClick={() => handleRate("positive")}
              className={cn(
                "rounded p-1 transition-colors hover:bg-green-100 hover:text-green-600",
                selected === "positive" && "bg-green-100 text-green-600"
              )}
              title="Sim, foi útil"
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => handleRate("negative")}
              className={cn(
                "rounded p-1 transition-colors hover:bg-red-100 hover:text-red-500",
                selected === "negative" && "bg-red-100 text-red-500"
              )}
              title="Não foi útil"
            >
              <ThumbsDown className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {state === "negative_comment" && (
          <div className="space-y-2 rounded-lg border border-muted p-3">
            <p className="text-xs text-muted-foreground">
              O que poderia ser melhor? (opcional)
            </p>
            <Textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Ex: A resposta não mencionou o procedimento correto..."
              className="h-16 resize-none text-sm"
              maxLength={500}
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                className="flex-1 text-xs"
                onClick={() => send("negative")}
                disabled={submitting}
              >
                Enviar sem comentário
              </Button>
              <Button
                size="sm"
                className="flex-1 text-xs"
                onClick={() => send("negative", comment)}
                disabled={submitting || !comment.trim()}
              >
                Enviar feedback
              </Button>
            </div>
          </div>
        )}
      </div>
    );
  }
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add frontend/src/components/chat/FeedbackWidget.tsx frontend/src/lib/api.ts
  git commit -m "feat(ui): FeedbackWidget com thumbs up/down e comentário opcional"
  ```

---

## Task 4: Integrar FeedbackWidget nas Mensagens

**Files:**
- Modify: `frontend/src/components/chat/MessageBubble.tsx`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Verificar que `MessageBubble` recebe `messageId`**

  Ler `frontend/src/components/chat/MessageBubble.tsx` e verificar se o componente recebe o `id` da mensagem como prop.

  Se não, adicionar `messageId?: string` às props do componente.

- [ ] **Step 2: Adicionar `FeedbackWidget` na bolha do assistente**

  No render da bolha do assistente (role === "assistant"), após o conteúdo da mensagem:

  ```tsx
  import { FeedbackWidget } from "./FeedbackWidget";

  // Dentro do render, após o conteúdo da mensagem:
  {role === "assistant" && messageId && (
    <FeedbackWidget messageId={messageId} />
  )}
  ```

- [ ] **Step 3: Verificar que `ChatWindow` passa o `messageId`**

  Em `ChatWindow.tsx`, verificar se o `id` da mensagem do backend (`session_id` + id da mensagem) é passado para `MessageBubble`. Se necessário, o `ChatResponse` precisa incluir o `message_id`.

  **Alternativa simples:** O feedback pode usar um ID gerado no frontend com `crypto.randomUUID()` e persistido localmente (menos ideal) — mas o ideal é ter o `message_id` real do banco. Verificar se `ChatResponse` retorna o `message_id` no endpoint `/chat/ask`.

  Se não retorna: adicionar `message_id: str` ao `ChatResponse` em `backend/app/api/chat.py` e ao salvar a mensagem do assistente capturar o ID retornado pelo `chat_repository.add_message`.

- [ ] **Step 4: Testar no browser**

  1. Fazer uma pergunta no chat
  2. Verificar botões thumbs up/down aparecem na resposta
  3. Clicar thumbs up → "Obrigado pelo feedback!" aparece
  4. Em outra resposta, clicar thumbs down → input aparece
  5. Escrever comentário e clicar "Enviar feedback"
  6. Verificar no banco: `SELECT * FROM message_feedback;`

- [ ] **Step 5: Commit final**

  ```bash
  git add frontend/src/components/chat/MessageBubble.tsx frontend/src/types/index.ts
  git commit -m "feat(chat): integrar FeedbackWidget nas respostas do assistente"
  ```

---

## Notas

- O feedback é **best-effort**: se a chamada falhar, nenhum erro é exibido ao usuário — não queremos interromper o fluxo de trabalho do técnico.
- Para análise futura: `SELECT rating, COUNT(*), AVG(CASE WHEN comment IS NOT NULL THEN 1 ELSE 0 END) FROM message_feedback GROUP BY rating;`
- O comentário é limitado a 500 caracteres no backend.
