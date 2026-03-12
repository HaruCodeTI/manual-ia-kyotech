# Kyotech AI — Guia de Demonstração

## Sobre o Sistema

O **Kyotech AI** é um assistente inteligente que responde perguntas sobre manuais técnicos de equipamentos. Ele utiliza inteligência artificial (RAG — Retrieval-Augmented Generation) para buscar informações nos documentos indexados e gerar respostas precisas com citações das fontes originais.

### Como funciona

1. **Upload** — Manuais em PDF são enviados ao sistema e processados automaticamente
2. **Indexação** — O conteúdo é extraído, dividido em trechos e indexado com vetores semânticos
3. **Consulta** — O usuário faz uma pergunta em linguagem natural
4. **Resposta** — A IA busca nos documentos, encontra os trechos relevantes e gera uma resposta com citações `[Fonte N]`
5. **Verificação** — O usuário pode clicar nas citações para ver o trecho original do documento

---

## Acesso

- **URL:** https://kyotech-ai.harucode.com.br
- **Login:** Utilize as credenciais fornecidas (autenticação via Clerk)

---

## Equipamentos Disponíveis para Teste

O sistema está carregado com manuais técnicos de equipamentos Xerox (mesma família tecnológica dos equipamentos Fujifilm/Fuji Xerox). Na versão final, estes serão substituídos pelos manuais reais da Kyotech/Fujifilm.

| Equipamento | Tipo | Conteúdo |
|-------------|------|----------|
| **Xerox AltaLink C8030/C8045/C8055/C8070** | MFP Color | Manual do usuário — impressão, cópia, scan, manutenção, troubleshooting |
| **Xerox AltaLink B8100/C8100 Series** | MFP Enterprise | Guia do administrador — configuração de rede, segurança, políticas |
| **Xerox VersaLink C405** | MFP Color Compacta | Manual completo — operação, manutenção, resolução de problemas |
| **Xerox VersaLink C7000** | Impressora Color | Manual do usuário — impressão, manutenção, troubleshooting |
| **Xerox VersaLink B605/B615** | MFP Mono | Manual do usuário — operação, manutenção, diagnóstico |
| **Xerox WorkCentre 6515** | MFP Color | Manual completo — fax, scan, cópia, manutenção |

---

## Perguntas Sugeridas para Teste

### Manutenção e Limpeza

Estas perguntas testam a capacidade do sistema de encontrar procedimentos técnicos detalhados:

1. **"How do I clean the printhead lenses on the AltaLink C80XX?"**
   - Deve retornar procedimento passo a passo de limpeza das lentes

2. **"What is the maintenance procedure for cleaning the scanner glass?"**
   - Deve encontrar instruções de limpeza do vidro do scanner

3. **"How to clean the document feed rollers?"**
   - Deve retornar procedimento de limpeza dos rolos do alimentador

4. **"What are the routine maintenance items for the VersaLink C7000?"**
   - Deve listar itens de manutenção rotineira (toner, drum, fuser, etc.)

5. **"How do I clean the color toner density sensor on the VersaLink C405?"**
   - Deve retornar procedimento específico de limpeza do sensor

### Troubleshooting e Resolução de Problemas

6. **"The printer is showing paper jam errors, how do I clear them?"**
   - Deve retornar locais comuns de atolamento e como desobstruir

7. **"How to fix print quality problems like streaks or faded prints?"**
   - Deve encontrar seção de qualidade de impressão com diagnóstico

8. **"What should I do if the printer is not connecting to the network?"**
   - Deve retornar passos de troubleshooting de rede

9. **"The automatic duplex printing is not working, how to troubleshoot?"**
   - Deve encontrar seção específica de problemas com impressão frente/verso

10. **"How do I reset the printer to factory defaults?"**
    - Deve retornar procedimento de reset para configurações de fábrica

### Configuração e Administração

11. **"How to configure email scanning on the WorkCentre 6515?"**
    - Deve encontrar configuração de scan-to-email

12. **"What are the steps to set up the printer on a wireless network?"**
    - Deve retornar procedimento de configuração Wi-Fi

13. **"How to configure secure printing with PIN?"**
    - Deve encontrar configuração de impressão segura

14. **"How do I set up the fax function on the WorkCentre 6515?"**
    - Deve retornar configuração de fax

15. **"What are the default administrator credentials for the Embedded Web Server?"**
    - Deve encontrar credenciais padrão de acesso administrativo

### Perguntas em Português

O sistema também responde em português (internamente traduz a busca para inglês):

16. **"Como faço para trocar o toner da VersaLink C405?"**
17. **"Quais são os procedimentos de segurança ao fazer manutenção?"**
18. **"Como configurar a impressora na rede?"**
19. **"O que fazer quando aparece erro de atolamento de papel?"**
20. **"Como limpar o interior da impressora?"**

---

## Funcionalidades para Demonstrar

### 1. Chat com IA
- Acesse a tela principal de chat
- Faça perguntas da lista acima
- Observe as citações `[Fonte N]` nas respostas
- Clique nas citações para ver o trecho original do documento

### 2. Filtro por Equipamento
- No chat, selecione um equipamento específico para filtrar as respostas
- Útil quando o técnico sabe em qual equipamento está trabalhando

### 3. Upload de Documentos
- Acesse a página de upload
- Demonstre o envio de um novo PDF
- O sistema processa automaticamente: extrai texto, cria chunks, gera embeddings

### 4. Visualizador Seguro de PDFs
- Os documentos são visualizados como imagens (PNG) com marca d'água
- Não é possível baixar o PDF original — proteção de propriedade intelectual

### 5. Estatísticas
- Acesse `/stats` para ver totais de equipamentos, documentos e chunks indexados

---

## Diferenciais Técnicos

| Característica | Detalhe |
|---------------|---------|
| **Busca Híbrida** | Combina busca semântica (70%) com busca textual (30%) para máxima precisão |
| **Citações com Fonte** | Toda resposta inclui referências ao documento e página original |
| **Multilíngue** | Perguntas em português são traduzidas internamente para busca em manuais em inglês |
| **Segurança** | Autenticação via Clerk, PDFs protegidos com marca d'água, RBAC por perfil |
| **Escalável** | Infraestrutura Azure com auto-scaling, suporta desde 10 até 1000+ usuários |

---

## Próximos Passos (após validação)

1. **Substituir manuais de teste** pelos manuais reais Fujifilm/Kyotech
2. **Ajustar qualidade das respostas** com base no feedback dos técnicos
3. **Hardening de segurança** — fechamento de Private Endpoints na rede Azure
4. **Dashboard de métricas** — acompanhamento de uso e perguntas mais frequentes
5. **Treinamento** dos técnicos para uso no dia a dia

---

*Documento gerado em Março/2026 — HaruCode*
