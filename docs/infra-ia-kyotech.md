# Infraestrutura de IA -- Kyotoec

**Documento de Consolidação Técnica (MVP + Roadmap)**\
**Empresa:** HaruCode\
**Data:** 25/02/2026

------------------------------------------------------------------------

# 1. Contexto Geral

A Kyotoec necessita de um sistema interno seguro baseado em IA para
permitir que técnicos consultem:

-   Manuais técnicos
-   Informativos (boletins técnicos, atualizações, service bulletins)
-   Documentação confidencial fornecida pela Fujifilm

## Restrições Críticas

-   Documentos confidenciais (não podem vazar)
-   Sem acesso público à internet (ambiente isolado)
-   Autenticação corporativa obrigatória
-   Respostas devem citar fonte (documento + página)
-   PDFs majoritariamente em inglês (alguns em japonês)
-   Comunicação com técnicos em português

------------------------------------------------------------------------

# 2. Objetivo do MVP

Construir um sistema interno com:

-   Autenticação corporativa (Clerk)
-   Upload manual assistido de PDFs
-   Versionamento baseado em data de publicação
-   Indexação vetorial (PostgreSQL + pgvector)
-   Chat RAG em português
-   Citação rastreável de fontes
-   Visualizador interno abrindo diretamente na página citada

------------------------------------------------------------------------

# 3. Arquitetura Técnica (Azure)

## Componentes

### Frontend

-   Aplicação web (React/Next.js ou equivalente)
-   Login via Clerk
-   Interface de Chat + Biblioteca de Documentos
-   Viewer interno de PDF

### Backend API

-   Orquestração RAG
-   Controle de autenticação/autorização
-   Gestão de uploads
-   Controle de versionamento
-   Logs e auditoria

### IA

-   Azure OpenAI (Private Endpoint)
-   Uso para:
    -   Query rewriting
    -   Classificação Manual vs Informativo
    -   Geração de resposta final

### Banco de Dados

-   Azure PostgreSQL Flexible Server
-   Extensão pgvector

### Armazenamento

-   Azure Blob Storage (privado)
-   PDFs versionados

### Rede

-   VNet isolada
-   Private Endpoints
-   Sem acesso público
-   Firewall com bloqueio de egress

------------------------------------------------------------------------

# 4. Modelo de Dados (MVP)

## Tabela: equipments

-   equipment_key
-   display_name
-   aliases

## Tabela: documents

-   id
-   doc_type (manual \| informativo)
-   equipment_key
-   created_at

## Tabela: document_versions

-   id
-   document_id
-   published_date (OBRIGATÓRIO)
-   source_hash
-   source_filename
-   ingested_at
-   storage_path

Regra: versão válida = maior published_date por document_id.

## Tabela: chunks

-   document_version_id
-   page_number
-   content
-   embedding

------------------------------------------------------------------------

# 5. Estratégia de Versionamento

Problema identificado: - Códigos da Fujifilm não seguem padrão - Única
referência confiável: data de publicação

Solução: - Data obrigatória no upload - Extração automática +
confirmação manual - Sempre priorizar versão mais recente - Versões
antigas permanecem armazenadas (não excluídas no MVP)

------------------------------------------------------------------------

# 6. Fluxo de Upload

1.  Gerente baixa PDFs do portal Fujifilm
2.  Upload em lote no sistema
3.  Sistema:
    -   Calcula hash
    -   Extrai texto
    -   Detecta equipamento
    -   Solicita confirmação de equipamento e data
    -   Gera embeddings
    -   Armazena versão
4.  Documento fica disponível para consulta

------------------------------------------------------------------------

# 7. Fluxo RAG

1.  Técnico pergunta em português
2.  Sistema reescreve consulta
3.  Router identifica Manual ou Informativo
4.  Busca híbrida (vetorial + textual)
5.  Filtra apenas versões atuais
6.  Geração da resposta em português
7.  Citações incluem:
    -   Documento
    -   Versão/Data
    -   Página

------------------------------------------------------------------------

# 8. Viewer Interno

-   PDF armazenado privadamente
-   URL assinada temporária
-   Abertura direta na página citada (#page=)
-   Possibilidade futura de watermark

------------------------------------------------------------------------

# 9. Segurança

-   Sem endpoints públicos
-   Private endpoints para todos serviços
-   Blob privado
-   Controle RBAC
-   Logs de consulta e upload
-   Proteção contra prompt injection
-   Limitação de trechos retornados

------------------------------------------------------------------------

# 10. Custos Estimados (Estrutura)

## Custos Variáveis

-   Tokens Azure OpenAI
-   Embeddings
-   OCR (se necessário no futuro)

## Custos Fixos

-   PostgreSQL
-   Storage
-   App Service/Container
-   Firewall

## Modelo de Cobrança Sugerido

-   Setup inicial (implantação)
-   Mensalidade fixa (infra + suporte)
-   Pacote de consultas/mês
-   Cobrança adicional por uso excedente

------------------------------------------------------------------------

# 11. Roadmap e Prazos

## Fase 0 -- Descoberta (3--7 dias úteis)

-   Validação de políticas
-   Confirmação de fluxo de documentos

## Fase 1 -- MVP Funcional (2--4 semanas)

-   Login
-   Upload
-   Indexação
-   Chat com citações
-   Viewer interno

## Fase 2 -- Robustez Operacional (2--4 semanas)

-   Versionamento refinado
-   Melhorias de ranking
-   Dashboard simples
-   Hardening completo da rede

## Fase 3 -- Evolução Contínua (4+ semanas)

-   Métricas de uso
-   Feedback loop
-   OCR avançado (se necessário)
-   Ajustes finos de qualidade

------------------------------------------------------------------------

# 12. Decisões Estratégicas Tomadas

✔ Versionamento baseado em data\
✔ Upload manual assistido no MVP\
✔ Sempre priorizar versão mais recente\
✔ Não excluir versões antigas inicialmente\
✔ Viewer interno para eliminar retrabalho do técnico\
✔ Separação lógica entre Manual e Informativo\
✔ Ambiente isolado na Azure

------------------------------------------------------------------------

# 13. Conclusão

O MVP proposto entrega:

-   Segurança adequada
-   Rastreabilidade
-   Controle de versões
-   Redução de tempo operacional dos técnicos
-   Base sólida para evolução futura

Arquitetura escalável, segura e alinhada ao orçamento inicial com
créditos Azure disponíveis.

------------------------------------------------------------------------

**Fim do Documento**
