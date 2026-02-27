# Kyotech AI — Migração para Produção

**HaruCode | Plano de Hardening e Produção**
**Data:** 27/02/2026 | **Fase:** 2 — Produção Segura

---

## Objetivo

Este documento descreve **exatamente** o que precisa mudar para migrar do ambiente de homologação para produção, onde documentos confidenciais da Fujifilm serão carregados. A premissa é que nenhum dado confidencial deve trafegar por redes públicas e nenhum serviço deve ter endpoint público.

### Princípio Fundamental

> Em produção, a única forma de acessar o sistema é via VPN corporativa ou rede interna da Kyotech. Zero acesso público.

---

## Estado Atual (Homologação) vs. Alvo (Produção)

| Componente | Homologação | Produção |
|---|---|---|
| Frontend ingress | Externo (HTTPS público) | Interno (VPN ou Front Door com WAF) |
| Backend ingress | Interno | Interno (sem mudança) |
| PostgreSQL | Acesso público + VNet | Somente VNet (acesso público desabilitado) |
| Azure OpenAI | Acesso público temporário | Somente Private Endpoint |
| Blob Storage | Acesso público temporário | Somente Private Endpoint |
| ACR | Acesso público | Private Endpoint ou Service Endpoint |
| Autenticação | Clerk dev mode | Clerk produção ou Microsoft Entra ID |
| Dados | PDFs de teste | Manuais e informativos Fujifilm reais |
| DNS | URL gerada pelo Azure (*.azurecontainerapps.io) | Domínio customizado (ex: ai.kyotech.com.br) |
| Certificado SSL | Gerenciado pelo Azure (automático) | Gerenciado pelo Azure ou próprio |
| Firewall | Nenhum | Azure Firewall Basic na AzureFirewallSubnet |
| NSG | Padrão | Regras deny-all + allow explícito |
| Logs | Console apenas | Application Insights + Log Analytics |

---

## Etapas da Migração

A migração não é um evento único — é uma sequência controlada de 8 etapas, cada uma validável independentemente. Não pule etapas.

---

### Etapa 1 — Configurar Autenticação de Produção

**Por que primeiro:** Antes de carregar dados confidenciais, precisamos garantir que apenas usuários autorizados acessam o sistema.

**Opção A — Clerk em Produção:**

1. No Clerk Dashboard, crie uma instância de Produção (separada da dev)
2. Configure o domínio customizado (ex: `auth.kyotech.com.br`)
3. Crie os usuários da Kyotech (gerentes + técnicos)
4. Defina roles via `publicMetadata`:
   - `{"role": "Admin"}` para gerentes (upload + chat + stats)
   - `{"role": "Technician"}` para técnicos (somente chat)
5. Atualize as variáveis no Container App:
   - `CLERK_JWKS_URL` → URL do JWKS de produção
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` → Key de produção
6. Rebuild e redeploy do frontend

**Opção B — Microsoft Entra ID (SSO corporativo):**

Se a Kyotech já usa Microsoft 365, considere substituir o Clerk por Entra ID:

1. Registrar aplicação no Entra ID da Kyotech
2. Configurar OIDC/OAuth2 no backend (substituir `auth.py`)
3. Configurar `@azure/msal-react` no frontend (substituir Clerk)
4. Vantagem: login com email corporativo, sem custo extra
5. Desvantagem: mais complexo de implementar, depende da TI da Kyotech

**Recomendação:** Começar com Clerk em produção (mais rápido) e avaliar migração para Entra ID na Fase 3 se a Kyotech preferir.

**Validação:** Testar login com um usuário de teste de produção. Confirmar que roles (Admin/Technician) funcionam. Confirmar que JWKS URL de produção valida tokens corretamente.

---

### Etapa 2 — Fechar Acesso Público do PostgreSQL

**O que muda:** Remover a regra de firewall que permite conexão pela internet.

```bash
# Listar regras de firewall atuais
az postgres flexible-server firewall-rule list \
  --resource-group rg-kyotech-ai \
  --name psql-kyotech \
  -o table

# Deletar cada regra (substitua RULE_NAME pelo nome listado)
az postgres flexible-server firewall-rule delete \
  --resource-group rg-kyotech-ai \
  --name psql-kyotech \
  --rule-name RULE_NAME \
  --yes

# Desabilitar acesso público
az postgres flexible-server update \
  --resource-group rg-kyotech-ai \
  --name psql-kyotech \
  --public-access Disabled
```

**Validação:** Após desabilitar, tente conectar via VS Code — deve falhar. O backend no Container Apps (dentro da VNet) deve continuar funcionando normalmente.

**Acesso para desenvolvimento:** A partir daqui, para acessar o banco você precisará de:
- Azure Cloud Shell (tem acesso à VNet)
- Jumpbox VM dentro da VNet
- Azure Bastion (se configurado)

---

### Etapa 3 — Fechar Acesso Público do Azure OpenAI

```bash
az cognitiveservices account update \
  --resource-group rg-kyotech-ai \
  --name aoai-kyotech \
  --public-network-access Disabled
```

**Validação:** O backend no Container Apps (dentro da VNet) deve continuar chamando o OpenAI via Private Endpoint. Teste fazendo uma pergunta no chat.

---

### Etapa 4 — Fechar Acesso Público do Blob Storage

```bash
az storage account update \
  --resource-group rg-kyotech-ai \
  --name stkyotechai \
  --public-network-access Disabled
```

**Validação:** O upload de PDFs e a geração de SAS URLs devem continuar funcionando pelo backend (dentro da VNet).

**Atenção com SAS URLs:** As URLs assinadas geradas pelo backend apontam para `stkyotechai.blob.core.windows.net`. Com acesso público desabilitado, o browser do técnico **não conseguirá** abrir o PDF diretamente — a URL resolve para o endpoint público que está bloqueado.

**Solução:** O viewer de PDF precisa ser redesenhado para:
- Backend busca o PDF via Private Endpoint e faz streaming para o frontend, **OU**
- Configurar Azure Front Door com Private Link para o Blob Storage

Isso será detalhado na Etapa 7.

---

### Etapa 5 — Configurar NSG (Network Security Groups)

Criar regras restritivas para cada subnet.

#### NSG para `snet-app` (Container Apps)

```bash
# Criar NSG
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

# Permitir saída para Clerk (autenticação)
az network nsg rule create \
  --resource-group rg-kyotech-ai \
  --nsg-name nsg-snet-app \
  --name allow-clerk-auth \
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

# Associar NSG à subnet
az network vnet subnet update \
  --resource-group rg-kyotech-ai \
  --vnet-name vnet-kyotech \
  --name snet-app \
  --network-security-group nsg-snet-app
```

> **Nota sobre Clerk:** A regra `allow-clerk-auth` permite saída para internet na porta 443. Se migrar para Entra ID, essa regra pode ser restrita ao IP específico do Entra. Se usar Azure Firewall (Etapa 6), remova essa regra e controle o egress pelo Firewall.

#### NSG para `snet-endpoints`

```bash
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

**Validação:** Após aplicar os NSGs, testar upload + chat + viewer de PDF. Tudo deve continuar funcionando porque o tráfego permitido é exatamente o que o sistema usa.

---

### Etapa 6 — Azure Firewall (Opcional, Recomendado)

O Azure Firewall dá controle granular sobre tráfego de saída (egress) — permite auditar e bloquear qualquer tentativa de exfiltração de dados.

**Custo:** Azure Firewall Basic = ~$335/mês. Considerando que já temos ~$910 em créditos e que o projeto vai gerar receita recorrente para a HaruCode, o investimento é justificável se a Kyotech exigir compliance rigoroso.

**Alternativa mais barata:** Os NSGs da Etapa 5 já bloqueiam egress não-autorizado. O Firewall adiciona logging detalhado e FQDN filtering (ex: permitir saída apenas para `*.clerk.com` e `*.azure.com`). Se o orçamento for limitado, os NSGs são suficientes e o Firewall pode vir na Fase 3.

```bash
# Criar IP público para o Firewall
az network public-ip create \
  --resource-group rg-kyotech-ai \
  --name pip-firewall-kyotech \
  --sku Standard \
  --allocation-method Static

# Criar Azure Firewall Basic
az network firewall create \
  --resource-group rg-kyotech-ai \
  --name fw-kyotech \
  --sku AZFW_VNet \
  --tier Basic \
  --vnet-name vnet-kyotech \
  --location canadacentral

# Configurar IP público no Firewall
az network firewall ip-config create \
  --resource-group rg-kyotech-ai \
  --firewall-name fw-kyotech \
  --name fw-config \
  --public-ip-address pip-firewall-kyotech \
  --vnet-name vnet-kyotech
```

Depois, criar regras de aplicação para permitir apenas domínios necessários e uma UDR (User Defined Route) para forçar o tráfego de `snet-app` pelo Firewall.

---

### Etapa 7 — Fechar Ingress do Frontend

**Cenário:** A Kyotech tem VPN ou rede corporativa.

Mude o frontend para ingress interno:

```bash
az containerapp ingress update \
  --name kyotech-frontend \
  --resource-group rg-kyotech-ai \
  --type internal
```

A partir deste ponto, o frontend só é acessível de dentro da VNet. Os técnicos acessam via:

**Opção A — Azure VPN Gateway:**
- Custo: ~$27/mês (Basic SKU)
- Técnicos instalam o VPN client no notebook
- Conectam à VNet da Azure e acessam a URL interna

**Opção B — Azure Front Door + WAF (para acesso sem VPN):**
- Custo: ~$35/mês (Standard)
- Front Door fica na frente do frontend com Private Link
- WAF filtra ataques e pode restringir por IP (whitelist do escritório Kyotech)
- Técnicos acessam via URL pública protegida pelo WAF

**Opção C — Manter ingress externo + restrição de IP:**
- Custo: $0 extra
- Mais simples, menos seguro
- Whitelist dos IPs da Kyotech no Container Apps:

```bash
az containerapp ingress access-restriction set \
  --name kyotech-frontend \
  --resource-group rg-kyotech-ai \
  --rule-name allow-kyotech-office \
  --action Allow \
  --ip-address "IP_DO_ESCRITORIO/32" \
  --description "Escritório Kyotech"
```

**Recomendação:** Começar com Opção C (restrição de IP), migrar para Opção B (Front Door) quando houver orçamento aprovado pelo cliente.

---

### Etapa 8 — Redesenhar Viewer de PDF

Com o Blob Storage sem acesso público, as SAS URLs não funcionam mais para o browser do técnico. Duas soluções:

**Solução A — Proxy pelo Backend (Recomendada para MVP):**

Criar um endpoint no backend que busca o PDF via Private Endpoint e faz streaming:

```python
@router.get("/pdf-proxy")
async def pdf_proxy(
    storage_path: str,
    page: int = 1,
    _user: CurrentUser = Depends(get_current_user),
):
    # Busca o PDF via Blob Storage (Private Endpoint, dentro da VNet)
    blob_bytes = download_blob(storage_path)
    
    return StreamingResponse(
        io.BytesIO(blob_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename=doc.pdf",
        }
    )
```

O frontend muda o viewer para apontar para `/api/v1/chat/pdf-proxy?storage_path=...&page=N`.

**Solução B — Front Door com Private Link para Blob:**

Mais elegante mas mais complexo e caro. O Azure Front Door conecta ao Blob via Private Link e serve os PDFs com cache. O frontend usa URLs do Front Door em vez de SAS URLs.

---

## Checklist Final de Produção

Antes de carregar documentos Fujifilm reais, **todos** os itens abaixo devem estar marcados:

### Autenticação e Autorização

- [ ] Clerk em modo produção (ou Entra ID)
- [ ] Usuários Kyotech criados com roles corretos
- [ ] Endpoint de upload restrito a role Admin (`require_role("Admin")`)
- [ ] Tokens JWT sendo validados no backend

### Rede e Isolamento

- [ ] PostgreSQL — acesso público DESABILITADO
- [ ] Azure OpenAI — acesso público DESABILITADO
- [ ] Blob Storage — acesso público DESABILITADO
- [ ] NSGs configurados em todas as subnets
- [ ] Frontend com restrição de IP ou ingress interno
- [ ] Viewer de PDF redesenhado (proxy ou Front Door)

### Monitoramento

- [ ] Application Insights habilitado no Container Apps
- [ ] Log Analytics Workspace configurado
- [ ] Alertas de erro configurados (falhas de auth, erros 5xx)
- [ ] Budget alerts atualizados para custo de produção

### Backup e Recuperação

- [ ] Backup automático do PostgreSQL habilitado (7-35 dias retenção)
- [ ] Blob Storage com soft delete habilitado (proteção contra exclusão acidental)
- [ ] Procedimento documentado para restore

### Compliance e Auditoria

- [ ] Logs de acesso ao Blob Storage habilitados
- [ ] Logs de queries no PostgreSQL habilitados
- [ ] Registro de quem acessou qual documento e quando
- [ ] Política de retenção de logs definida com a Kyotech

---

## Ordem de Execução Recomendada

```
Etapa 1 — Autenticação de produção .......... (1 dia)
Etapa 2 — Fechar PostgreSQL ................ (30 min)
Etapa 3 — Fechar Azure OpenAI .............. (10 min)
Etapa 4 — Fechar Blob Storage .............. (10 min)
Etapa 5 — Configurar NSGs .................. (1 hora)
Etapa 7 — Restrição de IP no frontend ...... (30 min)
Etapa 8 — Proxy de PDF no backend .......... (2 horas)
Etapa 6 — Azure Firewall ................... (Fase 3, se necessário)
```

**Tempo total estimado:** 1-2 dias úteis (excluindo Firewall).

Após completar as etapas 1-5, 7 e 8, o ambiente está seguro para receber documentos confidenciais. Validar todo o fluxo (upload → chat → citação → PDF) antes de iniciar a carga de manuais reais.

---

*HaruCode © 2026 — Documento de uso interno*
*Última atualização: 27/02/2026*