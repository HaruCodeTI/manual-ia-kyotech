# UI Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar favicon da marca, redesenho da página de stats com métricas de uso, e welcome state estilo Gemini na tela de chat com animação Framer Motion.

**Architecture:** Quatro áreas independentes: (1) substituição de favicon via convenção Next.js App Router, (2) novo endpoint backend + redesign do componente StatsCards com duas seções, (3) informacional sobre Clerk (sem código), (4) reescrita do ChatWindow com welcome state animado usando Framer Motion layoutId.

**Tech Stack:** Next.js 15 App Router, FastAPI, SQLAlchemy async, Tailwind CSS, shadcn/ui, Clerk (`@clerk/nextjs`), `framer-motion@^11`, lucide-react, pytest/anyio

**Spec de referência:** `docs/superpowers/specs/2026-03-20-ui-improvements-design.md`

---

## Mapa de Arquivos

| Arquivo | Ação | Responsabilidade |
|---------|------|-----------------|
| `frontend/src/app/icon.png` | Criar | Favicon da marca (cópia de `public/kyotech-icon.png`) |
| `frontend/src/app/favicon.ico` | Deletar | Remover favicon padrão que sobrescreve o novo |
| `backend/app/services/repository.py` | Modificar | Adicionar `docs_without_chunks` em `get_ingestion_stats()` + nova `get_usage_stats()` |
| `backend/app/api/upload.py` | Modificar | Atualizar `StatsResponse`, adicionar `UsageStatsResponse` + endpoint `/stats/usage` |
| `backend/tests/integration/test_upload_api.py` | Modificar | Atualizar teste de stats + adicionar testes para `/stats/usage` |
| `frontend/src/types/index.ts` | Modificar | Adicionar `docs_without_chunks` em `StatsResponse` + nova `UsageStatsResponse` |
| `frontend/src/lib/api.ts` | Modificar | Atualizar import + adicionar `getUsageStats()` |
| `frontend/src/components/dashboard/StatsCards.tsx` | Reescrever | Duas seções com loading/erro individuais |
| `frontend/src/app/stats/page.tsx` | Modificar | Atualizar `<h1>` para "Estatísticas" |
| `frontend/src/components/chat/ChatInput.tsx` | Modificar | Nova prop `variant?: "welcome" \| "bottom"` |
| `frontend/src/components/chat/ChatWindow.tsx` | Reescrever | Welcome state, `hasStarted`, `LayoutGroup`, `AnimatePresence`, `motion.div layoutId` |
| `frontend/package.json` | Modificar | Adicionar `framer-motion@^11` |

---

## Task 1: Favicon

**Files:**
- Create: `frontend/src/app/icon.png`
- Delete: `frontend/src/app/favicon.ico`

- [ ] **Step 1: Copiar o ícone da marca para a pasta app/**

```bash
cp frontend/public/kyotech-icon.png frontend/src/app/icon.png
```

- [ ] **Step 2: Deletar o favicon padrão**

```bash
rm frontend/src/app/favicon.ico
```

O Next.js App Router detecta automaticamente `src/app/icon.png` e o usa como favicon. Nenhuma mudança em `layout.tsx` é necessária.

- [ ] **Step 3: Verificar no navegador**

Iniciar o servidor de desenvolvimento (`npm run dev` dentro de `frontend/`) e verificar na aba do browser que o favicon mostra o ícone Kyotech.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/icon.png
git rm frontend/src/app/favicon.ico
git commit -m "feat(frontend): substituir favicon padrão pelo ícone da marca Kyotech"
```

---

## Task 2: Stats — Backend

**Files:**
- Modify: `backend/app/services/repository.py`
- Modify: `backend/app/api/upload.py`
- Modify: `backend/tests/integration/test_upload_api.py`

### 2a: Atualizar teste existente de stats

- [ ] **Step 1: Atualizar o teste `test_get_stats_admin` para incluir `docs_without_chunks`**

Em `backend/tests/integration/test_upload_api.py`, localizar a função `test_get_stats_admin` e atualizar o mock:

```python
@pytest.mark.anyio
async def test_get_stats_admin(async_client):
    stats = {
        "equipments": 5,
        "documents": 10,
        "versions": 15,
        "chunks": 200,
        "docs_without_chunks": 2,  # novo campo
    }

    with patch("app.api.upload.repository.get_ingestion_stats", new_callable=AsyncMock, return_value=stats):
        resp = await async_client.get("/api/v1/upload/stats")

    assert resp.status_code == 200
    data = resp.json()
    assert data["documents"] == 10
    assert data["versions"] == 15
    assert data["docs_without_chunks"] == 2  # novo campo
```

- [ ] **Step 2: Executar para verificar que falha**

```bash
cd backend && python -m pytest tests/integration/test_upload_api.py::test_get_stats_admin -v
```

Esperado: FAIL — `docs_without_chunks` não existe no `StatsResponse`.

### 2b: Implementar backend de stats

- [ ] **Step 3: Atualizar `StatsResponse` em `backend/app/api/upload.py`**

Localizar a classe `StatsResponse` (próximo ao topo do arquivo) e adicionar o novo campo:

```python
class StatsResponse(BaseModel):
    equipments: int
    documents: int
    versions: int
    chunks: int
    docs_without_chunks: int  # novo
```

- [ ] **Step 4: Atualizar `get_ingestion_stats()` em `backend/app/services/repository.py`**

Localizar a função e substituí-la completamente:

```python
async def get_ingestion_stats(db: AsyncSession) -> Dict[str, int]:
    result = await db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM equipments) AS total_equipments,
            (SELECT COUNT(*) FROM documents) AS total_documents,
            (SELECT COUNT(*) FROM document_versions) AS total_versions,
            (SELECT COUNT(*) FROM chunks) AS total_chunks,
            (
                SELECT COUNT(*) FROM document_versions dv
                WHERE NOT EXISTS (
                    SELECT 1 FROM chunks c WHERE c.document_version_id = dv.id
                )
            ) AS docs_without_chunks
    """))
    row = result.fetchone()
    return {
        "equipments": row[0],
        "documents": row[1],
        "versions": row[2],
        "chunks": row[3],
        "docs_without_chunks": row[4],
    }
```

- [ ] **Step 5: Executar o teste atualizado para verificar que passa**

```bash
cd backend && python -m pytest tests/integration/test_upload_api.py::test_get_stats_admin -v
```

Esperado: PASS.

### 2c: Novo endpoint `/stats/usage`

- [ ] **Step 6: Escrever o teste do novo endpoint**

Adicionar ao final do arquivo `backend/tests/integration/test_upload_api.py`:

```python
@pytest.mark.anyio
async def test_get_usage_stats_admin(async_client):
    usage = {
        "total_sessions": 100,
        "total_messages": 350,
        "thumbs_up": 42,
        "thumbs_down": 8,
    }

    with patch("app.api.upload.repository.get_usage_stats", new_callable=AsyncMock, return_value=usage):
        resp = await async_client.get("/api/v1/upload/stats/usage")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sessions"] == 100
    assert data["total_messages"] == 350
    assert data["thumbs_up"] == 42
    assert data["thumbs_down"] == 8


@pytest.mark.anyio
async def test_technician_cannot_see_usage_stats(async_client_tech):
    resp = await async_client_tech.get("/api/v1/upload/stats/usage")
    assert resp.status_code == 403
```

- [ ] **Step 7: Executar para verificar que falha**

```bash
cd backend && python -m pytest tests/integration/test_upload_api.py::test_get_usage_stats_admin tests/integration/test_upload_api.py::test_technician_cannot_see_usage_stats -v
```

Esperado: FAIL — endpoint não existe.

- [ ] **Step 8: Adicionar `UsageStatsResponse` em `backend/app/api/upload.py`**

Logo após a definição de `StatsResponse`:

```python
class UsageStatsResponse(BaseModel):
    total_sessions: int
    total_messages: int
    thumbs_up: int
    thumbs_down: int
```

- [ ] **Step 9: Adicionar endpoint `/stats/usage` em `backend/app/api/upload.py`**

Logo após o endpoint `get_stats` existente:

```python
@router.get("/stats/usage", response_model=UsageStatsResponse)
async def get_usage_stats(
    _user: CurrentUser = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    stats = await repository.get_usage_stats(db)
    return UsageStatsResponse(**stats)
```

- [ ] **Step 10: Adicionar `get_usage_stats()` em `backend/app/services/repository.py`**

Logo após `get_ingestion_stats()`:

```python
async def get_usage_stats(db: AsyncSession) -> Dict[str, int]:
    result = await db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM chat_sessions) AS total_sessions,
            (SELECT COUNT(*) FROM chat_messages WHERE role = 'user') AS total_messages,
            (SELECT COUNT(*) FROM message_feedback WHERE rating = 'thumbs_up') AS thumbs_up,
            (SELECT COUNT(*) FROM message_feedback WHERE rating = 'thumbs_down') AS thumbs_down
    """))
    row = result.fetchone()
    return {
        "total_sessions": row[0],
        "total_messages": row[1],
        "thumbs_up": row[2],
        "thumbs_down": row[3],
    }
```

- [ ] **Step 11: Executar todos os testes de upload para verificar que passam**

```bash
cd backend && python -m pytest tests/integration/test_upload_api.py -v
```

Esperado: todos PASS.

- [ ] **Step 12: Commit**

```bash
git add backend/app/api/upload.py backend/app/services/repository.py backend/tests/integration/test_upload_api.py
git commit -m "feat(backend): adicionar docs_without_chunks em stats e novo endpoint /stats/usage"
```

---

## Task 3: Stats — Frontend

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Rewrite: `frontend/src/components/dashboard/StatsCards.tsx`
- Modify: `frontend/src/app/stats/page.tsx`

- [ ] **Step 1: Atualizar `StatsResponse` e adicionar `UsageStatsResponse` em `frontend/src/types/index.ts`**

Localizar a interface `StatsResponse` existente e adicionar o campo novo. Adicionar `UsageStatsResponse` logo abaixo:

```typescript
export interface StatsResponse {
  equipments: number;
  documents: number;
  versions: number;
  chunks: number;
  docs_without_chunks: number; // novo
}

export interface UsageStatsResponse {
  total_sessions: number;
  total_messages: number;
  thumbs_up: number;
  thumbs_down: number;
}
```

- [ ] **Step 2: Atualizar `frontend/src/lib/api.ts`**

**2a.** Atualizar a linha de import no topo (linha 1) para incluir `UsageStatsResponse`:

```typescript
import type { ChatResponse, UploadResponse, StatsResponse, UsageStatsResponse, ChatSession, FeedbackRating } from "@/types";
```

**2b.** Adicionar `getUsageStats()` logo após a função `getStats()` existente:

```typescript
export async function getUsageStats(): Promise<UsageStatsResponse> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/upload/stats/usage`,
      { headers: auth },
      30_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}
```

- [ ] **Step 3: Reescrever `frontend/src/components/dashboard/StatsCards.tsx`**

Substituir o conteúdo completo do arquivo:

```typescript
"use client";

import { useEffect, useState } from "react";
import { getStats, getUsageStats } from "@/lib/api";
import type { StatsResponse, UsageStatsResponse } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  FileText,
  Layers,
  AlertTriangle,
  MessageSquare,
  MessagesSquare,
  ThumbsUp,
  ThumbsDown,
  TrendingUp,
  Loader2,
  AlertCircle,
} from "lucide-react";

function StatCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {label}
        </CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-bold">{value}</p>
      </CardContent>
    </Card>
  );
}

function SectionLoading() {
  return (
    <div className="flex items-center justify-center py-10 text-muted-foreground">
      <Loader2 className="mr-2 h-5 w-5 animate-spin" />
      Carregando…
    </div>
  );
}

function SectionError({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-destructive">
      <AlertCircle className="h-5 w-5" />
      {message}
    </div>
  );
}

export function StatsCards() {
  const [base, setBase] = useState<StatsResponse | null>(null);
  const [usage, setUsage] = useState<UsageStatsResponse | null>(null);
  const [baseError, setBaseError] = useState("");
  const [usageError, setUsageError] = useState("");
  const [baseLoading, setBaseLoading] = useState(true);
  const [usageLoading, setUsageLoading] = useState(true);

  useEffect(() => {
    getStats()
      .then(setBase)
      .catch((e) => setBaseError(e instanceof Error ? e.message : "Erro ao carregar"))
      .finally(() => setBaseLoading(false));

    getUsageStats()
      .then(setUsage)
      .catch((e) => setUsageError(e instanceof Error ? e.message : "Erro ao carregar"))
      .finally(() => setUsageLoading(false));
  }, []);

  const satisfactionRate = (() => {
    if (!usage) return "—";
    const total = usage.thumbs_up + usage.thumbs_down;
    if (total === 0) return "—";
    return `${Math.round((usage.thumbs_up / total) * 100)}%`;
  })();

  return (
    <div className="space-y-8">
      {/* Seção: Base de Conhecimento */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Base de Conhecimento</h2>
        <Separator className="mb-4" />
        {baseLoading ? (
          <SectionLoading />
        ) : baseError ? (
          <SectionError message={baseError} />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard
              label="Documentos"
              value={base?.documents?.toLocaleString("pt-BR") ?? "—"}
              icon={FileText}
            />
            <StatCard
              label="Versões de Documentos"
              value={base?.versions?.toLocaleString("pt-BR") ?? "—"}
              icon={Layers}
            />
            <StatCard
              label="Documentos sem Indexação"
              value={base?.docs_without_chunks?.toLocaleString("pt-BR") ?? "—"}
              icon={AlertTriangle}
            />
          </div>
        )}
      </div>

      {/* Seção: Uso & Qualidade */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Uso & Qualidade</h2>
        <Separator className="mb-4" />
        {usageLoading ? (
          <SectionLoading />
        ) : usageError ? (
          <SectionError message={usageError} />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard
              label="Total de Conversas"
              value={usage?.total_sessions?.toLocaleString("pt-BR") ?? "—"}
              icon={MessageSquare}
            />
            <StatCard
              label="Total de Mensagens"
              value={usage?.total_messages?.toLocaleString("pt-BR") ?? "—"}
              icon={MessagesSquare}
            />
            <StatCard
              label="Feedbacks Positivos"
              value={usage?.thumbs_up?.toLocaleString("pt-BR") ?? "—"}
              icon={ThumbsUp}
            />
            <StatCard
              label="Feedbacks Negativos"
              value={usage?.thumbs_down?.toLocaleString("pt-BR") ?? "—"}
              icon={ThumbsDown}
            />
            <StatCard
              label="Taxa de Satisfação"
              value={satisfactionRate}
              icon={TrendingUp}
            />
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Atualizar `<h1>` em `frontend/src/app/stats/page.tsx`**

```typescript
import { StatsCards } from "@/components/dashboard/StatsCards";

export default function StatsPage() {
  return (
    <div className="h-full overflow-y-auto p-6">
      <h1 className="mb-6 text-2xl font-bold">Estatísticas</h1>
      <StatsCards />
    </div>
  );
}
```

- [ ] **Step 5: Verificar compilação TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Esperado: sem erros.

- [ ] **Step 6: Verificar visualmente no navegador**

Com o servidor rodando, navegar para `/stats` e verificar:
- Duas seções com títulos e separadores
- Cards responsivos (testar redimensionando a janela)
- Estados de loading individuais por seção

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts frontend/src/components/dashboard/StatsCards.tsx frontend/src/app/stats/page.tsx
git commit -m "feat(frontend): redesenhar stats page com seções de base de conhecimento e uso & qualidade"
```

---

## Task 4: Chat Visual — Gemini-style Welcome State

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/components/chat/ChatInput.tsx`
- Rewrite: `frontend/src/components/chat/ChatWindow.tsx`

### 4a: Instalar Framer Motion

- [ ] **Step 1: Instalar a dependência**

```bash
cd frontend && npm install framer-motion@^11
```

Verificar que `framer-motion` aparece em `dependencies` no `package.json`.

### 4b: Atualizar ChatInput com prop `variant`

- [ ] **Step 2: Atualizar `frontend/src/components/chat/ChatInput.tsx`**

Substituir o conteúdo completo:

```typescript
"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { SendHorizontal } from "lucide-react";

interface ChatInputProps {
  onSend: (message: string, equipmentFilter?: string | null) => void;
  disabled?: boolean;
  variant?: "welcome" | "bottom";
}

export function ChatInput({ onSend, disabled, variant = "bottom" }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleSubmit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed, null);
    setValue("");
    textareaRef.current?.focus();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  const containerClass =
    variant === "welcome"
      ? "space-y-2 p-4"
      : "space-y-2 border-t bg-background/80 p-4 backdrop-blur-sm";

  return (
    <div className={containerClass}>
      <div className="flex items-end gap-2">
        <Textarea
          ref={textareaRef}
          placeholder="Faça uma pergunta sobre os manuais…"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          className="max-h-32 min-h-[2.5rem] resize-none rounded-xl border-border/50 bg-card shadow-sm focus-visible:ring-primary/30"
        />
        <Button
          size="icon"
          onClick={handleSubmit}
          disabled={disabled || !value.trim()}
          className="shrink-0 rounded-xl shadow-sm"
        >
          <SendHorizontal className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
```

### 4c: Reescrever ChatWindow com welcome state

- [ ] **Step 3: Reescrever `frontend/src/components/chat/ChatWindow.tsx`**

Substituir o conteúdo completo:

```typescript
"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { askQuestion, getSessionMessages } from "@/lib/api";
import { useChatContext } from "@/lib/chat-context";
import type { Message, ChatSessionDetail } from "@/types";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { Loader2 } from "lucide-react";
import Image from "next/image";
import { useUser } from "@clerk/nextjs";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";

export function ChatWindow() {
  const { activeSessionId, setActiveSessionId } = useChatContext();
  const { user } = useUser();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingSession, setLoadingSession] = useState(false);
  const [hasStarted, setHasStarted] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const sessionIdRef = useRef<string | null>(null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  useEffect(() => {
    if (!activeSessionId) {
      setMessages([]);
      setHasStarted(false);
      sessionIdRef.current = null;
      return;
    }

    if (activeSessionId === sessionIdRef.current) return;

    setLoadingSession(true);
    getSessionMessages(activeSessionId)
      .then((data: ChatSessionDetail) => {
        sessionIdRef.current = activeSessionId;
        const mapped = data.messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          citations: m.citations ?? undefined,
        }));
        setMessages(mapped);
        setHasStarted(mapped.length > 0);
      })
      .catch(() => {
        setMessages([]);
        setHasStarted(false);
        setActiveSessionId(null);
      })
      .finally(() => setLoadingSession(false));
  }, [activeSessionId, setActiveSessionId]);

  async function handleSend(question: string, equipmentFilter?: string | null) {
    setHasStarted(true);

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: question,
    };

    const loadingMsg: Message = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      isLoading: true,
    };

    setMessages((prev) => [...prev, userMsg, loadingMsg]);
    setIsLoading(true);

    try {
      const data = await askQuestion(
        question,
        equipmentFilter,
        sessionIdRef.current,
      );

      if (!sessionIdRef.current && data.session_id) {
        sessionIdRef.current = data.session_id;
        setActiveSessionId(data.session_id);
      }

      const assistantMsg: Message = {
        id: loadingMsg.id,
        message_id: data.message_id,
        role: "assistant",
        content: data.answer,
        citations: data.citations,
      };

      setMessages((prev) =>
        prev.map((m) => (m.id === loadingMsg.id ? assistantMsg : m))
      );
    } catch (err) {
      const errorMsg: Message = {
        id: loadingMsg.id,
        role: "assistant",
        content: `Erro ao buscar resposta: ${err instanceof Error ? err.message : "Erro desconhecido"}`,
      };
      setMessages((prev) =>
        prev.map((m) => (m.id === loadingMsg.id ? errorMsg : m))
      );
    } finally {
      setIsLoading(false);
    }
  }

  const firstName = user?.firstName ?? "";
  const greeting = firstName ? `Olá, ${firstName}` : "Olá!";

  return (
    <LayoutGroup>
      {loadingSession ? (
        <div className="flex h-full items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="flex h-full flex-col bg-background">
          <AnimatePresence mode="wait">
            {!hasStarted ? (
              /* Welcome state */
              <motion.div
                key="welcome"
                className="flex flex-1 flex-col items-center justify-center gap-4 px-4 text-center"
                initial={{ opacity: 1 }}
                exit={{ opacity: 0, transition: { duration: 0.2 } }}
              >
                <div>
                  <div className="mb-2 flex flex-col items-center gap-1 sm:flex-row sm:gap-2 sm:justify-center">
                    <Image
                      src="/kyotech-icon.png"
                      alt="Kyotech"
                      width={32}
                      height={32}
                      priority
                    />
                    <span className="text-sm text-muted-foreground">{greeting}</span>
                  </div>
                  <h2 className="text-xl font-bold sm:text-2xl">
                    Por onde começamos?
                  </h2>
                </div>

                <motion.div
                  layoutId="chat-input"
                  className="w-full max-w-[600px] rounded-2xl shadow-lg"
                  style={{ zIndex: 10 }}
                  transition={{ duration: 0.4, ease: "easeInOut" }}
                >
                  <ChatInput
                    onSend={handleSend}
                    disabled={isLoading}
                    variant="welcome"
                  />
                </motion.div>
              </motion.div>
            ) : (
              /* Chat state */
              <motion.div
                key="chat"
                className="flex flex-1 flex-col overflow-hidden"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: { duration: 0.2 } }}
              >
                <div ref={scrollRef} className="flex-1 overflow-y-auto px-4">
                  <div className="mx-auto max-w-3xl space-y-5 py-6">
                    {messages.map((msg) => (
                      <MessageBubble key={msg.id} message={msg} />
                    ))}
                    <div ref={bottomRef} />
                  </div>
                </div>

                <motion.div
                  layoutId="chat-input"
                  className="mx-auto w-full max-w-3xl"
                  style={{ zIndex: 10 }}
                  transition={{ duration: 0.4, ease: "easeInOut" }}
                >
                  <ChatInput
                    onSend={handleSend}
                    disabled={isLoading}
                    variant="bottom"
                  />
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </LayoutGroup>
  );
}
```

- [ ] **Step 4: Verificar compilação TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Esperado: sem erros.

- [ ] **Step 5: Verificar visualmente**

Com o servidor rodando (`npm run dev`), verificar:
- Tela inicial mostra saudação com nome do usuário + input centralizado
- Ao enviar mensagem: input anima para o bottom, saudação faz fade out
- Ao carregar uma sessão existente da sidebar: vai direto para o chat state (sem welcome)
- Responsividade: testar em viewport mobile (< 640px) — saudação em coluna, título menor

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/chat/ChatInput.tsx frontend/src/components/chat/ChatWindow.tsx
git commit -m "feat(frontend): welcome state estilo Gemini com animação Framer Motion no chat"
```

---

## Verificação Final

- [ ] Executar todos os testes do backend:

```bash
cd backend && python -m pytest tests/ -v
```

Esperado: todos PASS.

- [ ] Verificar build de produção do frontend:

```bash
cd frontend && npm run build
```

Esperado: build sem erros.

- [ ] Commit final se necessário:

```bash
git add .
git commit -m "chore: verificação final de build UI improvements"
```
