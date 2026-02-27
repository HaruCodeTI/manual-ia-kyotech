# Kyotech AI — Guia de Deploy: Homologação (Staging)

**HaruCode | Deploy do Monorepo na Azure**
**Data:** 27/02/2026 | **Fase:** 1.5 — Deploy para Homologação

---

## Visão Geral

Este documento detalha o deploy completo do monorepo Kyotech AI na Azure usando **Azure Container Apps**. O objetivo é ter um ambiente de homologação acessível para a equipe HaruCode + Kyotech validarem o sistema antes de carregar documentos confidenciais.

### Arquitetura de Deploy

```
Internet (HTTPS)
       │
       ▼
┌─────────────────────────────────────────────────┐
│       Container Apps Environment                │
│       (vnet-kyotech / snet-app)                 │
│                                                 │
│  ┌──────────────┐      ┌──────────────────┐     │
│  │   frontend   │ ───→ │     backend      │     │
│  │   Next.js    │      │     FastAPI      │     │
│  │   porta 3000 │      │     porta 8000   │     │
│  │              │      │                  │     │
│  │  Ingress:    │      │  Ingress:        │     │
│  │  EXTERNO     │      │  INTERNO         │     │
│  └──────────────┘      └────────┬─────────┘     │
│                                 │               │
└─────────────────────────────────┼───────────────┘
                                  │
                    ┌─────────────┼──────────────┐
                    │             │              │
                    ▼             ▼              ▼
              PostgreSQL    Azure OpenAI    Blob Storage
              (VNet Int.)   (Private EP)   (Private EP)
              snet-postgres  snet-endpoints  snet-endpoints
```

### Decisões de Segurança para Homologação

| Aspecto | Homologação (agora) | Produção (futuro) |
|---|---|---|
| Ingress do frontend | Externo (HTTPS) | Interno (VPN/Front Door) |
| Ingress do backend | Interno (só frontend alcança) | Interno |
| PostgreSQL | Acesso público temporário + VNet | Somente VNet |
| OpenAI / Blob | Acesso público temporário | Somente Private Endpoint |
| Autenticação | Clerk dev mode | Clerk produção ou Entra ID |
| Dados nos PDFs | Documentos de teste (não-confidenciais) | Manuais Fujifilm reais |

---

## Pré-requisitos

Antes de iniciar, confirme que você tem:

- [x] Conta Azure com créditos (~$910 restantes)
- [x] Resource Group `rg-kyotech-ai` em Canada Central
- [x] VNet `vnet-kyotech` com subnets configuradas
- [x] PostgreSQL `psql-kyotech` com schema + migration 002 aplicada
- [x] Azure OpenAI `aoai-kyotech` com deployments (gpt-4o, gpt-4o-mini, embedding-small)
- [x] Storage Account `stkyotechai` com containers
- [x] Monorepo funcional localmente (backend + frontend)
- [ ] Azure CLI instalada no Mac (`brew install azure-cli`)
- [ ] Docker Desktop instalado e rodando

---

## Passo 1 — Instalar Ferramentas Locais

### 1.1 Azure CLI

```bash
brew install azure-cli
az login
az account set --subscription "Azure subscription 1"
```

Confirme que está na subscription correta:

```bash
az account show --query "{name:name, id:id}" -o table
```

### 1.2 Docker Desktop

1. Baixe em https://www.docker.com/products/docker-desktop/
2. Instale e inicie
3. Confirme que funciona:

```bash
docker --version
docker ps
```

---

## Passo 2 — Criar o Azure Container Registry (ACR)

O ACR é o repositório privado onde ficam as imagens Docker do backend e frontend.

```bash
az acr create \
  --resource-group rg-kyotech-ai \
  --name acrkyotech \
  --sku Basic \
  --location canadacentral
```

**Custo:** ~$5/mês (Basic tier, 10 GB storage incluído).

Habilite o login admin (necessário para o Container Apps puxar as imagens):

```bash
az acr update --name acrkyotech --admin-enabled true
```

Anote as credenciais (vai precisar depois):

```bash
az acr credential show --name acrkyotech --query "{username:username, password:passwords[0].value}" -o table
```

---

## Passo 3 — Criar os Dockerfiles

### 3.1 Backend — `backend/Dockerfile`

```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Dependências do sistema para PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3.2 Frontend — `frontend/Dockerfile`

```dockerfile
FROM node:18-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Variáveis de build (Next.js precisa na build time)
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

RUN npm run build

# --- Stage 2: Runtime ---
FROM node:18-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

CMD ["node", "server.js"]
```

### 3.3 Frontend — atualizar `next.config.ts`

O Dockerfile acima usa o modo `standalone` do Next.js. Adicione ao `next.config.ts`:

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
```

### 3.4 Frontend — `.dockerignore`

Criar `frontend/.dockerignore`:

```
node_modules
.next
.git
```

### 3.5 Backend — `.dockerignore`

Criar `backend/.dockerignore`:

```
.venv
__pycache__
.env
*.zip
tests
```

---

## Passo 4 — Build e Push das Imagens

### 4.1 Login no ACR

```bash
az acr login --name acrkyotech
```

### 4.2 Build e push do Backend

```bash
cd ~/HaruCode/apps/kyotech-ai/backend

docker build --platform linux/amd64 -t acrkyotech.azurecr.io/kyotech-backend:v1 .

docker push acrkyotech.azurecr.io/kyotech-backend:v1
```

> **Nota:** O `--platform linux/amd64` é obrigatório porque o Mac M1/M2 compila para ARM por padrão, mas o Container Apps roda em x64.

### 4.3 Build e push do Frontend

Para o frontend, você precisa passar as variáveis de build:

```bash
cd ~/HaruCode/apps/kyotech-ai/frontend

docker build --platform linux/amd64 \
  --build-arg NEXT_PUBLIC_API_URL=https://kyotech-backend.internal.AMBIENTE.canadacentral.azurecontainerapps.io \
  --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_SEU_KEY_AQUI \
  -t acrkyotech.azurecr.io/kyotech-frontend:v1 .

docker push acrkyotech.azurecr.io/kyotech-frontend:v1
```

> **Atenção:** A URL do backend será conhecida após o Passo 5. Na primeira vez, faça o build do backend primeiro, pegue a URL interna, e então faça o build do frontend. Veja o Passo 6 para a URL correta.

---

## Passo 5 — Criar o Container Apps Environment

O Container Apps Environment é o "cluster" que hospeda os containers, conectado à VNet.

### 5.1 Registrar o provider (primeira vez)

```bash
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
```

### 5.2 Criar o Environment

```bash
az network vnet subnet update \
  --resource-group rg-kyotech-ai \
  --vnet-name vnet-kyotech \
  --name snet-app \
  --delegations Microsoft.App/environments
```

```bash
az containerapp env create \
  --name cae-kyotech \
  --resource-group rg-kyotech-ai \
  --location canadacentral \
  --infrastructure-subnet-resource-id "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/rg-kyotech-ai/providers/Microsoft.Network/virtualNetworks/vnet-kyotech/subnets/snet-app"
```

> **Importante:** Isso conecta o Container Apps Environment à subnet `snet-app` (10.0.1.0/24) da VNet que já temos. Os containers dentro desse environment poderão alcançar o PostgreSQL, OpenAI e Blob via Private Endpoints.

Aguarde 2-3 minutos para provisionamento.

### 5.3 Verificar

```bash
az containerapp env show \
  --name cae-kyotech \
  --resource-group rg-kyotech-ai \
  --query "{name:name, provisioningState:provisioningState, vnetSubnetId:vnetConfiguration.infrastructureSubnetId}" \
  -o table
```

---

## Passo 6 — Deploy do Backend (Container App)

### 6.1 Criar o Container App do Backend

```bash
az containerapp create \
  --name kyotech-backend \
  --resource-group rg-kyotech-ai \
  --environment cae-kyotech \
  --image acrkyotech.azurecr.io/kyotech-backend:v1 \
  --registry-server acrkyotech.azurecr.io \
  --registry-username acrkyotech \
  --registry-password "$(az acr credential show --name acrkyotech --query passwords[0].value -o tsv)" \
  --target-port 8000 \
  --ingress internal \
  --min-replicas 0 \
  --max-replicas 2 \
  --cpu 0.5 \
  --memory 1.0Gi \
  --env-vars \
    DATABASE_URL="postgresql+asyncpg://SEU_ADMIN:SUA_SENHA@psql-kyotech.postgres.database.azure.com:5432/kyotech_db?ssl=require" \
    AZURE_OPENAI_ENDPOINT="https://aoai-kyotech.openai.azure.com/" \
    AZURE_OPENAI_API_KEY="SUA_CHAVE" \
    AZURE_OPENAI_API_VERSION="2024-10-21" \
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT="embedding-small" \
    AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-4o" \
    AZURE_OPENAI_MINI_DEPLOYMENT="gpt-4o-mini" \
    AZURE_STORAGE_CONNECTION_STRING="SUA_CONNECTION_STRING" \
    AZURE_STORAGE_CONTAINER_ORIGINALS="pdfs-originais" \
    CLERK_JWKS_URL=""
```

**Pontos importantes:**

- `--ingress internal`: o backend NÃO fica exposto na internet, apenas acessível dentro do Container Apps Environment.
- `--min-replicas 0`: scale to zero quando não há tráfego (economia).
- `--max-replicas 2`: escala até 2 instâncias sob carga.
- `CLERK_JWKS_URL=""`: vazio = modo dev, sem autenticação no backend.

### 6.2 Obter a URL interna do Backend

```bash
az containerapp show \
  --name kyotech-backend \
  --resource-group rg-kyotech-ai \
  --query "properties.configuration.ingress.fqdn" -o tsv
```

A URL será algo como:

```
kyotech-backend.internal.delightfulfield-XXXXX.canadacentral.azurecontainerapps.io
```

**Anote essa URL** — será usada no build do frontend.

### 6.3 Testar o Backend (via CLI)

Como o ingress é interno, não dá para acessar pelo browser. Teste via exec:

```bash
az containerapp exec \
  --name kyotech-backend \
  --resource-group rg-kyotech-ai \
  --command "curl -s http://localhost:8000/health"
```

Deve retornar: `{"status":"ok","service":"kyotech-ai"}`

---

## Passo 7 — Deploy do Frontend (Container App)

### 7.1 Rebuild do Frontend com URL correta

Agora que você tem a URL interna do backend, refaça o build:

```bash
cd ~/HaruCode/apps/kyotech-ai/frontend

docker build --platform linux/amd64 \
  --build-arg NEXT_PUBLIC_API_URL=https://kyotech-backend.internal.XXXXXXX.canadacentral.azurecontainerapps.io \
  --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_SEU_KEY \
  -t acrkyotech.azurecr.io/kyotech-frontend:v1 .

docker push acrkyotech.azurecr.io/kyotech-frontend:v1
```

### 7.2 Criar o Container App do Frontend

```bash
az containerapp create \
  --name kyotech-frontend \
  --resource-group rg-kyotech-ai \
  --environment cae-kyotech \
  --image acrkyotech.azurecr.io/kyotech-frontend:v1 \
  --registry-server acrkyotech.azurecr.io \
  --registry-username acrkyotech \
  --registry-password "$(az acr credential show --name acrkyotech --query passwords[0].value -o tsv)" \
  --target-port 3000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 2 \
  --cpu 0.5 \
  --memory 1.0Gi
```

**Diferença:** `--ingress external` — o frontend é acessível pela internet via HTTPS.

### 7.3 Obter a URL pública do Frontend

```bash
az containerapp show \
  --name kyotech-frontend \
  --resource-group rg-kyotech-ai \
  --query "properties.configuration.ingress.fqdn" -o tsv
```

A URL será algo como:

```
kyotech-frontend.delightfulfield-XXXXX.canadacentral.azurecontainerapps.io
```

Abra no browser — você deve ver a interface do Kyotech AI.

---

## Validação Pós-Deploy

### Checklist de Validação

| Teste | Como verificar | Esperado |
|---|---|---|
| Frontend carrega | Abrir URL pública no browser | Tela de login ou chat |
| Health check | Via exec no backend container | `{"status":"ok"}` |
| Upload de PDF | Tela de Upload → subir PDF teste | Sucesso com contagem de chunks |
| Chat funciona | Perguntar sobre o PDF enviado | Resposta com citações |
| Citação abre PDF | Clicar em [Fonte N] → Ver PDF | PDF abre na página correta |
| Stats | Tela de Estatísticas | Cards com números corretos |

### Verificar logs

```bash
# Logs do backend
az containerapp logs show \
  --name kyotech-backend \
  --resource-group rg-kyotech-ai \
  --follow

# Logs do frontend
az containerapp logs show \
  --name kyotech-frontend \
  --resource-group rg-kyotech-ai \
  --follow
```

---

## Custos do Deploy (Homologação)

| Recurso | Custo/mês (USD) |
|---|---|
| Container Apps (2 containers, uso leve, scale to zero) | ~$5–10 |
| Azure Container Registry (Basic) | ~$5 |
| PostgreSQL B2s (já existente) | ~$58 |
| Private Endpoints x2 (já existente) | ~$15 |
| Azure OpenAI (uso leve) | ~$5–15 |
| Blob Storage (< 1 GB) | ~$0.10 |
| **Total estimado** | **~$88–103** |
| **Incremento vs. antes do deploy** | **~$10–15** |

---

## CI/CD com GitHub Actions (Opcional, Fase 2)

Após validar o deploy manual, pode-se automatizar com GitHub Actions:

```
git push → GitHub Actions → Build Docker → Push ACR → Deploy Container Apps
```

A configuração será detalhada na Fase 2. Para homologação, o deploy manual via CLI é suficiente e mais controlado.

---

## Troubleshooting

### Container não inicia / CrashLoopBackOff

```bash
az containerapp logs show --name kyotech-backend --resource-group rg-kyotech-ai --type system
```

Causas comuns:
- Variável de ambiente faltando (DATABASE_URL, AZURE_OPENAI_API_KEY)
- Senha com caracteres especiais não escapados na DATABASE_URL
- Porta errada no `--target-port`

### Frontend não consegue chamar o Backend

Verifique se a `NEXT_PUBLIC_API_URL` usada no build está correta. No Next.js, variáveis `NEXT_PUBLIC_*` são injetadas **em build time**, não runtime. Se a URL mudar, precisa rebuild.

### Timeout na conexão com PostgreSQL

O Container Apps Environment precisa resolver o DNS privado do PostgreSQL. Verifique se a Private DNS Zone `psql-kyotech.private.postgres.database.azure.com` está linkada à VNet.

### Upload demora muito

Documentos grandes (>5MB) podem levar minutos. O timeout padrão do Container Apps para requests HTTP é 240 segundos. Se precisar mais:

```bash
az containerapp ingress update \
  --name kyotech-backend \
  --resource-group rg-kyotech-ai \
  --transport http \
  --target-port 8000
```

---

*HaruCode © 2026 — Documento de uso interno*
*Última atualização: 27/02/2026*