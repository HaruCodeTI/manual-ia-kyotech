# Kyotech IA — Guia Passo a Passo: Primeiros Passos na Azure

**HaruCode | Fase 0 — Setup Inicial**
**Data:** 25/02/2026 | **Nível:** Iniciante

---

## Antes de Começar

Você acabou de criar sua conta Azure e tem **USD 1.000 em créditos**. Este guia vai te levar do zero até ter a infraestrutura base pronta para o desenvolvimento do MVP. Cada passo inclui o link direto da documentação oficial da Microsoft.

**Tempo estimado total:** 2–3 dias úteis (excluindo aprovação do OpenAI).

---

## PASSO 1 — Criar o Resource Group

**O que é:** Um Resource Group é uma "pasta" que agrupa todos os recursos Azure do projeto. Tudo que criarmos (banco de dados, rede, storage) vai morar dentro dele.

**Como fazer:**

1. Acesse [portal.azure.com](https://portal.azure.com) e faça login.
2. Na barra de busca no topo, digite **"Resource groups"** e clique no resultado.
3. Clique em **"+ Create"** (botão azul no topo).
4. Preencha:
   - **Subscription:** selecione a sua (a que tem os créditos).
   - **Resource group:** digite `rg-kyotech-ai`
   - **Region:** selecione **East US 2** (tem boa disponibilidade de Azure OpenAI e preço competitivo).
5. Clique em **"Review + create"** e depois **"Create"**.

**Pronto!** Em 5 segundos o Resource Group está criado.

> 📖 **Doc oficial:** [Gerenciar Resource Groups pelo portal](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/manage-resource-groups-portal)

---

## PASSO 2 — Configurar Budget Alert (URGENTE)

**Por que fazer isso agora:** Os USD 1.000 são limitados. Se algo der errado (recurso provisionado errado, teste descontrolado), você quer ser avisado antes de queimar tudo. Faça isso ANTES de criar qualquer recurso pago.

**Como fazer:**

1. Na barra de busca, digite **"Cost Management + Billing"** e entre.
2. No menu lateral, clique em **"Cost Management"** → **"Budgets"**.
3. Clique em **"+ Add"** para criar um novo budget.
4. Preencha:
   - **Name:** `budget-kyotech-1000`
   - **Reset period:** Monthly
   - **Amount:** `150` (esse é o valor mensal que esperamos gastar — se ultrapassar, algo está errado)
5. Na aba **"Alert conditions"**, crie três alertas:
   - **Alerta 1:** Type = Actual, 50% do budget (USD 75) → seu e-mail.
   - **Alerta 2:** Type = Actual, 80% do budget (USD 120) → seu e-mail.
   - **Alerta 3:** Type = Forecasted, 100% do budget (USD 150) → seu e-mail. Este avisa se a Azure *prevê* que você vai estourar.
6. Na aba **"Recipients"**, adicione o e-mail de quem deve receber os alertas.
7. Clique em **"Create"**.

**Importante:** Crie também um segundo budget chamado `budget-creditos-total` com Amount de `900` (guardando margem dos USD 1.000) no período **Annually**, com alertas em 25%, 50% e 75%.

> 📖 **Doc oficial:** [Tutorial: Criar e gerenciar budgets](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets)
>
> 📖 **Doc oficial:** [Monitorar uso com alertas de custo](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/cost-mgt-alerts-monitor-usage-spending)

---

## PASSO 3 — Solicitar Acesso ao Azure OpenAI

**Por que fazer isso agora:** Esta é a etapa que pode **travar o projeto**. A aprovação pode levar de 1 a 10 dias úteis. Enquanto espera, você continua configurando a rede e o banco.

**Situação atual (2025+):** Para modelos gerais como GPT-4o e GPT-4o-mini, a Microsoft **não exige mais formulário** para contas Pay-as-you-go. Você pode criar o recurso diretamente no portal. Porém, se sua conta for Free Trial ou Student, pode haver restrições.

**Como verificar e criar:**

1. Na barra de busca, digite **"Azure OpenAI"** e clique no resultado.
2. Clique em **"+ Create"**.
3. Se aparecer um formulário de solicitação de acesso, preencha usando o e-mail corporativo (não use @gmail.com — aplicações com e-mail pessoal são frequentemente rejeitadas).
4. Se o portal permitir criar diretamente, preencha:
   - **Subscription:** a sua.
   - **Resource group:** `rg-kyotech-ai`
   - **Region:** **East US 2** (mesma região do Resource Group).
   - **Name:** `aoai-kyotech`
   - **Pricing tier:** Standard S0
5. **NÃO** clique em Create ainda — apenas valide se o portal permite. Se permitir, aguarde: vamos criar isso no Passo 7, após a rede estar pronta.

**Se pedir formulário:** Preencha e envie imediatamente. Descreva o caso de uso como "Sistema RAG interno para consulta de manuais técnicos em ambiente corporativo isolado".

> 📖 **Doc oficial:** [Acesso limitado ao Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/openai/limited-access)
>
> 📖 **Referência:** [Modelos disponíveis no Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/concepts/models)

---

## PASSO 4 — Criar a Virtual Network (VNet)

**O que é:** A VNet é a rede privada virtual onde todos os recursos vão se comunicar. Pense nela como o "prédio" onde cada "sala" (subnet) abriga um tipo de recurso. Nada dentro da VNet é acessível pela internet pública — exatamente o que precisamos para proteger os documentos da Fujifilm.

**Como fazer:**

1. Na barra de busca, digite **"Virtual networks"** e clique.
2. Clique em **"+ Create"**.
3. Aba **Basics:**
   - **Resource group:** `rg-kyotech-ai`
   - **Name:** `vnet-kyotech`
   - **Region:** East US 2
4. Clique em **Next** até chegar na aba **"IP Addresses"**.
5. Configure o **Address space:** `10.0.0.0/16` (isso dá 65.536 endereços — mais que suficiente).
6. Agora crie **quatro subnets**. Clique em **"+ Add a subnet"** para cada uma:

| Nome da Subnet | Intervalo | Para quê serve |
|---|---|---|
| `snet-app` | `10.0.1.0/24` | Container App (backend + frontend) |
| `snet-endpoints` | `10.0.2.0/24` | Private Endpoints (PostgreSQL, Blob, OpenAI) |
| `snet-postgres` | `10.0.3.0/24` | Delegada para o PostgreSQL Flexible Server |
| `AzureFirewallSubnet` | `10.0.4.0/26` | Reservada para o Firewall futuro (Fase 2) |

**Atenção com as subnets:**

- A subnet `snet-postgres` precisa de **delegação**. Ao criá-la, no campo "Delegate subnet to a service", selecione **"Microsoft.DBforPostgreSQL/flexibleServers"**.
- A subnet `AzureFirewallSubnet` **deve ter exatamente este nome** — a Azure exige isso. O CIDR mínimo é /26 (64 endereços). Não vamos usar agora, mas criá-la já evita reconfiguração na Fase 2.
- A subnet `snet-endpoints` não precisa de delegação.

7. Clique em **"Review + create"** → **"Create"**.

> 📖 **Doc oficial:** [Quickstart: Criar uma VNet pelo portal](https://learn.microsoft.com/en-us/azure/virtual-network/quick-create-portal)
>
> 📖 **Doc oficial:** [Adicionar/alterar/excluir subnets](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-network-manage-subnet)

---

## PASSO 5 — Criar o Azure Blob Storage

**O que é:** É o "armário de arquivos" onde os PDFs da Fujifilm ficam armazenados. Privado, sem acesso público.

**Como fazer:**

1. Na barra de busca, digite **"Storage accounts"** e clique.
2. Clique em **"+ Create"**.
3. Aba **Basics:**
   - **Resource group:** `rg-kyotech-ai`
   - **Storage account name:** `stkyotechai` (só letras minúsculas e números, sem hífens)
   - **Region:** East US 2
   - **Performance:** Standard
   - **Redundancy:** LRS (Locally-redundant storage) — suficiente para o MVP, ~$0.018/GB/mês.
4. Aba **Advanced:**
   - **Require secure transfer (HTTPS):** ✅ Sim
   - **Allow Blob anonymous access:** ❌ **Desmarque isso!** Crítico para segurança.
   - **Enable storage account key access:** ✅ Sim (precisamos para o backend)
5. Aba **Networking:**
   - **Network access:** selecione **"Disable public access and use private access"**.
   - Isso garante que o Blob só será acessível dentro da VNet via Private Endpoint.
6. Clique em **"Review + create"** → **"Create"**.

**Após criar, crie os containers:**

1. Entre no Storage Account recém-criado.
2. No menu lateral, clique em **"Containers"** (dentro de "Data storage").
3. Clique em **"+ Container"** e crie:
   - **`pdfs-originais`** — Access level: Private
   - **`pdfs-processados`** — Access level: Private

> 📖 **Doc oficial:** [Criar uma Storage Account](https://learn.microsoft.com/en-us/azure/storage/common/storage-account-create?tabs=azure-portal)

---

## PASSO 6 — Criar o PostgreSQL Flexible Server

**O que é:** O banco de dados onde ficam os metadados dos documentos, versões, chunks de texto e os vetores (embeddings) para busca semântica. Usa a extensão pgvector.

**Como fazer:**

1. Na barra de busca, digite **"Azure Database for PostgreSQL flexible servers"** e clique.
2. Clique em **"+ Create"**.
3. Aba **Basics:**
   - **Resource group:** `rg-kyotech-ai`
   - **Server name:** `psql-kyotech`
   - **Region:** East US 2
   - **PostgreSQL version:** 16 (mais recente estável)
   - **Workload type:** Development (isso seleciona o tier Burstable automaticamente)
   - **Compute + storage:** Clique em **"Configure server"**:
     - **Compute tier:** Burstable
     - **Compute size:** Standard_B2s (2 vCores, 4 GB RAM) — ~$50/mês
     - **Storage:** 32 GB (suficiente para MVP, pode aumentar depois)
     - **Backups:** 7 dias de retenção (padrão)
   - **Admin username:** `kyotech_admin`
   - **Password:** crie uma senha forte e **anote em local seguro**.
4. Aba **Networking:**
   - **Connectivity method:** **Private access (VNet Integration)**
   - **Virtual network:** selecione `vnet-kyotech`
   - **Subnet:** selecione `snet-postgres` (a delegada)
   - **Private DNS zone:** deixe a Azure criar automaticamente (algo como `psql-kyotech.private.postgres.database.azure.com`)
5. Clique em **"Review + create"** → **"Create"**.

**Demora ~5–10 minutos para provisionar.**

**Após criar, ative o pgvector:**

1. Entre no servidor PostgreSQL recém-criado.
2. No menu lateral, clique em **"Server parameters"**.
3. Na busca, digite **`azure.extensions`**.
4. No campo value, adicione: **`VECTOR`** (selecione na lista).
5. Clique em **"Save"**.

**Depois, conecte ao banco** (via Azure Cloud Shell ou psql local, se estiver na VNet) e execute:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

> 📖 **Doc oficial:** [Quickstart: Criar PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/quickstart-create-server-portal)
>
> 📖 **Doc oficial:** [Usar pgvector no Azure PostgreSQL](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-use-pgvector)
>
> 📖 **Doc oficial:** [Tiers de compute e preços](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-compute)

---

## PASSO 7 — Criar o Azure OpenAI + Deployments

**Pré-requisito:** Sua conta precisa ter acesso ao Azure OpenAI (verificado no Passo 3).

**Como criar o recurso:**

1. Na barra de busca, digite **"Azure OpenAI"** e clique.
2. Clique em **"+ Create"**.
3. Preencha:
   - **Resource group:** `rg-kyotech-ai`
   - **Region:** East US 2
   - **Name:** `aoai-kyotech`
   - **Pricing tier:** Standard S0
4. Aba **Network:**
   - Selecione **"Disabled"** para acesso público (vamos usar Private Endpoint).
   - Ou, temporariamente, **"All networks"** para testar e depois mudar para Private Endpoint.
5. Clique em **"Review + create"** → **"Create"**.

**Após criar, faça os deployments dos modelos:**

1. Entre no recurso `aoai-kyotech`.
2. Clique em **"Model deployments"** → **"Manage Deployments"** (abre o Azure AI Foundry).
3. Clique em **"+ Create new deployment"** e crie três:

| Nome do Deployment | Modelo | Para quê |
|---|---|---|
| `gpt4o-mini` | gpt-4o-mini | Query rewriting + classificação (barato, rápido) |
| `gpt4o` | gpt-4o | Geração de respostas finais (mais capaz) |
| `embedding-small` | text-embedding-3-small | Gerar vetores dos chunks de texto |

4. Para cada deployment, comece com **quota baixa** (ex: 10K TPM). Você pode aumentar depois.

> 📖 **Doc oficial:** [Criar recurso Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/create-resource)
>
> 📖 **Doc oficial:** [Criar deployments de modelo](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/working-with-models)

---

## PASSO 8 — Criar os Private Endpoints

**O que é:** Private Endpoints criam uma "ponte privada" entre a VNet e cada serviço Azure. Com isso, o tráfego nunca sai da rede interna da Microsoft — os dados da Fujifilm nunca tocam a internet pública.

**Precisa criar para:** Blob Storage e Azure OpenAI. O PostgreSQL já ficou privado via VNet Integration no Passo 6.

### 8A — Private Endpoint para o Blob Storage

1. Na barra de busca, digite **"Private endpoints"** e clique.
2. Clique em **"+ Create"**.
3. Aba **Basics:**
   - **Resource group:** `rg-kyotech-ai`
   - **Name:** `pe-blob-kyotech`
   - **Region:** East US 2
4. Aba **Resource:**
   - **Resource type:** `Microsoft.Storage/storageAccounts`
   - **Resource:** `stkyotechai`
   - **Target sub-resource:** `blob`
5. Aba **Virtual Network:**
   - **Virtual network:** `vnet-kyotech`
   - **Subnet:** `snet-endpoints`
6. Aba **DNS:**
   - **Integrate with private DNS zone:** ✅ Sim (deixe criar automaticamente)
7. **"Review + create"** → **"Create"**.

### 8B — Private Endpoint para o Azure OpenAI

Repita o mesmo processo com:
- **Name:** `pe-openai-kyotech`
- **Resource type:** `Microsoft.CognitiveServices/accounts`
- **Resource:** `aoai-kyotech`
- **Target sub-resource:** `account`
- Mesmo VNet e subnet (`snet-endpoints`)

> 📖 **Doc oficial:** [O que é Azure Private Endpoint?](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-overview)
>
> 📖 **Doc oficial:** [Criar Private Endpoint pelo portal](https://learn.microsoft.com/en-us/azure/private-link/create-private-endpoint-portal)

---

## PASSO 9 — Verificação Final

Após completar todos os passos, você deve ter os seguintes recursos no `rg-kyotech-ai`:

| # | Recurso | Nome | Status |
|---|---|---|---|
| 1 | Resource Group | `rg-kyotech-ai` | ☐ Criado |
| 2 | Budget Alerts | `budget-kyotech-1000` + `budget-creditos-total` | ☐ Configurado |
| 3 | Virtual Network | `vnet-kyotech` (4 subnets) | ☐ Criado |
| 4 | Storage Account | `stkyotechai` (2 containers) | ☐ Criado, público desabilitado |
| 5 | PostgreSQL Flexible | `psql-kyotech` (B2s, pgvector ativo) | ☐ Criado, VNet integrado |
| 6 | Azure OpenAI | `aoai-kyotech` (3 deployments) | ☐ Criado (ou aguardando aprovação) |
| 7 | Private Endpoint Blob | `pe-blob-kyotech` | ☐ Criado |
| 8 | Private Endpoint OpenAI | `pe-openai-kyotech` | ☐ Criado |
| 9 | Private DNS Zones | (criadas automaticamente) | ☐ Verificado |

**Para verificar no portal:**

1. Vá em **Resource groups** → `rg-kyotech-ai`.
2. Todos os recursos acima devem aparecer listados.
3. Clique em cada um e verifique se o status é **"Succeeded"** ou **"Running"**.

---

## Custo Estimado do Mês 1

Após completar o setup, seu burn rate mensal estimado será:

| Recurso | Custo/mês (USD) |
|---|---|
| PostgreSQL B2s | ~$50 |
| Storage (< 1 GB inicial) | ~$0.10 |
| Private Endpoints (x2) | ~$15 |
| Private DNS Zones (x2) | ~$1 |
| Azure OpenAI (testes leves) | ~$5–15 |
| **Total Mês 1** | **~$70–80** |

Os USD 1.000 cobrem confortavelmente **12+ meses** neste ritmo.

---

## Próximo Passo: Criar o Schema do Banco

Após esta configuração estar pronta, o próximo passo técnico é conectar ao PostgreSQL e criar as tabelas do modelo de dados (conforme Seção 4 do documento de arquitetura): `equipments`, `documents`, `document_versions` e `chunks`.

---

## Links Rápidos — Documentação Oficial

| Tópico | Link |
|---|---|
| Resource Groups | [learn.microsoft.com/...manage-resource-groups-portal](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/manage-resource-groups-portal) |
| Budget Alerts | [learn.microsoft.com/...tutorial-acm-create-budgets](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets) |
| Virtual Networks | [learn.microsoft.com/...quick-create-portal](https://learn.microsoft.com/en-us/azure/virtual-network/quick-create-portal) |
| Storage Account | [learn.microsoft.com/...storage-account-create](https://learn.microsoft.com/en-us/azure/storage/common/storage-account-create?tabs=azure-portal) |
| PostgreSQL Flexible Server | [learn.microsoft.com/...quickstart-create-server-portal](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/quickstart-create-server-portal) |
| pgvector no PostgreSQL | [learn.microsoft.com/...how-to-use-pgvector](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-use-pgvector) |
| Azure OpenAI — Criar recurso | [learn.microsoft.com/...create-resource](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/create-resource) |
| Private Endpoints | [learn.microsoft.com/...create-private-endpoint-portal](https://learn.microsoft.com/en-us/azure/private-link/create-private-endpoint-portal) |
| Acesso limitado ao OpenAI | [learn.microsoft.com/...limited-access](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/openai/limited-access) |
| Cost Management Alerts | [learn.microsoft.com/...cost-mgt-alerts](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/cost-mgt-alerts-monitor-usage-spending) |

---

*HaruCode © 2026 — Documento de uso interno*