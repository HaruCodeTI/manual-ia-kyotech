"""
Kyotech AI — Serviço de Viewer (Render de PDF como imagem)

Renderiza páginas individuais de PDFs como imagens PNG com watermark dinâmico.
O PDF nunca é exposto ao frontend — apenas a imagem renderizada server-side.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Configurações de render
RENDER_DPI = 150  # Resolução de render (150 DPI = boa qualidade sem ser pesado)
WATERMARK_OPACITY = 0.06  # Opacidade do watermark (sutil mas visível)
WATERMARK_FONT_SIZE = 11
WATERMARK_COLOR = (0.5, 0.5, 0.5)  # Cinza médio


def render_page_as_image(
    pdf_bytes: bytes,
    page_number: int,
    user_id: str,
    watermark_text: str | None = None,
) -> tuple[bytes, int]:
    """
    Renderiza uma página de um PDF como imagem PNG com watermark.

    Args:
        pdf_bytes: Bytes do arquivo PDF
        page_number: Número da página (1-indexed)
        user_id: ID do usuário (para watermark de rastreabilidade)
        watermark_text: Texto customizado do watermark (opcional)

    Returns:
        Tuple de (bytes da imagem PNG, total de páginas do PDF)

    Raises:
        ValueError: Se a página não existir
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    # Validar page_number (1-indexed)
    if page_number < 1 or page_number > total_pages:
        doc.close()
        raise ValueError(
            f"Página {page_number} inválida. O documento tem {total_pages} páginas."
        )

    page = doc[page_number - 1]  # fitz usa 0-indexed

    # Aplicar watermark antes de renderizar
    _apply_watermark(page, user_id, watermark_text)

    # Renderizar página como imagem
    mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)

    # Converter para PNG
    png_bytes = pix.tobytes("png")

    doc.close()

    logger.info(
        f"Página {page_number}/{total_pages} renderizada "
        f"({len(png_bytes) / 1024:.0f} KB, {pix.width}x{pix.height}px)"
    )

    return png_bytes, total_pages


def _apply_watermark(
    page: fitz.Page,
    user_id: str,
    custom_text: str | None = None,
) -> None:
    """
    Aplica watermark diagonal repetido sobre a página do PDF.
    O watermark inclui ID do usuário + timestamp para rastreabilidade.

    Usa insert_text com morph para rotação diagonal de -30 graus.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = custom_text or f"Kyotech | {user_id} | {now}"

    rect = page.rect
    fontsize = WATERMARK_FONT_SIZE

    # Espaçamento entre watermarks repetidos
    step_x = 280
    step_y = 140

    # Ângulo de rotação em radianos (-30 graus)
    angle_deg = -30
    angle_rad = math.radians(angle_deg)

    # Matriz de rotação para o morph
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    rotation_matrix = fitz.Matrix(cos_a, sin_a, -sin_a, cos_a, 0, 0)

    y = 30
    row = 0
    while y < rect.height + 100:
        x = -80 + (row % 2) * 100  # offset alternado
        while x < rect.width + 100:
            point = fitz.Point(x, y)
            try:
                page.insert_text(
                    point,
                    text,
                    fontsize=fontsize,
                    fontname="helv",
                    color=WATERMARK_COLOR,
                    fill_opacity=WATERMARK_OPACITY,
                    stroke_opacity=WATERMARK_OPACITY,
                    rotate=0,  # rotate aceita apenas 0/90/180/270
                    morph=(point, rotation_matrix),  # rotação livre via morph
                    overlay=True,
                )
            except Exception:
                pass  # Ignorar se fora dos limites
            x += step_x
        y += step_y
        row += 1
