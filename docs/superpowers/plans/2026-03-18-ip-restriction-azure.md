# IP Restriction — Acesso Somente Pela Rede Kyotech

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restringir o acesso HTTP à aplicação (frontend + backend) exclusivamente ao(s) IP(s) públicos da Kyotech, bloqueando qualquer acesso externo via internet.

**Architecture:** Configuração de IP allow-list no nível do Azure Container Apps Ingress. O tráfego é bloqueado antes de chegar à aplicação, sem qualquer mudança de código. Todo acesso de fora do range autorizado recebe HTTP 403.

**Tech Stack:** Azure CLI (`az`), Azure Container Apps, opcionalmente Azure Portal.

---

## Pré-requisitos

- Azure CLI instalado e autenticado: `az login`
- Conhecer o nome do Container App Environment e do Resource Group: `rg-kyotech-ai`
- Obter o(s) IP(s) públicos da Kyotech com o cliente antes de executar
- Se o sistema ainda não está no Container Apps (desenvolvimento local), este plano serve como guia para quando for feito o deploy

---

## Task 1: Descobrir o IP Público da Kyotech

**Files:**
- Nenhum arquivo alterado — puro Azure CLI

- [ ] **Step 1: Peça ao responsável de TI da Kyotech o IP público da saída de internet deles**

  A forma mais simples é pedir para alguém na rede deles acessar: `https://whatismyip.com`
  Anote o IP no formato CIDR: ex. `200.123.45.67/32` (o `/32` significa IP único exato)

- [ ] **Step 2: Confirme o Resource Group e nome do Container App**

  ```bash
  az containerapp list --resource-group rg-kyotech-ai --output table
  ```

  Anote o nome do Container App do backend e do frontend (ex: `ca-kyotech-backend`, `ca-kyotech-frontend`)

- [ ] **Step 3: Verifique a configuração atual de ingress**

  ```bash
  az containerapp ingress show \
    --name ca-kyotech-backend \
    --resource-group rg-kyotech-ai
  ```

---

## Task 2: Aplicar IP Restriction no Backend (Container App)

**Files:**
- Nenhum arquivo alterado — puro Azure CLI

- [ ] **Step 1: Adicionar regra de allow para o IP da Kyotech**

  ```bash
  az containerapp ingress access-restriction set \
    --name ca-kyotech-backend \
    --resource-group rg-kyotech-ai \
    --rule-name "allow-kyotech" \
    --action Allow \
    --ip-address 200.123.45.67/32 \
    --description "Rede interna Kyotech"
  ```

  > Substitua `200.123.45.67/32` pelo IP real obtido no Task 1.

- [ ] **Step 2: Verificar se a regra foi aplicada**

  ```bash
  az containerapp ingress access-restriction list \
    --name ca-kyotech-backend \
    --resource-group rg-kyotech-ai \
    --output table
  ```

  Esperado: linha com `allow-kyotech | Allow | 200.123.45.67/32`

- [ ] **Step 3: Testar bloqueio de fora da rede Kyotech**

  De uma rede externa (ex: 4G do seu celular), acesse a URL pública do backend:
  ```
  curl -I https://<url-backend>/health
  ```
  Esperado: `HTTP/1.1 403 Forbidden`

- [ ] **Step 4: Confirmar que funciona dentro da rede Kyotech**

  Acesse de dentro da rede da Kyotech:
  ```
  curl -I https://<url-backend>/health
  ```
  Esperado: `HTTP/1.1 200 OK`

---

## Task 3: Aplicar IP Restriction no Frontend (Container App)

- [ ] **Step 1: Mesma regra para o Container App do frontend**

  ```bash
  az containerapp ingress access-restriction set \
    --name ca-kyotech-frontend \
    --resource-group rg-kyotech-ai \
    --rule-name "allow-kyotech" \
    --action Allow \
    --ip-address 200.123.45.67/32 \
    --description "Rede interna Kyotech"
  ```

- [ ] **Step 2: Testar frontend bloqueado externamente**

  De 4G: `curl -I https://<url-frontend>/`
  Esperado: `HTTP/1.1 403 Forbidden`

- [ ] **Step 3: Testar frontend acessível dentro da rede Kyotech**

  Esperado: a aplicação carrega normalmente

---

## Task 4: Adicionar IP da HaruCode (Acesso de Manutenção)

Para que a HaruCode consiga acessar a aplicação para manutenção e deploy sem precisar ir ao escritório da Kyotech:

- [ ] **Step 1: Adicionar regra para IP da HaruCode no backend e frontend**

  ```bash
  # Backend
  az containerapp ingress access-restriction set \
    --name ca-kyotech-backend \
    --resource-group rg-kyotech-ai \
    --rule-name "allow-harucode" \
    --action Allow \
    --ip-address <SEU-IP>/32 \
    --description "HaruCode manutencao"

  # Frontend
  az containerapp ingress access-restriction set \
    --name ca-kyotech-frontend \
    --resource-group rg-kyotech-ai \
    --rule-name "allow-harucode" \
    --action Allow \
    --ip-address <SEU-IP>/32 \
    --description "HaruCode manutencao"
  ```

- [ ] **Step 2: Confirmar ambas as regras**

  ```bash
  az containerapp ingress access-restriction list \
    --name ca-kyotech-backend \
    --resource-group rg-kyotech-ai \
    --output table
  ```

  Esperado: 2 linhas — `allow-kyotech` e `allow-harucode`

- [ ] **Step 3: Commit de documentação**

  ```bash
  git add docs/
  git commit -m "docs: documentar configuração de IP restriction Azure Container Apps"
  ```

---

## Notas Importantes

- **IP dinâmico:** Se a Kyotech tiver IP dinâmico (muda periodicamente), será necessário usar um range CIDR (ex: `200.123.45.0/24`) ou configurar um IP estático no roteador deles. Confirme com o TI da Kyotech.
- **VPN como alternativa:** Se a Kyotech tiver VPN corporativa, uma alternativa mais robusta seria integrar o Container Apps à VNet privada (já criada: `vnet-kyotech`) e usar a VPN para acesso. Isso é Fase 2.
- **Rollback:** Para remover uma regra:
  ```bash
  az containerapp ingress access-restriction remove \
    --name ca-kyotech-backend \
    --resource-group rg-kyotech-ai \
    --rule-name "allow-kyotech"
  ```
