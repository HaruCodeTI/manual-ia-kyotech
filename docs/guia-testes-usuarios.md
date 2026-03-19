# Guia de Testes — Kyotech IA
**Data:** 2026-03-19 | **Versão:** 1.0

Este guia cobre os cenários de teste das funcionalidades implementadas até hoje. Use os PDFs da pasta `kyotech-test-pdfs` para fazer os uploads antes de iniciar os testes.

---

## Pré-requisito: Upload dos Documentos

Antes de qualquer teste, faça o upload dos 10 PDFs de teste via a tela de Upload da plataforma.

**Documentos disponíveis:**

| Arquivo | Equipamento | Tipo | Idioma |
|---|---|---|---|
| `manual_fuji-x100_manutencao.pdf` | fuji-x100 | Manual | PT-BR |
| `manual_fuji-gfx100_operation.pdf` | fuji-gfx100 | Manual | EN |
| `manual_fuji-xh2s_video.pdf` | fuji-xh2s | Manual | EN |
| `manual_gfx50s-ii_medium-format.pdf` | fuji-gfx50s | Manual | EN |
| `manual_instax-mini12_tecnico.pdf` | instax-mini12 | Manual | PT-BR |
| `manual_instax-wide300_reparo.pdf` | instax-wide300 | Manual | PT-BR |
| `informativo_alerta-sensor-x-pro3.pdf` | fuji-xpro3 | Informativo | PT-BR |
| `informativo_atualizacao-firmware-xe4.pdf` | fuji-xe4 | Informativo | PT-BR |
| `informativo_battery-recall-np-w235.pdf` | fuji-battery | Informativo | EN |
| `informativo_lens-mount-advisory-xt5.pdf` | fuji-xt5 | Informativo | EN |

> **Dica:** Use o upload em lote (até 10 arquivos de uma vez) — veja o Cenário 7.

---

## Cenário 1 — Pergunta Técnica Direta

**O que testa:** busca RAG básica, resposta com citações

**Como fazer:** Abra o chat e faça perguntas técnicas objetivas.

**Perguntas para testar:**

```
Como faço a limpeza do sensor do X100VI?
```
> Esperado: procedimento de 4 passos com swab Eclipse, referência à página do manual, citação [Fonte 1]

```
Quais ferramentas são necessárias para manutenção do X100VI?
```
> Esperado: lista com chave Philips #0 e #1, torx T4 e T6, pinça antiestática, multímetro, soprador

```
Como calibrar o autofoco do GFX100S II?
```
> Esperado: 4 passos via FujiServ Toolkit, citação do manual

```
Quando devo substituir o módulo SSD de gravação do X-H2S?
```
> Esperado: 3 critérios (velocidade < 400MB/s, setores > 50, temperatura > 65°C)

```
Qual o procedimento para substituição dos roletes de revelação da Instax Wide 300?
```
> Esperado: 4 passos de substituição, intervalo de 5000 fotografias

**O que observar:**
- Resposta em português mesmo para documentos em inglês
- Citações `[Fonte N]` inline no texto
- Link clicável para abrir o PDF na página correta

---

## Cenário 2 — Consulta a Informativos e Alertas

**O que testa:** busca em informativos técnicos, informações de campanha/recall

**Perguntas para testar:**

```
Há algum alerta para o X-Pro3?
```
> Esperado: alerta de falha no módulo do sensor, números de série 84A10000 a 84A15999, código ERR-SEN-07, prazo de 60 dias, referência à campanha SEN-FIX-2025-001

```
O que mudou no firmware 3.10 do X-E4?
```
> Esperado: 3 correções (travamento com lente MK-X, Bluetooth iOS 17+, cálculo de exposição) e 3 melhorias (reconhecimento facial +30%, rastreamento de olhos, perfil Eterna Bleach Bypass II)

```
Como instalar o firmware 3.10 no X-E4?
```
> Esperado: 4 passos (download, copiar FW_X-E4_0310.DAT para SD, Menu > Setup > Versão do Usuário, aguardar 4 minutos)

```
Existe algum recall de bateria Fujifilm?
```
> Esperado: recall da NP-W235 fabricadas entre jan-mar 2024, códigos 2401XX a 2403XX, risco de curto-circuito

```
Qual o problema reportado no X-T5 com a montagem de lentes?
```
> Esperado: mecanismo de trava, séries 23C30000 a 23C34999, lubrificação com Molykote DX Paste, campanha MT-ADV-2024-012

---

## Cenário 3 — Diagnóstico Multi-Sintoma (IA-89)

**O que testa:** o bot detecta múltiplos sintomas e analisa cada um separadamente antes de sugerir causas

**Como reconhecer que ativou:** a resposta virá estruturada em três seções: *Análise dos Sintomas*, *Possíveis Causas* e *Próximos Passos*

**Perguntas para testar:**

```
Meu X-Pro3 está apresentando linhas horizontais nas imagens RAW e ruído excessivo em ISO alto. O que pode ser?
```
> Esperado: resposta estruturada com análise de cada sintoma separada, referência ao alerta de sensor, código ERR-SEN-07, orientação para envio ao centro de serviço

```
A Instax Wide 300 está dando erro E01 e as fotos saem com cores irregulares. O que verifico primeiro?
```
> Esperado: análise separada do E01 (motor de transporte) e da cor irregular (roletes de revelação), passos para cada problema

```
O X-H2S desligou sozinho durante uma gravação longa e agora o SSD mostra lentidão. Como procedo?
```
> Esperado: análise de superaquecimento (ventilador, 10 min de resfriamento) + avaliação do SSD (SMART data via FujiServ)

**O que observar:**
- Seções claramente separadas na resposta
- Cada sintoma tratado individualmente
- Próximos passos em ordem de prioridade

---

## Cenário 4 — Memória de Conversa (IA-103)

**O que testa:** o bot lembra do contexto das mensagens anteriores na mesma sessão

**Como fazer:** use a mesma janela de chat sem recarregar a página

**Sequência de perguntas:**

1. Envie: `Estou trabalhando numa Instax Mini 12 com problema no sistema óptico`
2. Aguarde a resposta
3. Envie: `E se a transmissão de luz estiver abaixo do esperado, o que faço?`
   > Esperado: o bot entende que "transmissão de luz" se refere à Instax Mini 12 já mencionada, cita o limite de 85% medido com luxímetro, sugere substituição da lente

4. Envie: `Qual o valor correto para o fotoresistor?`
   > Esperado: responde sobre o LDR da Instax Mini 12 (8 a 12 kohm em 500 lux), sem precisar repetir o equipamento

**O que observar:**
- O bot não pede para repetir o equipamento a cada mensagem
- Contexto acumulado sem perder coerência

---

## Cenário 5 — Detecção de Ambiguidade / Clarificação (IA-104)

**O que testa:** quando a pergunta é vaga demais, o bot faz uma pergunta de volta em vez de inventar resposta

**Perguntas para testar:**

```
Como calibrar?
```
> Esperado: bot pergunta qual equipamento e qual tipo de calibração (autofoco, obturador, exposição?)

```
Qual o procedimento correto?
```
> Esperado: bot pede mais contexto — procedimento de quê, em qual equipamento

```
Tem algum alerta?
```
> Esperado: bot pergunta sobre qual equipamento ou tipo de alerta

**O que observar:**
- O bot NÃO tenta responder com informações genéricas
- A pergunta de clarificação é natural e específica
- Após responder à clarificação, o bot segue normalmente

---

## Cenário 6 — Comparação de Versões (último deploy)

**O que testa:** o bot detecta quando há versões diferentes do mesmo documento e compara o que mudou

**Pré-requisito especial:** este cenário requer que haja **duas versões do mesmo documento** na base. Os PDFs atuais de teste são todos da mesma data (2025-01-15) — para testar este cenário, faça o upload de uma versão revisada de um dos documentos com uma data diferente.

**Sugestão de preparação:**
1. Faça upload do `informativo_atualizacao-firmware-xe4.pdf` (versão 2025-01-15 já carregada)
2. Prepare uma cópia do arquivo com data 2024-07-01 e carregue também
3. Agora faça as perguntas abaixo

**Perguntas para testar (após ter 2 versões):**

```
O que mudou no informativo do firmware X-E4 entre as versões?
```
> Esperado: resposta com seção `## Diferenças entre versões (2024-07-01 → 2025-01-15)` listando o que foi adicionado, removido ou modificado

```
Compara as duas versões do manual do X-E4
```
> Esperado: mesmo formato acima, diff semântico (não diff de texto)

```
Houve alguma atualização nas informações do firmware X-E4?
```
> Esperado: bot detecta implicitamente que há múltiplas versões e integra as diferenças na resposta

**O que observar:**
- Seção `## Diferenças entre versões` presente quando perguntado explicitamente
- Itens classificados como ADICIONADO / REMOVIDO / MODIFICADO
- Quando a pergunta é implícita (não pede comparação diretamente), as diferenças aparecem integradas no texto

---

## Cenário 7 — Upload em Lote (IA-87)

**O que testa:** envio de múltiplos PDFs de uma só vez

**Como fazer:**
1. Acesse a tela de Upload
2. Arraste todos os 10 PDFs da pasta `kyotech-test-pdfs` de uma só vez
3. Não é necessário preencher equipamento — o campo é opcional

**O que observar:**
- Barra de progresso individual por arquivo
- Status de sucesso ou erro por arquivo
- Após conclusão, documentos aparecem na base e ficam consultáveis

---

## Cenário 8 — Feedback de Respostas (IA-88)

**O que testa:** avaliação de respostas com thumbs up/down

**Como fazer:**
1. Faça qualquer pergunta e aguarde a resposta
2. Clique no polegar para cima (👍) se a resposta foi útil
3. Faça uma segunda pergunta com resposta insatisfatória
4. Clique no polegar para baixo (👎)

**O que observar:**
- Botões visíveis em cada resposta do assistente
- Feedback registrado sem travar o fluxo da conversa
- Não é obrigatório dar feedback para continuar usando

---

## O Que Considerar como Sucesso

| Funcionalidade | Sinal de Sucesso |
|---|---|
| RAG básico | Resposta em PT-BR com citações `[Fonte N]` clicáveis |
| Informativos | Informações específicas do alerta/recall aparecem corretamente |
| Diagnóstico | Resposta com 3 seções estruturadas |
| Memória | Perguntas de follow-up sem repetir contexto |
| Clarificação | Bot faz pergunta de volta em vez de inventar |
| Comparação de versões | Seção de diferenças com ADICIONADO/REMOVIDO/MODIFICADO |
| Upload em lote | 10 arquivos processados com barra de progresso |
| Feedback | Ícones respondem ao clique |

## O Que Anotar se Algo Falhar

Para cada problema encontrado, anote:
- A pergunta exata que foi feita
- O equipamento selecionado (se usou filtro)
- O que o bot respondeu
- O que era esperado

---

## Dúvidas Frequentes

**O bot respondeu em inglês** — normal para documentos em inglês (GFX100, X-H2S, GFX50S, X-T5 Lens Mount, Battery Recall). O bot responde sempre em PT-BR mas pode citar trechos do original.

**Não apareceu citação** — tente reformular a pergunta sendo mais específico sobre o equipamento.

**Bot disse "não encontrei informações"** — verifique se o PDF correspondente foi carregado com sucesso na tela de Upload.
