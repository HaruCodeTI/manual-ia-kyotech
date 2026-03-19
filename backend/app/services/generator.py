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

DIAGNOSTIC_SYSTEM_PROMPT = """Você é o assistente técnico da Kyotech, especializado em diagnóstico de equipamentos Fujifilm.
O técnico relatou múltiplos sintomas. Analise cada um separadamente antes de sugerir causas.

PERSONALIDADE:
- Tom profissional mas acolhedor — trate o técnico como um colega
- Seja direto e estruturado — diagnósticos precisam de clareza

REGRAS OBRIGATÓRIAS:
1. Responda SEMPRE em português brasileiro
2. Use APENAS as informações dos trechos fornecidos — NUNCA invente
3. Para cada afirmação, cite a fonte usando EXATAMENTE o formato [Fonte N] com colchetes
4. Se a informação não está nos trechos, diga explicitamente
5. Se houver conflito entre fontes, mencione ambas versões e indique a mais recente

FORMATO OBRIGATÓRIO DA RESPOSTA:
## Análise dos Sintomas
[Aborde cada sintoma individualmente com citações [Fonte N]]

## Possíveis Causas
[Causas em comum entre os sintomas, ou causas independentes com citações [Fonte N]]

## Próximos Passos
[Procedimentos em ordem de prioridade com citações [Fonte N]]

NÃO liste as fontes ao final — o sistema exibe as fontes automaticamente."""

COMPARISON_SYSTEM_PROMPT = """Você é o assistente técnico da Kyotech, especializado em equipamentos de endoscopia Fujifilm.
O técnico quer entender o que mudou entre versões de um documento técnico.

PERSONALIDADE:
- Tom profissional mas acolhedor — trate o técnico como um colega
- Seja direto e estruturado — comparações precisam de clareza

REGRAS OBRIGATÓRIAS:
1. Responda SEMPRE em português brasileiro
2. Use APENAS as informações dos trechos e do diff fornecidos — NUNCA invente
3. Para cada afirmação, cite a fonte usando EXATAMENTE o formato [Fonte N]
4. Se não houver diferenças relevantes, diga isso claramente

FORMATO OBRIGATÓRIO DA RESPOSTA:
## Diferenças entre versões ({version_old} → {version_new})
[Liste cada mudança identificada com citações [Fonte N]]

## Resumo
[1-2 frases resumindo o impacto das mudanças para o técnico]

NÃO liste as fontes ao final — o sistema exibe as fontes automaticamente."""


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


def build_clarification_from_weak_results(question: str) -> str:
    """
    Retorna pergunta de clarificação quando resultados RAG têm score fraco.
    Determinístico — não chama LLM.
    """
    return (
        "Não encontrei informações suficientemente precisas para responder com confiança. "
        "Poderia fornecer mais detalhes? Por exemplo: qual equipamento, "
        "código de erro exibido, ou em qual etapa do processo ocorre o problema?"
    )


def build_diff_context(version_diff) -> str:
    """Formata o VersionDiff como texto para injetar no contexto do LLM."""
    if not version_diff or not version_diff.has_changes:
        return ""
    lines = [f"DIFERENÇAS DETECTADAS ({version_diff.version_old} → {version_diff.version_new}):"]
    for item in version_diff.diff_items:
        if item.change_type == "modified":
            lines.append(f"- MODIFICADO — {item.topic}: era '{item.old_value}', agora é '{item.new_value}'")
        elif item.change_type == "added":
            lines.append(f"- ADICIONADO — {item.topic}: '{item.new_value}'")
        elif item.change_type == "removed":
            lines.append(f"- REMOVIDO — {item.topic}: era '{item.old_value}'")
    return "\n".join(lines)


@dataclass
class Citation:
    source_index: int
    source_filename: str
    page_number: int
    equipment_key: str
    doc_type: str
    published_date: str
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
    diagnostic_mode: bool = False,
    version_diff=None,           # Optional[VersionDiff] — sem import explícito para evitar circular
    is_comparison_query: bool = False,
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

    if version_diff and version_diff.has_changes:
        diff_text = build_diff_context(version_diff)
        context = f"{diff_text}\n\n{context}"

    if is_comparison_query and version_diff and version_diff.has_changes:
        system_prompt = COMPARISON_SYSTEM_PROMPT.format(
            version_old=version_diff.version_old,
            version_new=version_diff.version_new,
        )
    elif diagnostic_mode:
        system_prompt = DIAGNOSTIC_SYSTEM_PROMPT
    else:
        system_prompt = SYSTEM_PROMPT

    max_tokens = 2500 if (is_comparison_query or diagnostic_mode) else 1500
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

    if history_summary:
        messages.append({
            "role": "system",
            "content": f"Resumo do contexto anterior:\n{history_summary}",
        })

    if history_messages:
        messages.extend(history_messages)

    user_content = f"Pergunta do técnico: {question}\n\nTrechos encontrados:\n\n{context}"
    if version_diff and version_diff.has_changes and not is_comparison_query:
        user_content += "\n\nNota: Foram detectadas diferenças entre versões do documento acima. Integre essas informações na resposta com citações [Fonte N]."
    messages.append({"role": "user", "content": user_content})

    client = get_openai_client()
    response = await client.chat.completions.create(
        model=settings.azure_openai_chat_deployment,
        messages=messages,
        temperature=0.2,
        max_tokens=max_tokens,
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
