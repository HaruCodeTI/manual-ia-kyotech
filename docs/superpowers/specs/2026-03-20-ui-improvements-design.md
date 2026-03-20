# Design Spec: UI Improvements — Favicon, Stats, Chat Visual

**Data:** 2026-03-20
**Status:** Aprovado

---

## 1. Favicon

### Problema
O favicon atual (`frontend/src/app/favicon.ico`) é o padrão do Next.js/Vercel, sem identidade da marca Kyotech.

### Solução
1. Copiar `frontend/public/kyotech-icon.png` para `frontend/src/app/icon.png`. O Next.js App Router detecta `icon.*` na pasta `app/` e usa como favicon.
2. **Deletar** `frontend/src/app/favicon.ico` — quando ambos existem, o `favicon.ico` tem prioridade sobre `icon.png` e o novo arquivo seria ignorado.

### Arquivos afetados
- `frontend/src/app/icon.png` — novo (cópia de `frontend/public/kyotech-icon.png`)
- `frontend/src/app/favicon.ico` — **deletar**

---

## 2. Stats Page

### Visão geral
O frontend faz **duas chamadas** independentes:
- `getStats()` → endpoint existente `/api/v1/upload/stats` (base de conhecimento)
- `getUsageStats()` → novo endpoint `/api/v1/upload/stats/usage` (uso & qualidade)

A remoção dos cards de **Equipamentos** e **Chunks** é **intencional**: equipamentos são uma categoria administrativa sem relevância operacional diária, e chunks são um detalhe técnico de infraestrutura sem valor para o admin. Ambos os campos continuam existindo no backend por compatibilidade.

A página `frontend/src/app/stats/page.tsx` tem o `<h1>` atualizado de "Estatísticas da Base" para **"Estatísticas"** para refletir o escopo ampliado (base de conhecimento + uso).

---

### Seção "Base de Conhecimento" (3 cards, fonte: `getStats()`)

| Card | Campo | Ícone (lucide-react) |
|------|-------|----------------------|
| Documentos | `documents` | `FileText` |
| Versões de Documentos | `versions` | `Layers` |
| Documentos sem Indexação | `docs_without_chunks` | `AlertTriangle` |

#### Backend — modificar `StatsResponse` em `backend/app/api/upload.py`
```python
class StatsResponse(BaseModel):
    equipments: int        # mantido para compatibilidade — não exibido no frontend
    documents: int
    versions: int
    chunks: int            # mantido para compatibilidade — não exibido no frontend
    docs_without_chunks: int  # novo
```

#### Backend — modificar `get_ingestion_stats()` em `backend/app/services/repository.py`

Adicionar coluna na query SQL e o campo no return dict:

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
        "docs_without_chunks": row[4],  # novo
    }
```

#### Frontend — atualizar `StatsResponse` em `frontend/src/types/index.ts`
```typescript
export interface StatsResponse {
  equipments: number;
  documents: number;
  versions: number;
  chunks: number;
  docs_without_chunks: number; // novo
}
```

---

### Seção "Uso & Qualidade" (5 cards, fonte: `getUsageStats()`)

| Card | Campo | Ícone (lucide-react) | Obs |
|------|-------|----------------------|-----|
| Total de Conversas | `total_sessions` | `MessageSquare` | |
| Total de Mensagens | `total_messages` | `MessagesSquare` | |
| Feedbacks Positivos | `thumbs_up` | `ThumbsUp` | |
| Feedbacks Negativos | `thumbs_down` | `ThumbsDown` | |
| Taxa de Satisfação | calculado | `TrendingUp` | `thumbs_up / (thumbs_up + thumbs_down) * 100`; exibir `"—"` se total = 0 |

#### Backend — adicionar `UsageStatsResponse` em `backend/app/api/upload.py`
(mesmo arquivo onde `StatsResponse` está definido)
```python
class UsageStatsResponse(BaseModel):
    total_sessions: int
    total_messages: int
    thumbs_up: int
    thumbs_down: int
```

#### Backend — adicionar endpoint em `backend/app/api/upload.py`
```python
@router.get("/stats/usage", response_model=UsageStatsResponse)
async def get_usage_stats(
    _user: CurrentUser = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    stats = await repository.get_usage_stats(db)
    return UsageStatsResponse(**stats)
```

#### Backend — adicionar `get_usage_stats()` em `backend/app/services/repository.py`
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

#### Frontend — adicionar `UsageStatsResponse` em `frontend/src/types/index.ts`
```typescript
export interface UsageStatsResponse {
  total_sessions: number;
  total_messages: number;
  thumbs_up: number;
  thumbs_down: number;
}
```

#### Frontend — atualizar `frontend/src/lib/api.ts`

Atualizar a linha de import no topo do arquivo (já existente):
```typescript
import type { ChatResponse, UploadResponse, StatsResponse, UsageStatsResponse, ChatSession, FeedbackRating } from "@/types";
```

Adicionar função (variável correta é `API_BASE`, não `API_URL`):
```typescript
export async function getUsageStats(): Promise<UsageStatsResponse> {
  const res = await fetch(`${API_BASE}/api/v1/upload/stats/usage`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error("Erro ao carregar estatísticas de uso");
  return res.json();
}
```

---

### Layout Responsivo (Stats)

Grids:
- **"Base de Conhecimento"** (3 cards): `grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`
- **"Uso & Qualidade"** (5 cards): `grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3` — no desktop gera linha de 3 + linha de 2, alinhado à esquerda (padrão do grid)

O componente `frontend/src/components/dashboard/StatsCards.tsx` é **reescrito em seu lugar** (não criar novo arquivo). O componente reescrito contém ambas as seções, cada uma com:
- `<h2 className="text-lg font-semibold mb-3">` com título
- `<Separator className="mb-4" />` (componente shadcn)
- Estado de loading individual: spinner por seção
- Estado de erro individual: mensagem de erro por seção
- `<div className="mb-8">` separando as seções

---

### `getUsageStats` — padrão correto para `frontend/src/lib/api.ts`

Seguir o mesmo padrão de `getStats()` com `fetchWithTimeout` e `handleFetchError`:

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

---

### Arquivos afetados (Stats)
| Arquivo | Mudança |
|---------|---------|
| `backend/app/services/repository.py` | Atualizar `get_ingestion_stats()` + nova `get_usage_stats()` |
| `backend/app/api/upload.py` | Atualizar `StatsResponse` + `UsageStatsResponse` + endpoint `/stats/usage` |
| `frontend/src/types/index.ts` | Atualizar `StatsResponse` + adicionar `UsageStatsResponse` |
| `frontend/src/lib/api.ts` | Atualizar import + adicionar `getUsageStats()` (padrão `fetchWithTimeout`) |
| `frontend/src/components/dashboard/StatsCards.tsx` | Reescrever em lugar com duas seções |
| `frontend/src/app/stats/page.tsx` | Atualizar `<h1>` para "Estatísticas" |

---

## 3. Clerk — Migração para Production (Referência)


> **Informacional apenas — sem implementação de código.**

### Passos
1. Criar conta em clerk.com e criar uma aplicação de produção
2. Copiar `pk_live_...` (publishable key) e `sk_live_...` (secret key)
3. No Clerk Dashboard: **Sessions → Customize session token → Edit** — adicionar:
   ```json
   { "metadata": "{{user.public_metadata}}" }
   ```
4. Setar variáveis de ambiente no servidor de produção:
   ```
   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...
   CLERK_SECRET_KEY=sk_live_...
   CLERK_JWKS_URL=https://<seu-clerk-domain>/.well-known/jwks.json
   ENVIRONMENT=production
   ```
5. Recriar usuários admin no novo Clerk (não migram do keyless mode)
6. Para cada admin: setar `{ "role": "Admin" }` em **Public Metadata** no Clerk Dashboard

### Risco de segurança
`backend/app/core/auth.py` linhas 51–57: quando `CLERK_JWKS_URL` não está configurado **e** `ENVIRONMENT=development`, o backend bypassa toda autenticação e retorna Admin. **Nunca usar `ENVIRONMENT=development` em servidor público.**

---

## 4. Chat Visual — Gemini-style Welcome State

### Dependência
Instalar antes de editar código-fonte:
```bash
npm install framer-motion@^11
```
(`framer-motion@^11` é obrigatório para compatibilidade com React 19.)

### `LayoutGroup` — estrutura do `ChatWindow`

O `<LayoutGroup>` deve envolver **todo o retorno do componente**, incluindo o estado de loading de sessão (`loadingSession`), para que o contexto do Framer Motion esteja sempre montado:

```tsx
return (
  <LayoutGroup>
    {loadingSession ? (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    ) : (
      <div className="flex h-full flex-col bg-background">
        {/* conteúdo principal com AnimatePresence e motion.div */}
      </div>
    )}
  </LayoutGroup>
);
```

---

### Estado 1 — Welcome (sem mensagens, `hasStarted === false`)

```
[flex-1 spacer]

  [flex flex-col gap-1 sm:flex-row sm:gap-2 items-center]
    <img src="/kyotech-icon.png" width=32 height=32 />
    "Olá, Arthur"    ← text-sm text-muted-foreground

  "Por onde começamos?"   ← text-xl sm:text-2xl font-bold mt-2

[motion.div layoutId="chat-input"]
  <ChatInput variant="welcome" onSend={handleSend} disabled={isLoading} />

[pb-8 spacer]
```

- Container central: `flex flex-col items-center justify-center gap-4 flex-1 text-center px-4`
- Nome via `useUser()` de `@clerk/nextjs` → `user?.firstName`; se ausente: exibir "Olá!" sem nome
- Input centralizado: `w-full max-w-[600px] mx-auto`

---

### Estado 2 — Com mensagens (`hasStarted === true`)

- Área de scroll com mensagens (como hoje)
- `motion.div layoutId="chat-input"` posicionado no bottom
- `<ChatInput variant="bottom" onSend={handleSend} disabled={isLoading} />`

---

### Estado `hasStarted` em `ChatWindow`

```typescript
const [hasStarted, setHasStarted] = useState(false);
```

- Inicializado como `false`
- Muda para `true` **imediatamente quando `handleSend` é chamado** (antes da resposta da API) — isso garante que a animação dispara assim que o usuário envia a mensagem
- Também muda para `true` **quando uma sessão existente é carregada** via `getSessionMessages` (na resolução do `useEffect` que carrega o histórico): `setHasStarted(data.messages.length > 0)`

---

### Sequência de Animação

Ordem importa para evitar sobreposição visual:

1. Usuário envia → `hasStarted = true`
2. Welcome content (saudação + título) faz fade out: `opacity: 0`, duration 200ms
3. Após 200ms: welcome content é desmontado via `AnimatePresence mode="wait"`
4. Input "voa" do centro para o bottom via `layoutId="chat-input"`: duration 400ms, easing `easeInOut`
5. Mensagens aparecem com fade in individual

**Notas críticas de implementação:**
- `<LayoutGroup>` do `framer-motion` deve envolver o `ChatWindow` (ou ser o elemento raiz dentro do componente) para que `layoutId` funcione entre renders condicionais
- O `motion.div layoutId="chat-input"` deve existir **em ambas as branches** do condicional (welcome E bottom), com o mesmo `layoutId`
- O `motion.div` recebe `style={{ zIndex: 10 }}` para voar sobre conteúdo sendo desmontado

---

### Prop `variant` em `ChatInput`

Interface atualizada:
```typescript
interface ChatInputProps {
  onSend: (message: string, equipmentFilter?: string | null) => void;
  disabled?: boolean;
  variant?: "welcome" | "bottom"; // padrão: "bottom"
}
```

Classes completas do **div externo** (atualmente `<div className="space-y-2 border-t bg-background/80 p-4 backdrop-blur-sm">`) por variant:

- `variant="bottom"` (padrão atual): `space-y-2 border-t bg-background/80 p-4 backdrop-blur-sm`
- `variant="welcome"`: `space-y-2 p-4` (remove `border-t`, remove `bg-background/80 backdrop-blur-sm`; o shadow e rounded são aplicados pelo `motion.div` wrapper em `ChatWindow`, não aqui)

O `motion.div layoutId="chat-input"` é adicionado em `ChatWindow` **envolvendo** o `<ChatInput>`, não dentro do `ChatInput`. O `motion.div` recebe as classes `shadow-lg rounded-2xl` apenas no welcome state (via `className` condicional ou `animate` prop).

---

### Responsividade (Chat)

| Elemento | Mobile | Desktop |
|---------|--------|---------|
| Título | `text-xl` | `sm:text-2xl` |
| Greeting + logo | `flex-col gap-1` | `sm:flex-row sm:gap-2` |
| Input centralizado | `w-full px-4` | `max-w-[600px] mx-auto` |
| Animação | igual | igual |

Classe completa para o container da saudação:
```
flex flex-col gap-1 sm:flex-row sm:gap-2 items-center justify-center
```

---

### Arquivos afetados (Chat)
| Arquivo | Mudança |
|---------|---------|
| `frontend/package.json` | Adicionar `"framer-motion": "^11"` (após `npm install`) |
| `frontend/src/components/chat/ChatWindow.tsx` | Estado `hasStarted`, `LayoutGroup`, `AnimatePresence`, welcome state, `motion.div layoutId` em ambas branches, `useUser` de `@clerk/nextjs` |
| `frontend/src/components/chat/ChatInput.tsx` | Nova prop `variant`, estilos condicionais |

---

## Resumo de Prioridade de Implementação

| # | Item | Complexidade |
|---|------|-------------|
| 1 | Favicon | Baixa |
| 2 | Stats — backend | Média |
| 3 | Stats — frontend | Média |
| 4 | Chat visual | Alta |
