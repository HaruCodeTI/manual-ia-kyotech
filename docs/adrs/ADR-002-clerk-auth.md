# ADR-002 — Migração de Autenticação: Microsoft Entra ID → Clerk

| Campo        | Valor                                       |
|--------------|---------------------------------------------|
| **Data**     | 2026-03-05                                  |
| **Status**   | Aceita                                      |
| **Autor**    | HaruCode (Equipe Kyotech AI)                |
| **Jira**     | IA-82                                       |
| **Relação**  | Substituição parcial da Seção 3 do MVP Doc  |

---

## 1. Contexto

O documento de consolidação técnica "Infraestrutura de IA — Kyotoec MVP" (Seção 3 — Arquitetura Técnica) especificava **Microsoft Entra ID** (antigo Azure AD) com a biblioteca **MSAL** como mecanismo de autenticação corporativa. A arquitetura original previa:

- Login via Microsoft Entra ID no frontend React/Next.js
- Validação de tokens MSAL no backend FastAPI
- Integração direta com o ecossistema Azure (VNet, Private Endpoints)
- Roles via grupos do Entra ID (Admin / Technician)

Durante o desenvolvimento do MVP (Fase 0 → Fase 1), a equipe identificou que a implementação com Entra ID + MSAL adicionava complexidade significativa ao prazo apertado do MVP, especialmente considerando:

- Configuração de App Registration no Azure AD com redirect URIs, scopes e permissões delegadas
- Fluxo PKCE + refresh tokens no frontend Next.js 16 (incompatibilidades com MSAL.js v2 e React 19)
- Necessidade de configuração de claims customizados via Token Configuration para RBAC
- Overhead de integração em ambiente de desenvolvimento (tenant, consent admin, etc.)

---

## 2. Decisão

**Adotar Clerk como provedor de autenticação para o MVP**, substituindo Microsoft Entra ID + MSAL.

### Stack implementada

| Camada     | Tecnologia                         | Versão  |
|------------|------------------------------------|---------|
| Frontend   | `@clerk/nextjs`                    | 6.38.3  |
| Frontend   | `@clerk/localizations` (pt-BR)     | 3.37.1  |
| Backend    | `PyJWT` + `PyJWKClient` (JWKS)     | —       |
| Runtime    | Next.js 16 + React 19              | —       |

### Implementação atual

**Frontend:**
- `ClerkProvider` com localização `ptBR` envolve toda a aplicação
- Componentes pré-construídos `<SignIn />` e `<UserButton />` para login e gestão de sessão
- Proteção de rotas via `clerkMiddleware()` (Next.js middleware)
- Bearer token enviado automaticamente via `getToken()` do Clerk para chamadas ao backend

**Backend (`backend/app/core/auth.py`):**
- Validação de JWT via JWKS endpoint público do Clerk (`/.well-known/jwks.json`)
- Decodificação com algoritmo RS256 via `PyJWKClient`
- Extração de role via `user.public_metadata.role` (claim customizado `metadata`)
- Roles suportados: `Admin` e `Technician` (default)
- Dependency injection via `get_current_user()` e `require_role()` no FastAPI

**RBAC:**
- Configuração no Clerk Dashboard: Sessions → Customize session token → `{ "metadata": "{{user.public_metadata}}" }`
- Admin atribui roles via Clerk Dashboard → Users → Public Metadata: `{ "role": "Admin" }`
- Backend aplica regra: se `metadata.role != "Admin"` → `Technician`

---

## 3. Alternativas Consideradas

### 3a. Microsoft Entra ID + MSAL (Original)

| Aspecto               | Avaliação                                                   |
|-----------------------|-------------------------------------------------------------|
| Integração Azure      | Nativa — mesma VNet, Private Endpoints, consent corporativo |
| Custo incremental     | Zero (incluído na licença Microsoft 365)                    |
| Compatibilidade       | MSAL.js v2 com incompatibilidades conhecidas no React 19    |
| Tempo de setup        | Alto — App Registration, consent, token config, redirect URIs|
| RBAC                  | Via grupos do Entra ID (mais enterprise-ready)              |
| Localização           | Customização manual necessária                              |

### 3b. Clerk (Escolhida)

| Aspecto               | Avaliação                                                  |
|-----------------------|------------------------------------------------------------|
| Integração Azure      | Nenhuma — serviço SaaS externo                             |
| Custo incremental     | Plano gratuito até 10.000 MAU; Pro a partir de $25/mês     |
| Compatibilidade       | Integração nativa Next.js 16 + React 19 (SDK oficial)      |
| Tempo de setup        | Baixo — ~2h para auth completo com RBAC                    |
| RBAC                  | Via Public Metadata (funcional, mas menos enterprise)       |
| Localização           | pt-BR nativo via `@clerk/localizations`                    |

### 3c. NextAuth.js / Auth.js

| Aspecto               | Avaliação                                                  |
|-----------------------|------------------------------------------------------------|
| Integração Azure      | Possível via provider Entra ID                             |
| Custo incremental     | Zero (open source)                                         |
| Compatibilidade       | Suporte a Next.js 16 em fase de estabilização              |
| Tempo de setup        | Médio — configuração manual de providers e callbacks       |
| RBAC                  | Manual (via session callbacks + banco de dados)            |
| Localização           | Manual                                                     |

---

## 4. Consequências

### Positivas

- **Velocidade de entrega:** Auth completo implementado em ~2 horas vs estimativa de ~2-3 dias com Entra ID
- **Componentes prontos:** `<SignIn />`, `<UserButton />`, session management sem código custom
- **Localização nativa:** Interface de login 100% em português sem esforço adicional
- **DX (Developer Experience):** Hot reload do JWT, dashboard visual para gerenciar usuários, logs de autenticação integrados
- **Compatibilidade garantida:** SDK oficial testado com Next.js 16 e React 19

### Negativas

- **Dependência externa:** Clerk é um serviço SaaS — introduz ponto de falha fora da infraestrutura Azure
- **Tráfego externo:** JWKS validation requer que o backend alcance `clerk.com` — fura parcialmente o isolamento de rede (Seção 8 do MVP Doc)
- **Custo recorrente:** Potencial custo de $25+/mês no plano Pro se exceder free tier
- **Maturidade corporativa:** Menos adequado para compliance corporativo rigoroso vs Entra ID integrado ao Microsoft 365
- **Migração futura necessária:** Se a Kyotoec exigir SSO corporativo via Microsoft, será necessário migrar

### Riscos Mitigados

| Risco                                  | Mitigação                                                    |
|----------------------------------------|--------------------------------------------------------------|
| Clerk fora do ar                       | JWT tem TTL de 60s; cache de JWKS no PyJWKClient             |
| Migração futura para Entra ID          | Interface `CurrentUser` e `get_current_user()` abstraem o provider — troca requer apenas alterar `auth.py` e middleware |
| Exposição de rede (JWKS externo)       | JWKS endpoint é somente leitura e público; não expõe dados sensíveis |
| Custo escalar                          | MVP terá <50 usuários; free tier de 10.000 MAU é suficiente  |

---

## 5. Critérios para Migração Futura (Entra ID)

A migração para Microsoft Entra ID deverá ser avaliada quando **qualquer** das condições abaixo for atendida:

1. **Requisito corporativo formal** da Kyotoec/Fujifilm exigindo SSO via Microsoft 365
2. **Compliance** — auditoria exigindo que toda autenticação passe por infraestrutura Azure isolada
3. **Escala** — número de usuários excedendo o free tier do Clerk de forma que o custo não justifique
4. **Hardening de rede** (IA-81) — se o requisito de zero tráfego externo for estrito, o JWKS do Clerk será incompatível

### Esforço estimado de migração

- Frontend: substituir `@clerk/nextjs` por `msal-react` (~1-2 dias)
- Backend: alterar `auth.py` para validar tokens MSAL em vez de Clerk JWKS (~0.5 dia)
- Infra: criar App Registration no Azure AD, configurar redirect URIs, token claims (~0.5 dia)
- Testes: validar fluxo completo em staging (~0.5 dia)
- **Total estimado: 2-4 dias**

---

## 6. Referências

- Documento técnico: "Infraestrutura de IA — Kyotoec MVP", Seção 3 (Arquitetura Técnica)
- Clerk Docs: https://clerk.com/docs/quickstarts/nextjs
- Implementação: `backend/app/core/auth.py`, `frontend/src/app/layout.tsx`
- Card Jira: IA-82 (este ADR), IA-73 (setup de autenticação original)
