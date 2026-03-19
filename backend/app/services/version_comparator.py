"""
Kyotech AI — Comparação Semântica de Versões de Documentos

Detecta quando chunks de busca pertencem a versões diferentes do mesmo documento
e produz um diff semântico via gpt-4o-mini.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List

from app.core.config import settings
from app.services.embedder import get_openai_client
from app.services.search import SearchResult

logger = logging.getLogger(__name__)

VERSION_DIFF_PROMPT = """Você recebe trechos de duas versões do mesmo documento técnico da Fujifilm.
Compare-os e identifique o que mudou semanticamente entre as versões.
Ignore diferenças de formatação ou ordem de palavras. Foque em:
- Valores numéricos (torques, temperaturas, dimensões)
- Procedimentos (passos adicionados, removidos ou modificados)
- Peças ou componentes (substituições, adições)
- Alertas ou avisos de segurança

Versão antiga ({version_old}):
{chunks_old}

Versão nova ({version_new}):
{chunks_new}

Retorne APENAS JSON válido com o schema exato (sem markdown, sem texto adicional):
{{"diff_items": [{{"change_type": "added|removed|modified", "topic": "...", "old_value": "...", "new_value": "..."}}], "has_changes": true}}

Se os documentos forem semanticamente idênticos, retorne:
{{"diff_items": [], "has_changes": false}}"""

MAX_TOKENS_PER_VERSION = 6000  # ~4-5 chunks


@dataclass
class DiffItem:
    change_type: str  # "added" | "removed" | "modified"
    topic: str
    old_value: str
    new_value: str


@dataclass
class VersionDiff:
    version_old: str  # published_date ISO da versão mais antiga
    version_new: str  # published_date ISO da versão mais recente
    diff_items: List[DiffItem] = field(default_factory=list)
    has_changes: bool = False


def detect_multi_version(results: List[SearchResult]) -> bool:
    """
    Retorna True se há ≥2 document_version_id distintos para o mesmo document_id.
    Agrupamento por document_id — campo já presente em SearchResult.
    """
    doc_to_versions: Dict[str, set] = {}
    for r in results:
        doc_to_versions.setdefault(r.document_id, set()).add(r.document_version_id)

    return any(len(versions) >= 2 for versions in doc_to_versions.values())


def group_chunks_by_version(
    results: List[SearchResult],
) -> Dict[str, List[SearchResult]]:
    """
    Agrupa chunks por published_date (ISO string), ordenado cronologicamente.
    Retorna dict com as datas como chave — mais antiga primeiro.
    """
    grouped: Dict[str, List[SearchResult]] = {}
    for r in results:
        date_key = r.published_date.isoformat() if hasattr(r.published_date, "isoformat") else str(r.published_date)
        grouped.setdefault(date_key, []).append(r)

    # Ordenar por data crescente
    return dict(sorted(grouped.items()))


def _build_version_text(chunks: List[SearchResult]) -> str:
    """Constrói texto concatenado dos chunks, priorizando por similarity."""
    sorted_chunks = sorted(chunks, key=lambda c: c.similarity, reverse=True)
    parts = []
    total_chars = 0
    char_limit = MAX_TOKENS_PER_VERSION * 4  # ~4 chars por token

    for chunk in sorted_chunks:
        if total_chars + len(chunk.content) > char_limit:
            break
        parts.append(chunk.content)
        total_chars += len(chunk.content)

    return "\n---\n".join(parts)


async def compare_versions(
    grouped: Dict[str, List[SearchResult]],
) -> VersionDiff:
    """
    Compara a versão mais antiga e a mais recente dos chunks agrupados.
    Usa gpt-4o-mini com JSON mode.

    Raises: json.JSONDecodeError, openai.APIError
    """
    sorted_dates = sorted(grouped.keys())
    if len(sorted_dates) < 2:
        raise ValueError(f"compare_versions requires at least 2 versions, got {len(sorted_dates)}")
    version_old = sorted_dates[0]
    version_new = sorted_dates[-1]

    chunks_old = _build_version_text(grouped[version_old])
    chunks_new = _build_version_text(grouped[version_new])

    prompt = VERSION_DIFF_PROMPT.format(
        version_old=version_old,
        version_new=version_new,
        chunks_old=chunks_old,
        chunks_new=chunks_new,
    )

    client = get_openai_client()
    response = await client.chat.completions.create(
        model=settings.azure_openai_mini_deployment,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1000,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    if content is None:
        raise ValueError("LLM returned empty content for version diff")
    raw = content.strip()
    logger.info(f"Version diff: {version_old} → {version_new} | raw: {raw[:200]}")

    parsed = json.loads(raw)  # Raises json.JSONDecodeError se inválido
    diff_items = [
        DiffItem(
            change_type=item.get("change_type", "modified"),
            topic=item.get("topic", ""),
            old_value=item.get("old_value", ""),
            new_value=item.get("new_value", ""),
        )
        for item in parsed.get("diff_items", [])
    ]

    return VersionDiff(
        version_old=version_old,
        version_new=version_new,
        diff_items=diff_items,
        has_changes=parsed["has_changes"],
    )
