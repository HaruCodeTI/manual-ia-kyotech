"""
Kyotech AI — Geração de Resposta com Citações
Conforme Seção 7: resposta em português com citações rastreáveis.

Cada citação inclui: documento, versão/data, página.
O técnico pode clicar na citação e abrir o PDF direto na página.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.services.embedder import get_openai_client
from app.services.search import SearchResult
from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é o assistente técnico da Kyotech, especializado em equipamentos de endoscopia Fujifilm.
Você ajuda técnicos de campo a encontrar informações em manuais e informativos técnicos.

PERSONALIDADE:
- Tom profissional mas acolhedor — trate o técnico como um colega
- Seja direto nas respostas, mas não robótico
- Use linguagem técnica quando necessário, mas explique termos complexos brevemente
- Se a pergunta for vaga, responda o melhor possível e sugira como refinar

REGRAS OBRIGATÓRIAS:
1. Responda SEMPRE em português brasileiro
2. Use APENAS as informações dos trechos fornecidos — NUNCA invente
3. Para cada afirmação, cite a fonte usando EXATAMENTE o formato [Fonte N] com colchetes — nunca escreva "Fonte N" sem colchetes
4. Se a informação não está nos trechos, diga: "Não encontrei essa informação nos documentos disponíveis. Tente reformular ou verifique se o manual foi carregado."
5. Se houver conflito entre fontes, mencione ambas versões e indique a mais recente

FORMATO DA RESPOSTA:
- Resposta clara e objetiva com citações [Fonte N] inline no texto
- NÃO liste as fontes ao final — o sistema exibe as fontes automaticamente"""


def build_context(results: List[SearchResult]) -> str:
    """Constrói o contexto dos trechos para o prompt."""
    context_parts = []
    for i, r in enumerate(results, 1):
        context_parts.append(
            f"[Fonte {i}] Arquivo: {r.source_filename} | "
            f"Página: {r.page_number} | "
            f"Tipo: {r.doc_type} | "
            f"Equipamento: {r.equipment_key} | "
            f"Data: {r.published_date}\n"
            f"Conteúdo:\n{r.content}\n"
        )
    return "\n---\n".join(context_parts)


@dataclass
class Citation:
    source_index: int
    source_filename: str
    page_number: int
    equipment_key: str
    doc_type: str
    published_date: str
    storage_path: str
    document_version_id: str = ""


@dataclass
class RAGResponse:
    answer: str
    citations: List[Citation]
    query_original: str
    query_rewritten: str
    total_sources: int
    model_used: str


async def generate_response(
    question: str,
    query_rewritten: str,
    search_results: List[SearchResult],
    history_messages: Optional[List[Dict[str, str]]] = None,
    history_summary: Optional[str] = None,
) -> RAGResponse:
    """
    Gera resposta em português com citações baseadas nos resultados da busca.
    
    Usa gpt-4o (mais capaz) para a resposta final ao técnico.
    """
    if not search_results:
        return RAGResponse(
            answer="Não encontrei informações relevantes nos documentos disponíveis. "
                   "Tente reformular a pergunta ou verifique se o documento foi carregado no sistema.",
            citations=[],
            query_original=question,
            query_rewritten=query_rewritten,
            total_sources=0,
            model_used=settings.azure_openai_chat_deployment,
        )

    context = build_context(search_results)

    messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history_summary:
        messages.append({
            "role": "system",
            "content": f"Resumo do contexto anterior:\n{history_summary}",
        })

    if history_messages:
        messages.extend(history_messages)

    messages.append({
        "role": "user",
        "content": (
            f"Pergunta do técnico: {question}\n\n"
            f"Trechos encontrados:\n\n{context}"
        ),
    })

    client = get_openai_client()
    response = await client.chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=messages,
        temperature=0.2,
        max_tokens=1500,
    )

    answer = response.choices[0].message.content.strip()

    referenced_indices = {int(m) for m in re.findall(r"\[Fonte (\d+)\]", answer)}

    citations = []
    for i, r in enumerate(search_results, 1):
        if i not in referenced_indices:
            continue
        citations.append(Citation(
            source_index=i,
            source_filename=r.source_filename,
            page_number=r.page_number,
            equipment_key=r.equipment_key,
            doc_type=r.doc_type,
            published_date=str(r.published_date),
            storage_path=r.storage_path,
            document_version_id=r.document_version_id,
        ))

    logger.info(
        f"Resposta gerada: {len(answer)} chars, {len(citations)} citações"
    )

    return RAGResponse(
        answer=answer,
        citations=citations,
        query_original=question,
        query_rewritten=query_rewritten,
        total_sources=len(search_results),
        model_used=settings.azure_openai_chat_deployment,
    )
