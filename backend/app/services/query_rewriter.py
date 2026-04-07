"""
Kyotech AI — Query Rewriting
Conforme Seção 7: reescreve consulta do técnico (PT) para inglês técnico,
melhorando a busca contra manuais em inglês da Fujifilm.

Usa gpt-4o-mini (barato e rápido) para:
1. Traduzir PT → EN
2. Expandir termos técnicos
3. Classificar se é Manual ou Informativo
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from app.services.embedder import get_openai_client
from app.core.config import settings

logger = logging.getLogger(__name__)

REWRITE_PROMPT = """You are a technical assistant for Fujifilm endoscopy equipment.
Your job is to rewrite a technician's question (in Portuguese) into an optimized English search query.

Rules:
1. Translate to English
2. Use technical terms that would appear in Fujifilm service manuals
3. Keep the query focused and specific (max 2-3 sentences)
4. Classify the query as "manual" (procedures, specs, parts) or "informativo" (bulletins, updates, known issues)
5. If the question mentions a specific equipment model, extract it
6. Determine if the question needs clarification before searching.
   Set needs_clarification to true ONLY if ALL of these apply:
   - The question is too vague to produce any useful search (e.g. just "help" or "problem")
   - The conversation history does NOT already provide the missing context
   IMPORTANT — set needs_clarification to FALSE in these cases:
   - The user says "any", "all", "qualquer", "qualquer um", "todos", "both" when asked about equipment — this means search across ALL equipment
   - The conversation history already contains a clarification question from you — do NOT ask again, just search with what you have
   - The question is specific enough to search even without an equipment model (e.g. error codes, part numbers, general procedures)
   - The user is clearly asking a general question that applies to multiple equipment models
   When in doubt, prefer searching over asking for clarification.
7. If needs_clarification is true, write a short clarification question in Brazilian Portuguese.
   Be specific: ask for the missing information (equipment model, error code, symptom details).
   Keep it under 20 words. Example: "Poderia descrever melhor o problema ou informar o código de erro?"
8. Determine if this is a version comparison query.
   Set is_comparison_query to true if the technician asks to compare versions,
   asks what changed between versions, asks about updates or differences in a document.
   Keywords: "o que mudou", "compara", "diferença entre versões", "versão mais nova",
   "atualização do manual", "nova versão", "changed", "what's new".
9. Determine if this is a cross-document search query.
   Set is_document_search to true if the technician wants to know WHICH documents or manuals
   mention, cite, or contain a specific term — typically a Part Number (PN), part code, or component name.
   Keywords: "quais documentos", "quais manuais", "em quais manuais", "algum manual cita",
   "onde aparece", "quais arquivos mencionam", "which documents", "which manuals mention".
   This is different from a regular question — the user wants a LIST of documents, not a prose answer.

Respond ONLY with this JSON format, no markdown:
{"query_en": "...", "doc_type": "manual" or "informativo" or "both", "equipment_hint": "model name or null", "needs_clarification": false, "clarification_question": null, "is_comparison_query": false, "is_document_search": false}"""


@dataclass
class RewrittenQuery:
    original: str
    query_en: str
    doc_type: Optional[str]  # "manual", "informativo", or "both"
    equipment_hint: Optional[str]
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    is_comparison_query: bool = False
    is_document_search: bool = False


async def rewrite_query(
    question: str,
    conversation_context: Optional[str] = None,
) -> RewrittenQuery:
    """
    Reescreve a pergunta do técnico para busca otimizada.

    Input: "Como trocar o rolo de pressão da Frontier 780?"
    Output: RewrittenQuery(
        query_en="How to replace pressure roller Frontier 780",
        doc_type="manual",
        equipment_hint="frontier-780"
    )

    Se conversation_context for fornecido, é injetado no prompt para que o LLM
    possa resolver referências ao histórico da conversa (ex: "e esse modelo?").
    """
    client = get_openai_client()

    if conversation_context:
        user_content = (
            f"Previous conversation context:\n{conversation_context}\n\n"
            f"Current question: {question}"
        )
    else:
        user_content = question

    response = await client.chat.completions.create(
        model=settings.azure_openai_mini_deployment,
        messages=[
            {"role": "system", "content": REWRITE_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        max_tokens=300,
    )

    raw = response.choices[0].message.content.strip()
    logger.info(f"Query rewrite: '{question}' → {raw}")

    try:
        parsed = json.loads(raw)
        doc_type = parsed.get("doc_type")
        if doc_type == "both":
            doc_type = None  # busca em todos

        equipment = parsed.get("equipment_hint")
        if equipment and equipment.lower() in ("null", "none", ""):
            equipment = None
        if equipment:
            equipment = equipment.lower().replace(" ", "-")

        return RewrittenQuery(
            original=question,
            query_en=parsed.get("query_en", question),
            doc_type=doc_type,
            equipment_hint=equipment,
            needs_clarification=parsed.get("needs_clarification", False),
            clarification_question=parsed.get("clarification_question"),
            is_comparison_query=parsed.get("is_comparison_query", False),
            is_document_search=parsed.get("is_document_search", False),
        )
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Falha no parse do rewrite, usando query original: {e}")
        return RewrittenQuery(
            original=question,
            query_en=question,
            doc_type=None,
            equipment_hint=None,
        )
