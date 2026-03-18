# Advanced RAG — Diagnóstico Multi-Problema

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que o técnico descreva múltiplos problemas em uma única pergunta (ex: "Estou com os problemas X e Y, o que pode ser?") e receber uma resposta diagnóstica completa que aborda cada sintoma individualmente antes de sugerir causas comuns.

**Architecture:** Novo serviço `diagnostic_analyzer.py` que usa gpt-4o-mini para decompor a pergunta em sub-problemas, executa `hybrid_search` para cada sub-problema em paralelo, funde e ranqueia os resultados, e usa um prompt especializado em diagnóstico no `generator.py`. O endpoint `/chat/ask` detecta automaticamente perguntas diagnósticas (múltiplos problemas) e usa o novo pipeline. O modo diagnóstico é transparente ao usuário — a resposta é mais detalhada, mas o formato é o mesmo.

**Tech Stack:** Azure OpenAI gpt-4o-mini (decomposição), asyncio.gather (buscas paralelas), FastAPI (sem mudança de contrato), Python 3.9+.

**Tradeoff aceito pelo cliente:** Respostas diagnósticas são 2-3x mais lentas (3 chamadas OpenAI ao invés de 1) e mais caras (~3x mais tokens). Mas a qualidade para cenários complexos é significativamente melhor.

---

## Mapa de Arquivos

| Ação | Arquivo |
|---|---|
| Criar | `backend/app/services/diagnostic_analyzer.py` |
| Modificar | `backend/app/services/generator.py` |
| Modificar | `backend/app/api/chat.py` |
| Criar | `backend/tests/test_diagnostic.py` |

---

## Task 1: Serviço de Decomposição de Problemas

**Files:**
- Create: `backend/app/services/diagnostic_analyzer.py`

- [ ] **Step 1: Escrever o teste**

  Criar `backend/tests/test_diagnostic.py`:

  ```python
  # backend/tests/test_diagnostic.py
  import pytest
  from unittest.mock import patch, AsyncMock, MagicMock
  from app.services.diagnostic_analyzer import decompose_problems, is_diagnostic_query

  def test_is_diagnostic_query_positive():
      """Perguntas com múltiplos sintomas devem ser detectadas."""
      cases = [
          "Estou com os problemas X e Y no equipamento",
          "O equipamento está falhando e também tem barulho estranho",
          "Tenho dois problemas: não liga e faz barulho",
          "A imagem está distorcida e o papel está travando",
      ]
      for q in cases:
          assert is_diagnostic_query(q), f"Deveria ser diagnóstico: {q}"

  def test_is_diagnostic_query_negative():
      """Perguntas simples não devem ser detectadas como diagnóstico."""
      cases = [
          "Como trocar o rolo de pressão?",
          "Qual o torque do parafuso da tampa?",
          "O sistema não liga",
      ]
      for q in cases:
          assert not is_diagnostic_query(q), f"Não deveria ser diagnóstico: {q}"

  @pytest.mark.asyncio
  async def test_decompose_problems():
      """decompose_problems deve retornar lista de sub-problemas."""
      mock_response = MagicMock()
      mock_response.choices[0].message.content = '["problema X no motor", "problema Y no rolo"]'

      with patch("app.services.diagnostic_analyzer.get_openai_client") as mock_client:
          mock_instance = AsyncMock()
          mock_instance.chat.completions.create = AsyncMock(return_value=mock_response)
          mock_client.return_value = mock_instance

          result = await decompose_problems("Tenho problema X e problema Y")

          assert len(result) >= 1
          assert all(isinstance(p, str) for p in result)
  ```

- [ ] **Step 2: Rodar para ver falhar**

  ```bash
  cd backend && pytest tests/test_diagnostic.py -v
  ```

  Esperado: FAIL — módulo não existe

- [ ] **Step 3: Implementar `diagnostic_analyzer.py`**

  ```python
  """
  Kyotech AI — Analisador de Perguntas Diagnósticas

  Decompõe perguntas com múltiplos problemas em sub-queries independentes,
  permitindo busca especializada por sintoma antes da síntese final.
  """
  from __future__ import annotations

  import json
  import logging
  import re
  from dataclasses import dataclass
  from typing import List

  from app.services.embedder import get_openai_client
  from app.core.config import settings

  logger = logging.getLogger(__name__)

  # Padrões que indicam múltiplos problemas em uma pergunta
  _MULTI_PROBLEM_PATTERNS = [
      r'\be\s+(também|além|mais)\b',          # "e também", "e além disso"
      r'\bproblemas?\s+\w+\s+e\s+\w+',        # "problemas X e Y"
      r'\b(dois|dois|três|múltiplos)\s+problemas?\b',
      r'[:,]\s*(também|além disso|adicionalmente)',
      r'\bfalhando\b.{1,50}\btambém\b',
      r'\b(e|além disso|também)\b.{0,30}\b(problema|falha|erro|barulho|vibração)\b',
  ]

  _DECOMPOSE_PROMPT = """You are a technical assistant for Fujifilm endoscopy equipment.
  A technician has described MULTIPLE problems with their equipment.

  Your task: decompose the question into independent sub-problems, each focused on ONE symptom.
  Each sub-problem should be a self-contained search query in English.

  Rules:
  1. Return a JSON array of 2-4 strings
  2. Each string is a concise technical query for ONE symptom
  3. Preserve technical terms and model names
  4. If you can't find multiple distinct problems, return a single-item array

  Example input: "O equipamento não liga e também está fazendo barulho estranho no motor"
  Example output: ["equipment not powering on startup failure", "motor unusual noise vibration"]

  Respond ONLY with the JSON array, no markdown."""


  def is_diagnostic_query(question: str) -> bool:
      """
      Detecta se a pergunta contém múltiplos problemas.
      Heurística rápida — não usa LLM para evitar latência extra.
      """
      q = question.lower()
      return any(re.search(p, q) for p in _MULTI_PROBLEM_PATTERNS)


  async def decompose_problems(question: str) -> List[str]:
      """
      Decompõe uma pergunta multi-problema em sub-queries de busca.

      Input:  "Estou com problema X e também problema Y no equipamento"
      Output: ["technical query for problem X", "technical query for problem Y"]
      """
      client = get_openai_client()

      try:
          response = await client.chat.completions.create(
              model=settings.azure_openai_mini_deployment,
              messages=[
                  {"role": "system", "content": _DECOMPOSE_PROMPT},
                  {"role": "user", "content": question},
              ],
              temperature=0.1,
              max_tokens=300,
          )

          raw = response.choices[0].message.content.strip()
          logger.info(f"Decomposição de problemas: {raw}")

          parsed = json.loads(raw)
          if isinstance(parsed, list) and all(isinstance(p, str) for p in parsed):
              return parsed[:4]  # máximo 4 sub-problemas
          return [question]

      except Exception as e:
          logger.warning(f"Falha na decomposição, usando query original: {e}")
          return [question]
  ```

- [ ] **Step 4: Rodar os testes**

  ```bash
  pytest tests/test_diagnostic.py -v
  ```

  Esperado: todos PASS

- [ ] **Step 5: Commit**

  ```bash
  git add backend/app/services/diagnostic_analyzer.py backend/tests/test_diagnostic.py
  git commit -m "feat(rag): serviço de decomposição de perguntas multi-problema"
  ```

---

## Task 2: Prompt de Diagnóstico no Generator

**Files:**
- Modify: `backend/app/services/generator.py`

- [ ] **Step 1: Adicionar prompt especializado para diagnóstico**

  Em `generator.py`, após o `SYSTEM_PROMPT` existente, adicionar:

  ```python
  DIAGNOSTIC_SYSTEM_PROMPT = """Você é o assistente técnico da Kyotech, especializado em diagnóstico de equipamentos de endoscopia Fujifilm.
  O técnico descreveu MÚLTIPLOS problemas. Sua resposta deve ser um diagnóstico estruturado.

  PERSONALIDADE:
  - Tom profissional e empático — o técnico está com um equipamento com múltiplos problemas
  - Seja sistemático: aborde cada sintoma antes de propor causas comuns
  - Priorize as causas mais prováveis

  REGRAS OBRIGATÓRIAS:
  1. Responda SEMPRE em português brasileiro
  2. Use APENAS as informações dos trechos fornecidos — NUNCA invente
  3. Para cada afirmação, cite a fonte no formato [Fonte N]
  4. Se a informação não está nos trechos, diga claramente

  FORMATO OBRIGATÓRIO DA RESPOSTA:
  ## Análise dos Sintomas
  Para cada sintoma mencionado, uma breve análise baseada nos documentos.

  ## Possíveis Causas
  Causas prováveis que expliquem os sintomas em conjunto (se houver relação).

  ## Próximos Passos
  Procedimentos de diagnóstico sugeridos, em ordem de prioridade.

  ## Fontes
  Lista numerada das fontes referenciadas."""
  ```

- [ ] **Step 2: Adicionar parâmetro `diagnostic_mode` em `generate_response`**

  ```python
  async def generate_response(
      question: str,
      query_rewritten: str,
      search_results: List[SearchResult],
      diagnostic_mode: bool = False,  # novo parâmetro
  ) -> RAGResponse:
      # ...
      prompt = DIAGNOSTIC_SYSTEM_PROMPT if diagnostic_mode else SYSTEM_PROMPT

      client = get_openai_client()
      response = await client.chat.completions.create(
          model=settings.azure_openai_chat_deployment,
          messages=[
              {"role": "system", "content": prompt},
              {
                  "role": "user",
                  "content": f"Pergunta do técnico: {question}\n\n"
                             f"Trechos encontrados:\n\n{context}",
              },
          ],
          temperature=0.2,
          max_tokens=2500 if diagnostic_mode else 1500,  # mais tokens no diagnóstico
      )
      # ... resto sem mudança
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add backend/app/services/generator.py
  git commit -m "feat(generator): prompt especializado para diagnóstico multi-problema"
  ```

---

## Task 3: Integrar no Endpoint de Chat

**Files:**
- Modify: `backend/app/api/chat.py`

- [ ] **Step 1: Escrever o teste de integração diagnóstica**

  Em `backend/tests/test_diagnostic.py`, adicionar:

  ```python
  from unittest.mock import patch, AsyncMock, MagicMock
  from fastapi.testclient import TestClient
  from app.main import app

  client = TestClient(app)

  def test_diagnostic_query_uses_decomposition():
      """Pergunta com múltiplos problemas deve acionar decomposição."""
      with patch("app.api.chat.is_diagnostic_query", return_value=True) as mock_is_diag, \
           patch("app.api.chat.decompose_problems", new_callable=AsyncMock,
                 return_value=["problem A query", "problem B query"]) as mock_decomp, \
           patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]) as mock_search, \
           patch("app.api.chat.generate_response", new_callable=AsyncMock) as mock_gen, \
           patch("app.api.chat.chat_repository") as mock_repo, \
           patch("app.api.chat.rewrite_query", new_callable=AsyncMock) as mock_rewrite:

          mock_rewrite.return_value = MagicMock(
              query_en="problem query", doc_type=None, equipment_hint=None
          )
          mock_repo.create_session = AsyncMock(return_value="session-uuid")
          mock_repo.add_message = AsyncMock()
          mock_gen.return_value = MagicMock(
              answer="Diagnóstico...", citations=[], query_original="q",
              query_rewritten="q_en", total_sources=0,
              model_used="gpt-4o"
          )

          response = client.post(
              "/api/v1/chat/ask",
              json={"question": "Tenho problema X e também problema Y"},
              headers={"Authorization": "Bearer fake"},
          )

          # decompose_problems deve ter sido chamado
          mock_decomp.assert_called_once()
          # hybrid_search deve ter sido chamado para cada sub-problema
          assert mock_search.call_count >= 2
  ```

- [ ] **Step 2: Rodar para ver falhar**

  ```bash
  pytest tests/test_diagnostic.py::test_diagnostic_query_uses_decomposition -v
  ```

  Esperado: FAIL

- [ ] **Step 3: Modificar `chat.py` para usar o pipeline diagnóstico**

  Em `backend/app/api/chat.py`, modificar o endpoint `ask_question`:

  ```python
  from app.services.diagnostic_analyzer import is_diagnostic_query, decompose_problems
  import asyncio

  @router.post("/ask", response_model=ChatResponse)
  async def ask_question(
      request: ChatRequest,
      user: CurrentUser = Depends(get_current_user),
      db: AsyncSession = Depends(get_db),
  ):
      question = request.question.strip()
      logger.info(f"[{user.id}] Pergunta: {question}")

      # Resolver sessão (sem mudança)
      if request.session_id:
          session_id = UUID(request.session_id)
      else:
          title = question[:80] + ("…" if len(question) > 80 else "")
          session_id = await chat_repository.create_session(db, user.id, title)

      await chat_repository.add_message(db, session_id, "user", question)

      # Detectar modo diagnóstico
      diagnostic_mode = is_diagnostic_query(question)
      logger.info(f"Modo diagnóstico: {diagnostic_mode}")

      # Rewrite da query principal (sempre)
      rewritten = await rewrite_query(question)
      equipment_filter = request.equipment_filter or rewritten.equipment_hint

      if diagnostic_mode:
          # Decompor em sub-problemas e buscar em paralelo
          sub_queries = await decompose_problems(question)
          logger.info(f"Sub-problemas: {sub_queries}")

          search_tasks = [
              hybrid_search(
                  db=db,
                  query_en=sq,
                  query_original=question,
                  limit=5,  # menos por sub-query para não exceder contexto
                  doc_type=rewritten.doc_type,
                  equipment_key=equipment_filter,
              )
              for sq in sub_queries
          ]
          all_results_nested = await asyncio.gather(*search_tasks)

          # Fundir e deduplificar por chunk_id, mantendo melhor score
          seen: dict = {}
          for sub_results in all_results_nested:
              for r in sub_results:
                  if r.chunk_id not in seen or r.similarity > seen[r.chunk_id].similarity:
                      seen[r.chunk_id] = r

          results = sorted(seen.values(), key=lambda r: r.similarity, reverse=True)[:10]
      else:
          results = await hybrid_search(
              db=db,
              query_en=rewritten.query_en,
              query_original=question,
              limit=8,
              doc_type=rewritten.doc_type,
              equipment_key=equipment_filter,
          )

      logger.info(f"Resultados encontrados: {len(results)}")

      rag_response = await generate_response(
          question=question,
          query_rewritten=rewritten.query_en,
          search_results=results,
          diagnostic_mode=diagnostic_mode,
      )

      # ... resto do endpoint sem mudança (persistir resposta, retornar)
  ```

- [ ] **Step 4: Rodar todos os testes diagnósticos**

  ```bash
  pytest tests/test_diagnostic.py -v
  ```

  Esperado: todos PASS

- [ ] **Step 5: Testar manualmente no chat**

  Pergunta de teste: `"Estou tendo problemas com a imagem distorcida e também o equipamento está fazendo um barulho estranho durante o procedimento. O que pode ser?"`

  Verificar:
  - Resposta tem seções "Análise dos Sintomas", "Possíveis Causas", "Próximos Passos"
  - Citações presentes
  - Latência ~2-3x maior que pergunta simples (esperado)

- [ ] **Step 6: Commit final**

  ```bash
  git add backend/app/api/chat.py
  git commit -m "feat(chat): modo diagnóstico para perguntas com múltiplos problemas"
  ```

---

## Notas de Design

- **Detecção heurística:** `is_diagnostic_query` usa regex para evitar uma chamada LLM extra. Se a heurística gerar falsos positivos, o pior caso é uma resposta mais lenta e detalhada — comportamento aceitável.
- **Máximo 4 sub-problemas:** Limita custos e latência. Se o técnico descrever 5+ problemas, os mais importantes serão capturados.
- **Deduplicação por chunk_id:** Evita que o mesmo trecho apareça múltiplas vezes no contexto do LLM.
- **Custo estimado por pergunta diagnóstica:** ~3x mais tokens do que uma pergunta simples. Com gpt-4o e gpt-4o-mini, estima-se ~$0.05-0.15 por diagnóstico complexo.
- **Fallback:** Se `decompose_problems` falhar (ex: timeout da Azure OpenAI), o sistema cai de volta para o pipeline normal com a query original.
