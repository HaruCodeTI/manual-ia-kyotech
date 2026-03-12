# Kyotech AI — Hardening Checklist (IA-81)

**Data:** 11/03/2026 | **Deadline:** 13/03/2026 (sexta)
**Ref:** `docs/migracao-producao.md` (documentação completa)

---

## Status Atual da Infraestrutura

| Serviço | Acesso Público | Private Endpoint | Status |
|---------|---------------|-----------------|--------|
| Azure OpenAI (`aoai-kyotech`) | Desabilitado | `pe-openai-kyotech` | OK |
| Blob Storage (`stkyotechai`) | Desabilitado | `pe-blob-kyotech` | OK |
| PostgreSQL (`psql-kyotech`) | Desabilitado | `pe-postgres-kyotech` (10.0.2.6) | OK (12/03/2026) |
| Container Apps (frontend) | Público (HTTPS) | N/A | Avaliar restrição IP |
| NSG `nsg-snet-app` | Associado a `snet-app` | N/A | OK (12/03/2026) |
| NSG `nsg-snet-endpoints` | Associado a `snet-endpoints` | N/A | OK (12/03/2026) |

---

## Etapas para Sexta-feira

### Etapa 1: Fechar PostgreSQL (30 min)

**Pré-requisito:** Confirmar que o backend em Container Apps acessa o banco via VNet (o que já funciona em produção).

```bash
# 1. Listar regras de firewall atuais
az postgres flexible-server firewall-rule list \
  --resource-group rg-kyotech-ai \
  --name psql-kyotech \
  -o table

# 2. Deletar cada regra (substituir RULE_NAME pelo nome listado acima)
az postgres flexible-server firewall-rule delete \
  --resource-group rg-kyotech-ai \
  --name psql-kyotech \
  --rule-name RULE_NAME \
  --yes

# 3. Desabilitar acesso público
az postgres flexible-server update \
  --resource-group rg-kyotech-ai \
  --name psql-kyotech \
  --public-access Disabled
```

**Validação:**
- [ ] `psql` local falha ao conectar (esperado)
- [ ] Chat no site continua respondendo normalmente
- [ ] Upload de PDF continua funcionando

**Rollback (se algo quebrar):**
```bash
az postgres flexible-server update \
  --resource-group rg-kyotech-ai \
  --name psql-kyotech \
  --public-access Enabled

az postgres flexible-server firewall-rule create \
  --resource-group rg-kyotech-ai \
  --name psql-kyotech \
  --rule-name allow-dev \
  --start-ip-address SEU_IP \
  --end-ip-address SEU_IP
```

---

### Etapa 2: Configurar NSGs (1 hora)

```bash
# --- NSG para snet-app (Container Apps) ---
az network nsg create \
  --resource-group rg-kyotech-ai \
  --name nsg-snet-app

# Permitir saída para PostgreSQL (snet-postgres)
az network nsg rule create \
  --resource-group rg-kyotech-ai \
  --nsg-name nsg-snet-app \
  --name allow-postgres \
  --priority 100 \
  --direction Outbound \
  --access Allow \
  --protocol Tcp \
  --source-address-prefixes "10.0.1.0/24" \
  --destination-address-prefixes "10.0.3.0/24" \
  --destination-port-ranges 5432

# Permitir saída para Private Endpoints (snet-endpoints)
az network nsg rule create \
  --resource-group rg-kyotech-ai \
  --nsg-name nsg-snet-app \
  --name allow-private-endpoints \
  --priority 200 \
  --direction Outbound \
  --access Allow \
  --protocol Tcp \
  --source-address-prefixes "10.0.1.0/24" \
  --destination-address-prefixes "10.0.2.0/24" \
  --destination-port-ranges 443

# Permitir saída HTTPS (Clerk auth + ACR pull)
az network nsg rule create \
  --resource-group rg-kyotech-ai \
  --nsg-name nsg-snet-app \
  --name allow-https-outbound \
  --priority 300 \
  --direction Outbound \
  --access Allow \
  --protocol Tcp \
  --source-address-prefixes "10.0.1.0/24" \
  --destination-address-prefixes "Internet" \
  --destination-port-ranges 443

# Negar todo o resto de saída
az network nsg rule create \
  --resource-group rg-kyotech-ai \
  --nsg-name nsg-snet-app \
  --name deny-all-outbound \
  --priority 4000 \
  --direction Outbound \
  --access Deny \
  --protocol '*' \
  --source-address-prefixes '*' \
  --destination-address-prefixes '*' \
  --destination-port-ranges '*'

# Associar à subnet
az network vnet subnet update \
  --resource-group rg-kyotech-ai \
  --vnet-name vnet-kyotech \
  --name snet-app \
  --network-security-group nsg-snet-app

# --- NSG para snet-endpoints ---
az network nsg create \
  --resource-group rg-kyotech-ai \
  --name nsg-snet-endpoints

# Permitir entrada apenas de snet-app
az network nsg rule create \
  --resource-group rg-kyotech-ai \
  --nsg-name nsg-snet-endpoints \
  --name allow-from-app \
  --priority 100 \
  --direction Inbound \
  --access Allow \
  --protocol Tcp \
  --source-address-prefixes "10.0.1.0/24" \
  --destination-address-prefixes "10.0.2.0/24" \
  --destination-port-ranges 443

# Negar tudo mais
az network nsg rule create \
  --resource-group rg-kyotech-ai \
  --nsg-name nsg-snet-endpoints \
  --name deny-all-inbound \
  --priority 4000 \
  --direction Inbound \
  --access Deny \
  --protocol '*' \
  --source-address-prefixes '*' \
  --destination-address-prefixes '*' \
  --destination-port-ranges '*'

az network vnet subnet update \
  --resource-group rg-kyotech-ai \
  --vnet-name vnet-kyotech \
  --name snet-endpoints \
  --network-security-group nsg-snet-endpoints
```

**Validação:**
- [ ] Chat continua respondendo
- [ ] Upload continua funcionando
- [ ] PDFs abrem no viewer

**Rollback (se algo quebrar):**
```bash
# Desassociar NSG da subnet
az network vnet subnet update \
  --resource-group rg-kyotech-ai \
  --vnet-name vnet-kyotech \
  --name snet-app \
  --remove networkSecurityGroup
```

---

### Etapa 3: Restrição de IP no Frontend (Opcional — 15 min)

Whitelist do IP do escritório da Kyotech no ingress do frontend:

```bash
# Descobrir IP público do escritório (pedir ao cliente ou acessar ifconfig.me)
az containerapp ingress access-restriction set \
  --name kyotech-frontend \
  --resource-group rg-kyotech-ai \
  --rule-name allow-kyotech-office \
  --action Allow \
  --ip-address "IP_DO_ESCRITORIO/32" \
  --description "Escritório Kyotech"
```

**Nota:** Não aplicar isso antes da demo — ou incluir seu IP também. Pode ser feito pós-apresentação com o cliente.

---

## Itens que NÃO precisam ser feitos para sexta

| Item | Motivo |
|------|--------|
| Azure Firewall | ~$335/mês, overkill para MVP. NSGs são suficientes |
| Fechar Blob/OpenAI | Já estão fechados |
| Migrar Clerk → Entra ID | Fase 3 |
| VPN Gateway | Fase 3 |
| Front Door + WAF | Fase 3, se cliente exigir |

---

## Impacto no Custo

| Item | Custo mensal |
|------|-------------|
| NSGs | $0 (sem custo) |
| Fechar PostgreSQL público | $0 (sem mudança) |
| Restrição de IP | $0 (sem mudança) |
| **Total adicional** | **$0** |

Hardening via NSGs + Private Endpoints não tem custo adicional — os Private Endpoints já estão provisionados e pagos ($7.30/cada × 3 = $21.90/mês).

---

## Ordem de Execução

```
1. Fechar PostgreSQL .......... (30 min) → validar chat + upload     ✅ Concluído 12/03/2026
2. Configurar NSGs ............ (1 hora) → validar tudo novamente    ✅ Concluído 12/03/2026
3. Restrição IP (opcional) .... (15 min) → decidir com cliente       ⏳ Pós-demo
```

**Etapas 1 e 2 concluídas em 12/03/2026. Produção validada após cada etapa.**

---

*HaruCode © 2026 — Documento interno*
