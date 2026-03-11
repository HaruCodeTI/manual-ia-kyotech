# Kyotech AI — Custos Azure (Março 2026)

## Resumo Mensal

| Serviço | Uso Baixo (~100 req/dia) | Uso Médio (~1.000 req/dia) |
|---------|--------------------------|-------------------------------|
| PostgreSQL Flexible Server (B2s) | $53.32 | $53.32 |
| Azure OpenAI | $9.21 | $92.10 |
| Blob Storage (LRS Hot) | ~$0.03 | ~$0.22 |
| Container Apps (Consumption) | $0.00 | $0.00 |
| VNet + 3 Private Endpoints | $21.91 | $22.00 |
| Container Registry (Basic) | $5.00 | $5.00 |
| **TOTAL** | **~$89/mês** | **~$173/mês** |

---

## Detalhamento por Serviço

### PostgreSQL Flexible Server — B2s (Canada Central)

| Componente | Detalhe | Custo |
|-----------|---------|-------|
| Compute (B2s) | 2 vCores, 4 GiB RAM | $49.64/mês |
| Storage | 32 GB x $0.115/GiB | $3.68/mês |

- Custo fixo, não escala com uso
- Suporta stop/start — desligar fora do horário pode economizar até 50% do compute
- Upgrade para D2s_v3 (General Purpose): ~$140/mês se necessário

### Azure OpenAI (East US 2)

**Preço por 1M tokens:**

| Modelo | Input | Output |
|--------|-------|--------|
| gpt-4o | $2.50 | $10.00 |
| gpt-4o-mini | $0.15 | $0.60 |
| text-embedding-3-small | $0.02 | N/A |

**Estimativa por volume:**

| Volume | gpt-4o-mini | gpt-4o | Embeddings | Total |
|--------|------------|--------|------------|-------|
| 3.000 req/mês | $2.43 | $6.75 | $0.03 | $9.21 |
| 30.000 req/mês | $24.30 | $67.50 | $0.30 | $92.10 |

- **Principal driver de custo variável**
- gpt-4o output é 17x mais caro que gpt-4o-mini
- Prompt caching pode reduzir tokens de input em até 50%

### Blob Storage — Standard LRS, Hot Tier

| Volume | Storage | Operações | Total |
|--------|---------|-----------|-------|
| 500 MB | $0.01 | ~$0.02 | ~$0.03 |
| 5 GB | $0.12 | ~$0.10 | ~$0.22 |

- Custo desprezível mesmo com escala

### Container Apps — Consumption Plan (2 apps)

**Free tier mensal:** 180.000 vCPU-seconds, 360.000 GiB-seconds, 2M requests

- Uso baixo e médio ficam dentro do free tier
- Custos só aparecem com centenas de milhares de requests
- Além do free tier: ~$0.000024/vCPU-s e ~$0.000003/GiB-s

### VNet + Private Endpoints

| Componente | Custo |
|-----------|-------|
| VNet | $0.00 (gratuito) |
| Private Endpoint (Blob) | $7.30/mês |
| Private Endpoint (OpenAI) | $7.30/mês |
| Private Endpoint (PostgreSQL) | $7.30/mês |
| Data processing | ~$0.01–$0.10/mês |

- Custo fixo por endpoint: $0.01/hora

### Container Registry — Basic Tier

| Componente | Custo |
|-----------|-------|
| Basic (10 GB incluído) | $5.00/mês |

---

## Otimizações Possíveis

1. **Maximizar gpt-4o-mini** — Usar para query rewrite e respostas simples, reservar gpt-4o para respostas complexas
2. **Prompt caching** — Reduz até 50% dos tokens de input em prompts repetitivos
3. **Batch API** — 50% de desconto para processamento não-realtime (ex: reindexação)
4. **PostgreSQL stop/start** — Desligar fora do horário comercial = até -50% no compute
5. **Avaliar remoção de Private Endpoints** — Economiza ~$22/mês, mas reduz segurança de rede

---

## Projeção de Escala

| Cenário | Requests/mês | Custo estimado |
|---------|-------------|---------------|
| Piloto (1-5 usuários) | ~3.000 | ~$89/mês |
| Produção leve (10-20 usuários) | ~15.000 | ~$130/mês |
| Produção média (50+ usuários) | ~30.000 | ~$173/mês |
| Produção alta (100+ usuários) | ~100.000 | ~$350/mês |

O principal fator de escala é o consumo de tokens do Azure OpenAI (gpt-4o).
