# Kyotech AI — Análise de Custos e Modelo de Cobrança

## 1. Custos Fixos (infraestrutura Azure)

Estes custos existem independente do uso:

| Serviço | Detalhe | Custo/mês |
|---------|---------|-----------|
| PostgreSQL Flexible Server | B2s (2 vCores, 4 GB RAM, 32 GB storage) | $53.32 |
| Container Apps (2 apps) | Consumption plan (free tier cobre o uso) | $0.00 |
| Container Registry | Basic tier (10 GB) | $5.00 |
| VNet + 3 Private Endpoints | Blob + OpenAI + PostgreSQL ($7.30 cada) | $21.90 |
| Private DNS Zones (4 zonas) | Blob + OpenAI + PostgreSQL VNet + PostgreSQL PE | ~$2.00 |
| **Total fixo** | | **$82.22/mês** |

---

## 2. Custos Variáveis (Azure OpenAI)

### Preço por 1M tokens (Azure OpenAI)

| Modelo | Uso | Input | Output |
|--------|-----|-------|--------|
| gpt-4o | Geração de resposta | $2.50 | $10.00 |
| gpt-4o-mini | Rewrite da query (PT→EN) | $0.15 | $0.60 |
| text-embedding-3-small | Embeddings (busca + indexação) | $0.02 | — |

### Tokens consumidos por operação

**Cada pergunta do técnico consome:**

| Etapa | Modelo | Input | Output |
|-------|--------|-------|--------|
| Query rewrite | gpt-4o-mini | ~250 tokens | ~80 tokens |
| Query embedding | embedding-3-small | ~30 tokens | — |
| Geração de resposta | gpt-4o | ~2.800 tokens | ~600 tokens |

**Cada upload de PDF consome:**

| Etapa | Modelo | Tokens |
|-------|--------|--------|
| Embedding dos chunks | embedding-3-small | ~400 tokens × número de chunks |

Um PDF de ~200 páginas gera ~500 chunks → ~200.000 tokens de embedding por PDF.

---

## 3. Cenário Real: Kyotech (20 funcionários)

### Premissas

| Parâmetro | Valor |
|-----------|-------|
| Funcionários totais | 20 |
| Usuários ativos diários | 8 (~40%) |
| Perguntas por usuário/dia | 8 |
| Dias úteis/mês | 22 |
| Uploads de PDF/semana | 15 |
| Tamanho médio do PDF | ~200 páginas (~500 chunks) |

### Cálculo Mensal — Consultas

**Total de consultas/mês:** 8 usuários × 8 perguntas × 22 dias = **1.408 consultas**

| Modelo | Cálculo | Tokens/mês | Custo |
|--------|---------|-----------|-------|
| gpt-4o input | 1.408 × 2.800 | 3.94M | $9.85 |
| gpt-4o output | 1.408 × 600 | 845K | $8.45 |
| gpt-4o-mini input | 1.408 × 250 | 352K | $0.05 |
| gpt-4o-mini output | 1.408 × 80 | 113K | $0.07 |
| embedding (query) | 1.408 × 30 | 42K | ~$0.00 |
| **Subtotal consultas** | | | **$18.42** |

### Cálculo Mensal — Uploads/Ingestion

**Total de uploads/mês:** 15/semana × 4.3 semanas = **~65 PDFs**

| Modelo | Cálculo | Tokens/mês | Custo |
|--------|---------|-----------|-------|
| embedding (chunks) | 65 PDFs × 500 chunks × 400 tokens | 13M | $0.26 |
| **Subtotal ingestion** | | | **$0.26** |

### Cálculo Mensal — Storage

| Item | Cálculo | Custo |
|------|---------|-------|
| Blob Storage (PDFs) | ~65 PDFs × 3 MB = 195 MB/mês (acumulativo) | ~$0.05 |
| PostgreSQL storage | 32 GB base + crescimento lento | já incluído no fixo |

---

## 4. Custo Total — Cenário Kyotech

| Categoria | Custo/mês |
|-----------|-----------|
| Infraestrutura fixa | $80.22 |
| Azure OpenAI (consultas) | $18.42 |
| Azure OpenAI (ingestion) | $0.26 |
| Blob Storage | ~$0.05 |
| **TOTAL** | **~$99/mês** |

**Em reais (câmbio ~R$5,80):** ~R$574/mês

---

## 5. Como os Custos Escalam

### Se o uso dobrar (16 usuários ativos, 30 uploads/semana)

| Categoria | Custo/mês |
|-----------|-----------|
| Infraestrutura fixa | $80.22 (não muda) |
| Azure OpenAI (consultas) | $36.84 |
| Azure OpenAI (ingestion) | $0.52 |
| **TOTAL** | **~$118/mês** (~R$684) |

### Se o uso triplicar (24 ativos, 45 uploads/semana)

| Categoria | Custo/mês |
|-----------|-----------|
| Infraestrutura fixa | $80.22 |
| Azure OpenAI (consultas) | $55.26 |
| Azure OpenAI (ingestion) | $0.78 |
| **TOTAL** | **~$136/mês** (~R$789) |

### Se precisar escalar o banco (>50 usuários simultâneos)

| Upgrade | De → Para | Impacto |
|---------|-----------|---------|
| PostgreSQL | B2s → D2s_v3 | +$87/mês |
| Container Apps | Free → dedicado | +$50-100/mês |

### Observações importantes sobre escala

1. **O custo de ingestion (upload) é desprezível** — embedding-3-small custa $0.02/M tokens
2. **O principal driver é o gpt-4o na geração de respostas** — ~95% do custo variável
3. **Infraestrutura fixa domina** — no cenário Kyotech, ~80% do custo é fixo
4. **Escala linear** — dobrar uso ≈ +$19/mês, não dobra o custo total
5. **Blob Storage é irrelevante** — mesmo com 1.000 PDFs, custo < $1/mês

---

## 6. Proposta Comercial — Modelo de Cobrança

### Modelo: Setup + Mensalidade Fixa

#### Setup (implantação) — R$18.000

| Item | Descrição | Horas |
|------|-----------|-------|
| Infraestrutura Azure | Provisionamento, VNet, Private Endpoints, CI/CD | ~40h |
| Backend RAG | Pipeline completo: extração, busca híbrida, geração com citações | ~80h |
| Frontend | Interface de chat, upload, viewer seguro, dashboard | ~60h |
| Testes + Documentação | Suite automatizada, diagramas C4, ADRs, API docs | ~30h |
| Auth + RBAC + Domínio | Clerk, controle de acesso por perfil, SSL | ~10h |
| **Total** | | **~220h** |

#### Mensalidade — R$1.800/mês

| O que está incluído | Detalhe |
|---------------------|---------|
| Hospedagem Azure | PostgreSQL, Container Apps, Blob Storage, OpenAI |
| Até 25 usuários ativos | Escalável conforme demanda |
| Uploads ilimitados | PDFs de manuais e informativos |
| Suporte técnico | Correções, monitoramento, atualizações de segurança |
| Backups automáticos | PostgreSQL + Blob Storage |
| SSL + domínio custom | HTTPS com certificado gerenciado |

#### O que NÃO está incluído (cobrado à parte)

- Desenvolvimento de novas funcionalidades sob demanda
- Integrações com sistemas externos (ERP, SAP, etc.)
- Treinamento presencial
- Consultoria de IA/dados além do escopo contratado

---

### Justificativa de Valor

#### Economia gerada para o cliente

| Cálculo | Valor |
|---------|-------|
| Técnicos ativos usando o sistema | 8 |
| Tempo economizado por técnico/dia (busca em manuais físicos) | ~30 min |
| Dias úteis/mês | 22 |
| Custo médio hora/técnico | ~R$30 |
| **Economia mensal em produtividade** | **~R$2.640/mês** |

**ROI:** A mensalidade de R$1.800 se paga com a economia de tempo dos técnicos. O sistema gera ROI positivo já no primeiro mês (economia de R$840/mês líquidos).

#### Composição de custo e margem (interno HaruCode)

| Item | Valor/mês |
|------|-----------|
| Custo real Azure | ~R$574 |
| Margem de segurança (câmbio + picos de uso) | ~R$170 |
| **Custo protegido** | **~R$745** |
| **Mensalidade cobrada** | **R$1.800** |
| **Margem líquida** | **~R$1.055/mês (59%)** |
| **Receita recorrente anual** | **R$12.660** |

#### Break-even do desconto no setup

O setup real (~220h × R$120/h) custaria ~R$26.400. Cobrando R$18.000, o "desconto" de R$8.400 é recuperado em ~8 meses de mensalidade.

---

### Cenários de Escalabilidade

Se a Kyotech crescer, o custo Azure sobe pouco e a margem se mantém:

| Cenário | Usuários ativos | Custo Azure | Mensalidade | Margem |
|---------|----------------|-------------|-------------|--------|
| **Atual** | 8 | ~R$574 | R$1.800 | 59% |
| **Crescimento** | 16 | ~R$684 | R$1.800 | 52% |
| **Expansão** | 24 | ~R$789 | R$2.200* | 55% |

*Upgrade para faixa Enterprise se ultrapassar 25 ativos.

---

### Por que Mensalidade Fixa (e não por uso)

1. **Previsibilidade** — cliente sabe exatamente quanto paga
2. **Incentiva adoção** — técnico não tem medo de perguntar
3. **Simplicidade** — sem medição de tokens ou billing complexo
4. **Receita estável** — MRR previsível para a HaruCode
5. **Custo variável baixo** — OpenAI custa ~R$110/mês no cenário Kyotech, não justifica cobrança por uso

---

## 7. Referência de Preços Azure

### Preços por token (Azure OpenAI, Março 2026)

| Modelo | Input (por 1M) | Output (por 1M) |
|--------|----------------|-----------------|
| gpt-4o | $2.50 | $10.00 |
| gpt-4o-mini | $0.15 | $0.60 |
| text-embedding-3-small | $0.02 | — |

### Preços de infraestrutura

| Serviço | Tier | Preço/mês |
|---------|------|-----------|
| PostgreSQL Flexible | B2s (2 vCores, 4GB) | $49.64 + $3.68 storage |
| Container Apps | Consumption (free tier) | $0.00 |
| Container Registry | Basic | $5.00 |
| Private Endpoint | Por endpoint | $7.30 |
| Blob Storage | Standard LRS Hot | $0.023/GB |

---

*Documento atualizado em Março/2026 — HaruCode · Documento interno — não compartilhar com cliente*
