# services/business/export_service.py
# Módulo de exportación avanzada (PDF, JSON, CSV, HTML) optimizado para consistencia de biodiversidad.

import json
import re
import pandas as pd
from datetime import datetime
from pathlib import Path
from io import BytesIO
from django.conf import settings
from django.http import HttpResponse
from django.utils.text import slugify

import base64

from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table as XLTable, TableStyleInfo
from openpyxl.worksheet.hyperlink import Hyperlink
from openpyxl.drawing.image import Image as XLImage

import plotly.graph_objects as go

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, PageBreak, HRFlowable,
)
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT


# ---------------------------------------------------------------------------
# Inyección de fórmulas en Excel (CWE-1236)
# ---------------------------------------------------------------------------
# codigo/localidad/finca_lote/cultivo/variedad vienen de texto libre que
# cualquier usuario con permiso de carga escribe en el formulario, y
# genus/species/family vienen tal cual del CSV/Excel subido. Si alguno
# empieza con = + - @ (o tab/CR), Excel/LibreOffice lo interpreta como
# fórmula al abrir el reporte generado — p. ej. un "código de muestra"
# =HYPERLINK("http://evil.com","click") ejecutaría esa fórmula para quien
# abra el reporte. Se sanea en todo el módulo justo antes de escribir a
# Excel (nunca se toca lo que se guarda en la base de datos).
_EXCEL_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _excel_safe(value):
    """Antepone un apóstrofe a texto que Excel interpretaría como fórmula."""
    if isinstance(value, str) and value.startswith(_EXCEL_FORMULA_TRIGGERS):
        return "'" + value
    return value


def _excel_safe_df(df):
    """
    Aplica _excel_safe a todas las columnas de texto de un DataFrame.

    No filtra por dtype antes de mapear: pandas >= 2.x puede tipar columnas
    de texto como 'object' o como su nuevo dtype 'str' dedicado según la
    versión/configuración, y _excel_safe ya ignora internamente cualquier
    valor que no sea str, así que aplicarlo a todas las columnas es más
    simple y no depende de adivinar qué dtype exacto usa pandas en cada caso.
    """
    df = df.copy()
    for col in df.columns:
        df[col] = df[col].map(_excel_safe)
    return df


# ---------------------------------------------------------------------------
# Paleta global
# ---------------------------------------------------------------------------
_DONUT_PALETTE = [
    '#1D9E75', '#0F6E56', '#BA7517', '#185FA5', '#A32D2D',
    '#9E6515', '#0C447C', '#6B4E9E', '#2E8B57', '#c7a640',
]
_COLOR_OTROS = '#B0B8C1'

_NIVEL_COLORES = {
    "ÓPTIMO":    "#14532d",
    "FAVORABLE": "#16a34a",
    "MODERADO":  "#ca8a04",
    "EN RIESGO": "#dc2626",
    "CRÍTICO":   "#7f1d1d",
}

# ---------------------------------------------------------------------------
# Identidad visual Plotly — gráficos del reporte Excel (Fase 1.2)
# ---------------------------------------------------------------------------
# Reusa los mismos tonos que ya usa el resto del reporte (CV/CAZUL/CA/CR de
# generar_excel_multisheet), agregando un turquesa como puente visual entre
# el verde y el azul. PLOTLY_FONT usa una familia ampliamente disponible en
# el servidor: Kaleido renderiza server-side y no tiene garantizada ninguna
# fuente web custom instalada.
PLOTLY_VERDE    = "#1D9E75"
PLOTLY_VERDE_OS = "#0F6E56"
PLOTLY_AZUL     = "#185FA5"
PLOTLY_TURQUESA = "#14B8A6"
PLOTLY_AMBAR    = "#BA7517"
PLOTLY_ROJO     = "#A32D2D"
PLOTLY_GRIS     = "#94A3B8"
PLOTLY_FONT     = "Arial, sans-serif"

# Colores por clasificación ecológica — mismos usados en los íconos
# 🟢🔴🔵⚪ del resto del reporte, para que los gráficos comuniquen el rol
# funcional de un vistazo en vez de un solo color plano sin significado.
COLOR_POR_CLAS = {
    "benefico":       PLOTLY_VERDE,
    "fitopatogeno":   PLOTLY_ROJO,
    "neutral":        PLOTLY_AZUL,
    "sin_clasificar": PLOTLY_GRIS,
}

# ---------------------------------------------------------------------------
# Modo de exportación (color / escala de grises) — Fase presentación
# ---------------------------------------------------------------------------
# El modo por defecto ("color") no cambia ningún valor respecto al
# comportamiento histórico de este archivo. El modo "grises" es aditivo:
# convierte cada color a su equivalente de luminancia percibida y, para
# gráficos de barras/torta, agrega un patrón de trama (hatch) distinto por
# categoría para que la figura siga siendo legible sin depender del color
# (requisito de tesis/publicación impresa en blanco y negro).
_HATCHES = ['', '//', 'xx', '..', '||', '--', '++', 'oo']  # matplotlib (multi-char permitido)
_HATCHES_PLOTLY = ['', '/', '\\', 'x', '-', '|', '+', '.']  # Plotly solo acepta 1 carácter


def _hex_a_gris(hex_color):
    """Convierte un color hex a su equivalente en gris (luminancia perceptual)."""
    h = (hex_color or "").lstrip('#')
    if len(h) != 6:
        return hex_color
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    y = round(0.299 * r + 0.587 * g + 0.114 * b)
    return '#{0:02x}{0:02x}{0:02x}'.format(max(0, min(255, y)))


def _resolver_color(hex_color, modo):
    return hex_color if modo != "grises" else _hex_a_gris(hex_color)


def _resolver_colores(hex_list, modo):
    return [_resolver_color(c, modo) for c in hex_list]


def _resolver_hatch(i, modo):
    return _HATCHES[i % len(_HATCHES)] if modo == "grises" else None


def _resolver_hatch_plotly(i, modo):
    return _HATCHES_PLOTLY[i % len(_HATCHES_PLOTLY)] if modo == "grises" else ""


def _plotly_layout_base(titulo="", subtitulo=None):
    """Layout base compartido por todas las figuras del reporte: tipografía,
    fondo blanco y título con estilo consistente, para no repetir estas
    mismas líneas en cada gráfico."""
    titulo_html = f"<b>{titulo}</b>"
    if subtitulo:
        titulo_html += f"<br><span style='font-size:12px;color:#6B7280'>{subtitulo}</span>"
    return dict(
        title=dict(text=titulo_html, font=dict(family=PLOTLY_FONT, size=16, color="#1F2937"),
                   x=0.02, xanchor="left"),
        font=dict(family=PLOTLY_FONT, size=13, color="#374151"),
        paper_bgcolor="white",
        plot_bgcolor="white",
        margin=dict(l=60, r=30, t=70 if not subtitulo else 90, b=50),
        showlegend=False,
    )


def _fig_a_imagen_xl(fig, ancho_px=900, alto_px=520, escala=3):
    """Renderiza una figura Plotly a PNG (motor Kaleido) y la envuelve como
    openpyxl.drawing.image.Image lista para ws.add_image(). escala=3 da
    ~300 DPI equivalentes (partiendo de una base de pantalla de 96 DPI) para
    que la imagen no se vea pixelada ni al ampliar en Excel ni si se
    reutiliza en un informe impreso — mismo criterio de resolución que usa
    este archivo para los gráficos matplotlib del PDF (dpi=300, ver
    ExportService._chart_donut_taxa y similares)."""
    fig.update_layout(width=ancho_px, height=alto_px)
    buf = BytesIO()
    fig.write_image(buf, format="png", scale=escala)
    buf.seek(0)
    img = XLImage(buf)
    img.width, img.height = ancho_px, alto_px
    return img


# Colores ReportLab para clasificación
_C_BEN  = colors.HexColor('#16a34a')
_C_FITO = colors.HexColor('#dc2626')
_C_NEU  = colors.HexColor('#64748b')
_C_SC   = colors.HexColor('#94a3b8')

_C_PRIMARY   = colors.HexColor('#1b4332')
_C_SECONDARY = colors.HexColor('#2d6a4f')
_C_LIGHT     = colors.HexColor('#f8f9fa')
_C_BORDER    = colors.HexColor('#dee2e6')
_C_INNER     = colors.HexColor('#e9ecef')


def _get_styles():
    styles = getSampleStyleSheet()
    _gray   = colors.HexColor('#374151')
    _muted  = colors.HexColor('#64748b')
    _white  = colors.white

    style_titulo = ParagraphStyle(
        'ScientificTitle', parent=styles['Heading1'], fontSize=22, leading=27,
        textColor=_white, spaceAfter=0, alignment=TA_LEFT, fontName='Helvetica-Bold',
    )
    style_subtitle = ParagraphStyle(
        'ScientificSubtitle', parent=styles['Normal'], fontSize=11, leading=15,
        textColor=colors.HexColor('#d1fae5'), fontName='Helvetica',
    )
    style_h2 = ParagraphStyle(
        'ScientificH2', parent=styles['Heading2'], fontSize=11, leading=14,
        textColor=_white, spaceBefore=0, spaceAfter=0, fontName='Helvetica-Bold',
    )
    style_h3 = ParagraphStyle(
        'ScientificH3', parent=styles['Heading3'], fontSize=10.5, leading=14,
        textColor=_C_PRIMARY, spaceBefore=10, spaceAfter=5, fontName='Helvetica-Bold',
    )
    style_body = ParagraphStyle(
        'ScientificBody', parent=styles['Normal'], fontSize=9.5, leading=13.5,
        textColor=_gray,
    )
    style_body_sm = ParagraphStyle(
        'ScientificBodySm', parent=styles['Normal'], fontSize=8.5, leading=11.5,
        textColor=_gray,
    )
    style_th = ParagraphStyle(
        'TableTh', parent=styles['Normal'], fontSize=8.5, leading=11,
        textColor=_white, fontName='Helvetica-Bold',
    )
    style_th_dark = ParagraphStyle(
        'TableThDark', parent=styles['Normal'], fontSize=8.5, leading=11,
        textColor=_white, fontName='Helvetica-Bold', alignment=TA_CENTER,
    )
    style_center = ParagraphStyle(
        'CenteredBody', parent=styles['Normal'], fontSize=9.5, leading=13,
        textColor=_gray, alignment=TA_CENTER,
    )
    style_italic = ParagraphStyle(
        'ItalicBody', parent=styles['Normal'], fontSize=8.5, leading=12,
        textColor=_muted, fontName='Helvetica-Oblique',
    )
    style_caption = ParagraphStyle(
        'Caption', parent=styles['Normal'], fontSize=7.5, leading=10,
        textColor=_muted, fontName='Helvetica-Oblique', alignment=TA_CENTER,
        spaceBefore=3, spaceAfter=6,
    )
    style_kpi_val = ParagraphStyle(
        'KpiVal', parent=styles['Normal'], fontSize=26, leading=30,
        fontName='Helvetica-Bold', alignment=TA_CENTER,
    )
    style_kpi_lbl = ParagraphStyle(
        'KpiLbl', parent=styles['Normal'], fontSize=7.5, leading=10,
        textColor=_muted, alignment=TA_CENTER,
    )
    style_label = ParagraphStyle(
        'LabelDark', parent=styles['Normal'], fontSize=8.5, leading=11,
        textColor=_C_PRIMARY, fontName='Helvetica-Bold',
    )
    style_muted = ParagraphStyle(
        'Muted', parent=styles['Normal'], fontSize=8, leading=11,
        textColor=_muted,
    )
    return {
        "titulo":    style_titulo,
        "subtitle":  style_subtitle,
        "h2":        style_h2,
        "h3":        style_h3,
        "body":      style_body,
        "body_sm":   style_body_sm,
        "th":        style_th,
        "th_dark":   style_th_dark,
        "center":    style_center,
        "italic":    style_italic,
        "caption":   style_caption,
        "kpi_val":   style_kpi_val,
        "kpi_lbl":   style_kpi_lbl,
        "label":     style_label,
        "muted":     style_muted,
    }


def _pdf_footer(canvas, doc):
    """Footer con separador y número de página."""
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#e2e8f0'))
    canvas.setLineWidth(0.5)
    canvas.line(40, 30, A4[0] - 40, 30)
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(colors.HexColor('#94a3b8'))
    canvas.drawString(40, 20, "BioMicro UTC — Análisis Microbiológico de Suelos")
    canvas.drawRightString(A4[0] - 40, 20, f"Pág. {canvas.getPageNumber()}")
    canvas.restoreState()


def _seccion_hdr(titulo, ancho_util, S, color=None, numero=None):
    """Banda de encabezado de sección: fondo verde oscuro, texto blanco."""
    bg = color or _C_PRIMARY
    texto = f"{'  ' + str(numero) + '.  ' if numero else '  '}{titulo}"
    t = Table([[Paragraph(texto, S["h2"])]], colWidths=[ancho_util])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), bg),
        ('TOPPADDING',    (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
        ('LEFTPADDING',   (0, 0), (-1, -1), 12),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 12),
    ]))
    return t


def _kpi_tiles(items, ancho_util, S):
    """
    Fila de tarjetas KPI.
    items = [{'val': str, 'lbl': str, 'color': hex_str, 'sub': str (opcional)}]
    """
    n = len(items)
    w = ancho_util / n

    cells = []
    for it in items:
        kpi_style = ParagraphStyle(
            'KpiValDyn', parent=S["kpi_val"],
            textColor=colors.HexColor(it.get("color", "#1b4332")),
        )
        sub_p = Paragraph(it.get("sub", ""), S["kpi_lbl"]) if it.get("sub") else Spacer(1, 2)
        cells.append(
            Table(
                [[Paragraph(str(it["val"]), kpi_style)],
                 [Paragraph(it["lbl"], S["kpi_lbl"])],
                 [sub_p]],
                colWidths=[w - 2],
            )
        )

    t = Table([cells], colWidths=[w] * n)
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX',           (0, 0), (-1, -1), 1,   colors.HexColor('#e2e8f0')),
        ('INNERGRID',     (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
    ]))
    return t


def _nivel_color_rl(nivel_salud: str):
    hex_color = _NIVEL_COLORES.get(nivel_salud, "#64748b")
    return colors.HexColor(hex_color)


# ---------------------------------------------------------------------------
# Fase 1 — Portada / Índice / Conclusiones / Recomendaciones / navegación
# ---------------------------------------------------------------------------
# Todo lo que sigue es aditivo sobre generar_excel_multisheet: agrega hojas
# y una fila de navegación al tope de las hojas ya existentes, sin tocar su
# contenido/valores. No modifica generar_pdf_individual, generar_pdf_comparativo
# ni generar_html_reporte.

_REF_RANGE_RE   = re.compile(r"([A-Z]+)(\d+):([A-Z]+)(\d+)")
_CELL_ANCHOR_RE = re.compile(r"^([A-Z]+)(\d+)$")
_FORMULA_ROW_RE = re.compile(r"\$([A-Z]+)\$(\d+)")


def _shift_ref_rows(ref, offset):
    """'A1:E26' -> 'A2:E27' (desplaza el rango de una Table de Excel)."""
    m = _REF_RANGE_RE.match(ref or "")
    if not m:
        return ref
    c1, r1, c2, r2 = m.groups()
    return f"{c1}{int(r1) + offset}:{c2}{int(r2) + offset}"


def _shift_anchor(anchor, offset):
    """'G3' -> 'G4' (desplaza el ancla de un gráfico)."""
    m = _CELL_ANCHOR_RE.match(str(anchor or ""))
    if not m:
        return anchor
    col, row = m.groups()
    return f"{col}{int(row) + offset}"


def _shift_formula_rows(formula, offset):
    """"'Hoja'!$D$1:$D$26" -> "'Hoja'!$D$2:$D$27" (fórmulas de series de gráfico)."""
    if not formula:
        return formula
    return _FORMULA_ROW_RE.sub(
        lambda m: f"${m.group(1)}${int(m.group(2)) + offset}", formula
    )


def _retro_freeze_y_nav(ws, freeze_cell="A3", titulo_extra=None, offset=1,
                         indice_location="'Índice'!A1"):
    """
    Inserta una fila de navegación ("⬅ Volver al Índice") al tope de una hoja
    YA construida y congela paneles, sin romper las Tables ni los gráficos
    que la hoja ya tenga.

    ws.insert_rows() no actualiza automáticamente el rango de las Tables de
    Excel, ni el ancla/fórmulas de series de los gráficos, ni row_dimensions
    (verificado empíricamente) — por eso se parchean a mano después de
    insertar la fila. ws._charts es un atributo "privado" pero es la única
    forma de llegar a los gráficos ya agregados (openpyxl no expone una API
    pública de lectura).
    """
    original_heights = {k: v.height for k, v in list(ws.row_dimensions.items())
                         if v.height is not None}
    for k in list(ws.row_dimensions.keys()):
        del ws.row_dimensions[k]

    ws.insert_rows(1, amount=offset)

    for k, h in original_heights.items():
        ws.row_dimensions[k + offset].height = h
    ws.row_dimensions[1].height = 20

    for tbl in ws.tables.values():
        tbl.ref = _shift_ref_rows(tbl.ref, offset)

    for ch in ws._charts:
        ch.anchor = _shift_anchor(ch.anchor, offset)
        for s in ch.series:
            if getattr(s, "val", None) and s.val.numRef:
                s.val.numRef.f = _shift_formula_rows(s.val.numRef.f, offset)
            if getattr(s, "cat", None):
                ref = s.cat.numRef or s.cat.strRef
                if ref:
                    ref.f = _shift_formula_rows(ref.f, offset)
            if getattr(s, "tx", None) and s.tx and s.tx.strRef:
                s.tx.strRef.f = _shift_formula_rows(s.tx.strRef.f, offset)

    # Los gráficos Plotly se embeben como imágenes (ws._images), no como
    # ws._charts — su ancla es igual de una cadena tipo "G3" y necesita el
    # mismo desplazamiento, si no quedan una fila más arriba de donde deben.
    for img in ws._images:
        img.anchor = _shift_anchor(img.anchor, offset)

    texto_nav = "⬅ Volver al Índice"
    if titulo_extra:
        texto_nav += f"    |    {titulo_extra}"
    c = ws.cell(row=1, column=1, value=texto_nav)
    # Hipervínculo INTERNO (misma carpeta de trabajo): debe usarse el
    # parámetro location= de Hyperlink, no target= (que es lo que openpyxl
    # asigna por defecto si se pasa un string plano a .hyperlink). target=
    # crea una relación con TargetMode="External" apuntando a un fragmento
    # interno ("#'Índice'!A1"), algo que Excel detecta como contenido
    # inválido y dispara el diálogo de "hemos encontrado un problema...".
    # location= en cambio se escribe directo en el XML sin relationship.
    c.hyperlink = Hyperlink(ref=c.coordinate, location=indice_location,
                             tooltip="Volver al Índice")
    c.font = Font(color="0563C1", underline="single", bold=True, size=10)
    ws.freeze_panes = freeze_cell


_ETIQUETAS_HOJAS = {
    "Dashboard":               ("🌱", "Dashboard"),
    "Resumen":                ("📋", "Resumen Ejecutivo"),
    "Resumen_Comparativo":    ("📋", "Resumen Ejecutivo Comparativo"),
    "Top_N_Taxa":              ("📊", "Top Taxa"),
    "Top_N_Global":            ("📊", "Top Taxa Global"),
    "Taxonomia_Completa":      ("🧬", "Taxonomía Completa"),
    "Diversidad_Alfa":         ("🔬", "Diversidad Alfa"),
    "Diversidad_Beta":         ("🔬", "Diversidad Beta"),
    "Clasificacion_Funcional": ("🏷", "Clasificación Funcional"),
    "Clas_Por_Muestra":        ("🏷", "Clasificación por Muestra"),
    "Microorganismos_Detalle": ("🦠", "Microorganismos — Detalle"),
    "Analisis_Diferencial":    ("⚖", "Análisis Diferencial"),
    "Cuadro_Comparativo":      ("📐", "Cuadro Comparativo"),
    "Conclusiones_Recomendaciones": ("✅", "Conclusiones y Recomendaciones"),
}

_TITULO_EXTRA_HOJAS = {
    "Microorganismos_Detalle": "🟢🔴🔵 Benéficos · Fitopatógenos · Neutrales",
}


# ---------------------------------------------------------------------------
# Interpretación automática — texto generado a partir de valores ya calculados
# (no se agregan cálculos nuevos, solo se traducen a prosa)
# ---------------------------------------------------------------------------

_NIVEL_TEXTO_SALUD = {
    "ÓPTIMO":    "Esto indica una comunidad microbiana altamente funcional, con condiciones "
                 "óptimas para el desarrollo del cultivo.",
    "FAVORABLE": "Esto indica condiciones adecuadas, con una relación entre microorganismos "
                 "benéficos y fitopatógenos favorable al cultivo.",
    "MODERADO":  "Esto indica un equilibrio funcional con margen de mejora; se recomienda "
                 "monitorear la evolución del suelo.",
    "EN RIESGO": "Esto indica un desequilibrio funcional que amerita intervención agronómica.",
    "CRÍTICO":   "Esto indica una perturbación significativa del microbioma que requiere "
                 "intervención urgente.",
}


def _texto_shannon(v):
    v = float(v or 0)
    if v > 3:
        return ("Este valor refleja una diversidad alta: la comunidad es heterogénea y "
                "potencialmente más resiliente frente a perturbaciones.")
    if v > 2:
        return "Este valor refleja una diversidad moderada-alta, propia de un ecosistema funcional."
    if v > 1:
        return "Este valor refleja una diversidad moderada, con distribución irregular entre los taxa presentes."
    return "Este valor refleja una diversidad baja, con dominancia marcada de uno o pocos taxa."


def _texto_simpson(v):
    v = float(v or 0)
    if v > 0.85:
        return "Este valor indica alta equidad: la abundancia está distribuida de forma uniforme entre los taxa."
    if v > 0.60:
        return "Este valor indica buena equidad, con varios taxa de abundancia relevante."
    if v > 0.30:
        return "Este valor indica dominancia moderada: pocos taxa concentran buena parte del perfil."
    return "Este valor indica dominancia alta: uno o dos taxa concentran la mayoría de la abundancia."


def _contexto_reglas(datos: dict) -> dict:
    """
    Extrae un contexto plano y con defaults ya resueltos a partir del dict
    `datos` que ya arma reportes.py — reusado por los tres generadores de
    texto para no repetir la misma extracción tres veces. No calcula nada
    nuevo, solo lee valores que ya vienen calculados.
    """
    diversidad   = datos.get("diversidad") or {}
    totales_clas = datos.get("totales_clas") or {}
    muestras     = datos.get("muestras") or []
    n_ben  = totales_clas.get("benefico", 0)
    n_fito = totales_clas.get("fitopatogeno", 0)
    n_neu  = totales_clas.get("neutral", 0)
    total_cat     = (n_ben + n_fito + n_neu) or 1
    total_ben_fito = (n_ben + n_fito) or 1
    return {
        "indice_salud":     datos.get("indice_salud") or 0,
        "nivel_salud":      datos.get("nivel_salud") or "N/A",
        "shannon":          float(diversidad.get("shannon") or 0),
        "simpson":          float(diversidad.get("simpson") or 0),
        "equitatividad":    float(diversidad.get("equitatividad") or 0),
        "riqueza":          int(diversidad.get("riqueza") or len(datos.get("todos_taxa") or [])),
        "n_benefico":       n_ben,
        "n_fitopatogeno":   n_fito,
        "n_neutral":        n_neu,
        "n_sin_clasificar": totales_clas.get("sin_clasificar", 0),
        # ratio_ben/ratio_fito usan el mismo denominador (benéfico+fitopatógeno)
        # que ya usa calcular_indice_salud() para el índice de salud — así las
        # reglas de conclusiones/recomendaciones nunca contradicen el nivel
        # de salud ya calculado (ej. no recomendar "más benéficos" en un
        # suelo ÓPTIMO solo porque hay muchos taxa neutrales sin relación).
        "ratio_ben":        n_ben / total_ben_fito,
        "ratio_fito":       n_fito / total_ben_fito,
        # Para la narrativa descriptiva ("% de los taxa catalogados"), que sí
        # debe incluir neutrales en el denominador.
        "ratio_fito_comunidad": n_fito / total_cat,
        "n_muestras":       len(muestras),
        "is_comparativo":   len(muestras) > 1,
        "total_taxa":       len(datos.get("todos_taxa") or []),
        "marcador":         datos.get("tipo") or "16S",
        "nivel_tax":        datos.get("nivel") or "genus",
    }


def _generar_interpretacion_ejecutiva(datos: dict) -> list:
    """4-6 párrafos de prosa que responden qué tan saludable está el suelo,
    cuál es su diversidad, cuántos microorganismos se encontraron, si hay
    fitopatógenos y qué significan Shannon/Simpson — todo a partir de valores
    ya calculados en `datos`, sin cálculos nuevos."""
    c = _contexto_reglas(datos)
    parrafos = []

    plural = "s" if c["is_comparativo"] else ""
    parrafos.append(
        f"Esta muestra{plural} presenta{plural} un Índice de Salud del Suelo de "
        f"{c['indice_salud']}/100, clasificado como {c['nivel_salud']}. "
        + _NIVEL_TEXTO_SALUD.get(c["nivel_salud"], "")
    )

    parrafos.append(
        f"Se identificaron {c['total_taxa']} taxones distintos a nivel de {c['nivel_tax']} "
        f"mediante el marcador molecular {c['marcador']}, de los cuales {c['n_benefico']} "
        f"están catalogados como benéficos, {c['n_fitopatogeno']} como potenciales fitopatógenos, "
        f"{c['n_neutral']} como neutrales y {c['n_sin_clasificar']} aún no están catalogados."
    )

    if c["n_fitopatogeno"] > 0:
        riesgo = ("Su proporción es baja y no representa, por sí sola, un riesgo fitosanitario relevante."
                  if c["ratio_fito"] < 0.15 else
                  "Su proporción sugiere un riesgo fitosanitario que amerita monitoreo.")
        parrafos.append(
            f"Se detectó presencia de microorganismos fitopatógenos ({c['n_fitopatogeno']} "
            f"taxón(es), {c['ratio_fito_comunidad']*100:.1f}% de los taxa catalogados funcionalmente). {riesgo}"
        )
    else:
        parrafos.append("No se detectaron microorganismos fitopatógenos entre los taxa catalogados funcionalmente.")

    parrafos.append(
        f"El índice de Shannon (H'={c['shannon']:.4f}) mide la diversidad considerando tanto la "
        f"riqueza de taxa como su distribución de abundancias. {_texto_shannon(c['shannon'])}"
    )
    parrafos.append(
        f"El índice de Simpson (1-D={c['simpson']:.4f}) expresa la probabilidad de que dos "
        f"individuos tomados al azar pertenezcan a taxa distintos. {_texto_simpson(c['simpson'])}"
    )

    return parrafos


_REGLAS_CONCLUSIONES = [
    {"condicion": lambda c: c["nivel_salud"] in ("ÓPTIMO", "FAVORABLE"),
     "texto": lambda c: (
        f"El índice de salud del suelo ({c['indice_salud']}/100, nivel {c['nivel_salud']}) indica "
        f"una comunidad microbiana funcional y en equilibrio con el cultivo.")},
    {"condicion": lambda c: c["nivel_salud"] in ("EN RIESGO", "CRÍTICO"),
     "texto": lambda c: (
        f"El índice de salud del suelo ({c['indice_salud']}/100, nivel {c['nivel_salud']}) señala "
        f"un desequilibrio funcional de la comunidad microbiana que amerita atención.")},
    {"condicion": lambda c: c["shannon"] > 3,
     "texto": lambda c: (
        f"La diversidad de Shannon (H'={c['shannon']:.4f}) es alta, lo que sugiere una comunidad "
        f"microbiana resiliente frente a perturbaciones ambientales.")},
    {"condicion": lambda c: c["shannon"] <= 1,
     "texto": lambda c: (
        f"La diversidad de Shannon (H'={c['shannon']:.4f}) es baja, evidenciando dominancia marcada "
        f"de uno o pocos taxa sobre el resto de la comunidad.")},
    {"condicion": lambda c: c["ratio_fito"] > 0.15,
     "texto": lambda c: (
        f"Los taxa fitopatógenos representan {c['ratio_fito']*100:.1f}% frente a los benéficos "
        f"({c['n_fitopatogeno']} taxón(es)), un nivel que sugiere riesgo fitosanitario relevante.")},
    {"condicion": lambda c: c["n_fitopatogeno"] == 0,
     "texto": lambda c: "No se detectaron microorganismos fitopatógenos entre los taxa catalogados funcionalmente."},
    {"condicion": lambda c: c["ratio_ben"] > 0.5,
     "texto": lambda c: (
        f"Los microorganismos benéficos predominan claramente sobre los fitopatógenos "
        f"({c['ratio_ben']*100:.1f}% frente a estos últimos), aportando potencial de reciclaje de "
        f"nutrientes y control biológico natural.")},
    {"condicion": lambda c: 0 < c["equitatividad"] < 0.3,
     "texto": lambda c: (
        f"La equitatividad de Pielou (J'={c['equitatividad']:.4f}) es baja: uno o dos taxa concentran "
        f"la mayor parte de la abundancia detectada.")},
    {"condicion": lambda c: c["is_comparativo"],
     "texto": lambda c: (
        f"El análisis comparativo incluye {c['n_muestras']} muestras, lo que permite contrastar la "
        f"composición microbiana entre distintos puntos de muestreo.")},
]

_REGLAS_RECOMENDACIONES = [
    {"condicion": lambda c: c["ratio_ben"] < 0.3,
     "texto": lambda c: (
        "Favorecer la actividad de microorganismos benéficos mediante abonos orgánicos, compost "
        "maduro o inoculantes microbianos específicos.")},
    {"condicion": lambda c: c["nivel_salud"] in ("EN RIESGO", "CRÍTICO"),
     "texto": lambda c: (
        "Evitar aplicaciones innecesarias de fungicidas de amplio espectro, ya que pueden afectar "
        "aún más el equilibrio de la comunidad microbiana del suelo.")},
    {"condicion": lambda c: c["ratio_fito"] > 0.15,
     "texto": lambda c: (
        "Implementar monitoreo fitosanitario periódico y evaluar rotación de cultivos para reducir "
        "la presión de organismos fitopatógenos sobre el sistema.")},
    {"condicion": lambda c: c["shannon"] <= 1 or c["riqueza"] < 30,
     "texto": lambda c: (
        "Incrementar la diversidad microbiana mediante cobertura vegetal, rotación de cultivos y "
        "reducción de la labranza intensiva.")},
    {"condicion": lambda c: c["nivel_salud"] in ("ÓPTIMO", "FAVORABLE"),
     "texto": lambda c: (
        "Conservar las prácticas de manejo actuales, priorizando la cobertura vegetal y el aporte "
        "de materia orgánica que sostienen el equilibrio observado.")},
    {"condicion": lambda c: 0 < c["equitatividad"] < 0.3,
     "texto": lambda c: (
        "Diversificar fuentes de materia orgánica y evitar monocultivos prolongados para reducir la "
        "dominancia de unos pocos taxa.")},
    {"condicion": lambda c: True,
     "texto": lambda c: (
        "Mantener un monitoreo periódico de la comunidad microbiana para dar seguimiento a la "
        "evolución del suelo en el tiempo.")},
]


def _generar_conclusiones(datos: dict) -> list:
    c = _contexto_reglas(datos)
    resultado = [regla["texto"](c) for regla in _REGLAS_CONCLUSIONES if regla["condicion"](c)]
    return resultado or ["No se generaron conclusiones automáticas para los datos disponibles."]


def _generar_recomendaciones(datos: dict) -> list:
    c = _contexto_reglas(datos)
    resultado = [regla["texto"](c) for regla in _REGLAS_RECOMENDACIONES if regla["condicion"](c)]
    return resultado or ["No se generaron recomendaciones automáticas para los datos disponibles."]


def _construir_hoja_portada(wb, datos):
    """Hoja de portada: logo, identidad del sistema, datos institucionales e
    identificación de la(s) muestra(s). Solo usa campos que existen en el
    modelo MuestraSuelo — no incluye "Sector" ni "Laboratorio" (no existen)."""
    ws = wb.create_sheet("Portada")
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 4
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 46
    for col in "DEFG":
        ws.column_dimensions[col].width = 12

    for col in range(1, 8):
        ws.cell(row=1, column=col).fill = PatternFill("solid", fgColor="0F6E56")
    ws.row_dimensions[1].height = 6

    logo_path = settings.BASE_DIR / "portal" / "static" / "portal" / "img" / "logo.png"
    if logo_path.exists():
        try:
            img = XLImage(str(logo_path))
            img.width = 90
            img.height = 90
            ws.add_image(img, "B3")
        except Exception:
            pass  # el logo es decorativo — no debe romper la generación del reporte

    ws.cell(row=3, column=3, value="BioMicro").font = Font(bold=True, size=28, color="0F6E56")
    ws.cell(row=4, column=3,
            value="Sistema Web para Procesamiento, Análisis Comparativo y").font = Font(size=11, italic=True, color="4A4A4A")
    ws.cell(row=5, column=3,
            value="Visualización de Perfiles Microbianos").font = Font(size=11, italic=True, color="4A4A4A")

    fila = 8
    for linea, tam, negrita, color in [
        ("Universidad Técnica de Cotopaxi", 13, True, "0F6E56"),
        ("Carrera de Ingeniería en Sistemas de Información", 11, False, "4A4A4A"),
        ("Proyecto de Investigación — Análisis Comparativo de Perfiles Microbianos de Suelo", 10, False, "888888"),
    ]:
        ws.cell(row=fila, column=2, value=linea).font = Font(size=tam, bold=negrita, color=color)
        ws.merge_cells(start_row=fila, start_column=2, end_row=fila, end_column=7)
        fila += 1

    fila += 1
    ws.cell(row=fila, column=2,
            value="REPORTE DE SALUD DEL SUELO Y BIODIVERSIDAD MICROBIANA").font = Font(bold=True, size=14, color="FFFFFF")
    ws.cell(row=fila, column=2).fill = PatternFill("solid", fgColor="1D9E75")
    for col in range(2, 8):
        ws.cell(row=fila, column=col).fill = PatternFill("solid", fgColor="1D9E75")
    ws.merge_cells(start_row=fila, start_column=2, end_row=fila, end_column=7)
    ws.row_dimensions[fila].height = 26
    fila += 2

    muestras = datos.get("muestras") or []
    muestra  = datos.get("muestra")
    usuario  = datos.get("usuario")
    if usuario:
        nombre_completo = getattr(usuario, "get_full_name", lambda: "")()
        usuario_nombre = _excel_safe(nombre_completo or getattr(usuario, "username", "Sistema"))
    else:
        usuario_nombre = "Sistema"
    ahora = datetime.now()

    filas_meta = [
        ("Fecha de generación", ahora.strftime("%d/%m/%Y")),
        ("Hora de generación", ahora.strftime("%H:%M:%S")),
        ("Generado por", usuario_nombre),
        ("Marcador molecular", "16S rRNA (bacterias)" if datos.get("tipo") == "16S" else "ITS (hongos)"),
        ("Nivel taxonómico analizado", str(datos.get("nivel", "genus")).capitalize()),
    ]

    if muestra and len(muestras) <= 1:
        cultivo_nom = getattr(getattr(muestra, "cultivo", None), "nombre", None) or "N/A"
        var_nom     = getattr(getattr(muestra, "variedad_clon", None), "nombre", None) or "N/A"
        filas_meta += [
            ("Código de muestra", _excel_safe(str(getattr(muestra, "codigo", "N/A")))),
            ("Cultivo",           _excel_safe(str(cultivo_nom))),
            ("Variedad / Clon",   _excel_safe(str(var_nom))),
            ("Localidad",         _excel_safe(str(getattr(muestra, "localidad", None) or "N/A"))),
            ("Finca / Lote",      _excel_safe(str(getattr(muestra, "finca_lote", None) or "N/A"))),
            ("Tipo de muestra",   _excel_safe(str(getattr(muestra, "tipo_muestra", None) or "Suelo"))),
        ]
        if getattr(muestra, "altitud", None) is not None:
            filas_meta.append(("Altitud", f"{muestra.altitud} m.s.n.m."))
    elif muestras:
        codigos_list = [_excel_safe(str(getattr(m, "codigo", "N/A"))) for m in muestras[:12]]
        codigos = ", ".join(codigos_list)
        if len(muestras) > 12:
            codigos += f" … (+{len(muestras) - 12} más)"
        filas_meta += [
            ("Tipo de reporte",    "Comparativo"),
            ("N.° de muestras",    str(len(muestras))),
            ("Muestras incluidas", codigos),
        ]
    else:
        filas_meta.append(("Alcance", "Global (todas las muestras registradas)"))

    for etiqueta, valor in filas_meta:
        ws.cell(row=fila, column=2, value=etiqueta).font = Font(bold=True, size=10, color="0F6E56")
        celda_valor = ws.cell(row=fila, column=3, value=valor)
        celda_valor.font = Font(size=10, color="374151")
        celda_valor.alignment = Alignment(wrap_text=True, vertical="center")
        ws.merge_cells(start_row=fila, start_column=3, end_row=fila, end_column=7)
        fila += 1

    fila += 2
    for col in range(1, 8):
        ws.cell(row=fila, column=col).fill = PatternFill("solid", fgColor="E8F5EF")
    ws.cell(row=fila, column=2,
            value="Generado automáticamente por BioMicro — reporte científico de biodiversidad "
                  "microbiana del suelo").font = Font(italic=True, size=9, color="0F6E56")
    ws.merge_cells(start_row=fila, start_column=2, end_row=fila, end_column=7)
    ws.row_dimensions[fila].height = 20

    return ws


def _construir_hoja_indice(wb, nombres_hojas):
    """Hoja de índice con hipervínculos internos a cada hoja del reporte."""
    ws = wb.create_sheet("Índice")
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 46

    ws.cell(row=1, column=1, value="Índice del Reporte").font = Font(bold=True, size=16, color="0F6E56")
    ws.cell(row=2, column=1,
            value="Haz clic en cualquier hoja para ir directamente a ella.").font = Font(italic=True, size=10, color="888888")

    fila = 4
    for nombre in nombres_hojas:
        icono, etiqueta = _ETIQUETAS_HOJAS.get(nombre, ("📄", nombre))
        celda = ws.cell(row=fila, column=1, value=f"{icono}  {etiqueta}")
        celda.hyperlink = Hyperlink(ref=celda.coordinate, location=f"'{nombre}'!A1",
                                     tooltip=f"Ir a {etiqueta}")
        celda.font = Font(color="0563C1", underline="single", size=12)
        ws.row_dimensions[fila].height = 22
        fila += 1

    return ws


def _agregar_seccion_narrativa(ws, fila, titulo, items, color_hex):
    """Escribe una sección narrativa (título + lista numerada) a partir de
    `fila` y devuelve la siguiente fila libre — permite apilar varias
    secciones en una misma hoja en vez de crear una hoja por sección."""
    ws.cell(row=fila, column=2, value=titulo).font = Font(bold=True, size=15, color=color_hex)
    ws.row_dimensions[fila].height = 26
    fila += 2

    for i, texto in enumerate(items, start=1):
        celda = ws.cell(row=fila, column=2, value=f"{i}.  {texto}")
        celda.font = Font(size=11, color="374151")
        celda.alignment = Alignment(wrap_text=True, vertical="top")
        lineas = max(1, -(-len(texto) // 90))  # ceil(len/90) sin importar math
        ws.row_dimensions[fila].height = 18 * lineas
        fila += 2

    return fila + 1


def _construir_hoja_conclusiones_recomendaciones(wb, datos):
    """Una sola hoja con dos secciones (Conclusiones + Recomendaciones), en
    vez de 2 hojas casi vacías separadas."""
    ws = wb.create_sheet("Conclusiones_Recomendaciones")
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 4
    ws.column_dimensions["B"].width = 95

    fila = _agregar_seccion_narrativa(
        ws, 1, "✅  Conclusiones del Análisis",
        _generar_conclusiones(datos), "0F6E56",
    )
    fila = _agregar_seccion_narrativa(
        ws, fila + 1, "💡  Recomendaciones de Manejo del Suelo",
        _generar_recomendaciones(datos), "BA7517",
    )

    ws.cell(row=fila, column=2,
            value="Generado automáticamente por BioMicro a partir de los índices ecológicos "
                  "calculados.").font = Font(italic=True, size=9, color="888888")
    return ws


class ExportService:
    """Servicio de exportación avanzada a múltiples formatos con soporte biogeográfico."""

    # ------------------------------------------------------------------
    # Charts matplotlib
    # ------------------------------------------------------------------

    @staticmethod
    def _chart_donut_taxa(top_taxa, width_pt=250, height_pt=200,
                          titulo="Composición Taxonómica", subtitulo="Top 10 taxa por abundancia relativa (%)",
                          modo="color"):
        """Donut chart de top 10 taxa con título interno. Devuelve RLImage o None."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            # Sans-serif (Arial/Helvetica) — lo que piden la mayoría de
            # revistas científicas para el texto DENTRO de las figuras;
            # DejaVu Sans (incluida con matplotlib) como respaldo si el
            # servidor no tiene Arial/Helvetica instalada.
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']

            if not top_taxa:
                return None

            taxa_top10 = top_taxa[:10]
            labels = [str(r.get("taxonomia", r.get("nombre", "?"))) for r in taxa_top10]
            sizes  = [float(r.get("total_porcentaje", r.get("porcentaje", 0))) for r in taxa_top10]
            otros  = max(0, 100 - sum(sizes))

            if otros > 0.01:
                labels.append("Otros")
                sizes.append(otros)
                palette = _DONUT_PALETTE[:len(taxa_top10)] + [_COLOR_OTROS]
            else:
                palette = _DONUT_PALETTE[:len(labels)]
            palette = _resolver_colores(palette, modo)

            fig, ax = plt.subplots(figsize=(width_pt / 72, height_pt / 72))
            fig.patch.set_facecolor('#ffffff')

            wedges, _ = ax.pie(
                sizes, labels=None, colors=palette,
                startangle=90, counterclock=False,
                wedgeprops=dict(width=0.48, edgecolor='white', linewidth=0.8),
            )
            if modo == "grises":
                for i, w in enumerate(wedges):
                    w.set_hatch(_resolver_hatch(i, modo))
            ax.legend(
                wedges, labels, loc='center left',
                bbox_to_anchor=(1.0, 0.5),
                fontsize=5.5, frameon=False,
            )
            ax.set(aspect='equal')

            # Título y subtítulo internos
            fig.text(0.5, 0.97, titulo,
                     ha='center', va='top', fontsize=7.5, fontweight='bold', color='#1b4332')
            fig.text(0.5, 0.90, subtitulo,
                     ha='center', va='top', fontsize=6, color='#64748b', style='italic')

            plt.tight_layout(pad=0.3, rect=[0, 0, 1, 0.88])

            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=300, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return RLImage(buf, width=width_pt, height=height_pt)
        except Exception:
            return None

    @staticmethod
    def _chart_barras_clas(totales, width_pt=220, height_pt=130,
                           titulo="Categorías Funcionales", subtitulo="N.° de taxa por rol en el suelo",
                           modo="color"):
        """Barras horizontales de resumen funcional (4 categorías) con título interno."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            # Sans-serif (Arial/Helvetica) — lo que piden la mayoría de
            # revistas científicas para el texto DENTRO de las figuras;
            # DejaVu Sans (incluida con matplotlib) como respaldo si el
            # servidor no tiene Arial/Helvetica instalada.
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']

            cats   = ["Benéfico", "Fitopatógeno", "Neutral", "Sin clas."]
            keys   = ["benefico", "fitopatogeno", "neutral", "sin_clasificar"]
            clrs   = _resolver_colores(['#16a34a', '#dc2626', '#64748b', '#94a3b8'], modo)
            values = [totales.get(k, 0) for k in keys]

            fig, ax = plt.subplots(figsize=(width_pt / 72, height_pt / 72))
            fig.patch.set_facecolor('#ffffff')

            bars = ax.barh(cats, values, color=clrs, edgecolor='white', linewidth=0.6, height=0.55)
            if modo == "grises":
                for i, b in enumerate(bars):
                    b.set_hatch(_resolver_hatch(i, modo))
            ax.bar_label(bars, padding=4, fontsize=7, color='#374151', fontweight='bold')
            ax.set_xlabel("N.° de taxa", fontsize=6.5)
            ax.tick_params(axis='y', labelsize=7)
            ax.tick_params(axis='x', labelsize=6)
            ax.spines[['top', 'right']].set_visible(False)
            ax.set_title(f"{titulo}\n{subtitulo}",
                         fontsize=7.5, fontweight='bold', color='#1b4332',
                         pad=6, loc='left')

            plt.tight_layout(pad=0.4)

            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=300, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return RLImage(buf, width=width_pt, height=height_pt)
        except Exception:
            return None

    @staticmethod
    def _chart_ranked_bar_taxa(top_taxa, width_pt=440, height_pt=None,
                               titulo="Perfil de Abundancia Relativa",
                               subtitulo="Taxa ordenados de mayor a menor — color indica rol funcional",
                               modo="color"):
        """
        Barras horizontales rankeadas de top taxa, coloreadas por clasificación funcional.
        Forma estándar para perfiles de abundancia en microbiología de suelos.
        """
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            # Sans-serif (Arial/Helvetica) — lo que piden la mayoría de
            # revistas científicas para el texto DENTRO de las figuras;
            # DejaVu Sans (incluida con matplotlib) como respaldo si el
            # servidor no tiene Arial/Helvetica instalada.
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
            from matplotlib.patches import Patch

            if not top_taxa:
                return None

            CATS_ORDEN = ['benefico', 'fitopatogeno', 'neutral', 'sin_clasificar']
            CLR_MAP = dict(zip(CATS_ORDEN, _resolver_colores(
                ['#16a34a', '#dc2626', '#64748b', '#94a3b8'], modo)))
            HATCH_MAP = {cat: _resolver_hatch(i, modo) for i, cat in enumerate(CATS_ORDEN)}

            # Ordenar: menor→mayor abundancia (el de mayor abundancia queda arriba en el eje Y)
            sorted_taxa = sorted(
                top_taxa,
                key=lambda r: float(r.get("total_porcentaje", r.get("porcentaje", 0)) or 0)
            )

            nombres = [str(r.get("taxonomia", r.get("nombre", "?"))) for r in sorted_taxa]
            valores = [float(r.get("total_porcentaje", r.get("porcentaje", 0)) or 0) for r in sorted_taxa]
            clases  = [r.get("clasificacion", "sin_clasificar") for r in sorted_taxa]
            colores = [CLR_MAP.get(c, CLR_MAP['sin_clasificar']) for c in clases]

            n     = len(nombres)
            dyn_h = height_pt or min(max(n * 14 + 80, 140), 520)
            max_v = max(valores) if valores else 1

            fig, ax = plt.subplots(figsize=(width_pt / 72, dyn_h / 72))
            fig.patch.set_facecolor('#ffffff')

            bars = ax.barh(nombres, valores, color=colores, edgecolor='white', linewidth=0.5, height=0.70)
            if modo == "grises":
                for bar, cat in zip(bars, clases):
                    bar.set_hatch(HATCH_MAP.get(cat, ''))

            # Etiqueta de porcentaje fuera de la barra
            for bar, val in zip(bars, valores):
                ax.text(
                    bar.get_width() + max_v * 0.012,
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:.2f}%",
                    va='center', ha='left', fontsize=6.5, color='#374151',
                )

            ax.set_xlabel("Abundancia relativa (%)", fontsize=7)
            ax.tick_params(axis='y', labelsize=6.5)
            ax.tick_params(axis='x', labelsize=6)
            ax.spines[['top', 'right']].set_visible(False)
            ax.set_xlim(0, max_v * 1.20)

            # Título y subtítulo encima del área de plot
            ax.set_title(titulo, fontsize=8, fontweight='bold', color='#1b4332', pad=4, loc='left')
            ax.annotate(subtitulo, xy=(0, 1.01), xycoords='axes fraction',
                        fontsize=6, color='#64748b', style='italic', va='bottom')

            # Leyenda compacta
            legend_elements = [
                Patch(facecolor=CLR_MAP['benefico'], hatch=HATCH_MAP['benefico'], label='Benéfico'),
                Patch(facecolor=CLR_MAP['fitopatogeno'], hatch=HATCH_MAP['fitopatogeno'], label='Fitopatógeno'),
                Patch(facecolor=CLR_MAP['neutral'], hatch=HATCH_MAP['neutral'], label='Neutral'),
                Patch(facecolor=CLR_MAP['sin_clasificar'], hatch=HATCH_MAP['sin_clasificar'], label='Sin clasificación'),
            ]
            ax.legend(handles=legend_elements, loc='lower right',
                      fontsize=6, framealpha=0.8, ncol=2,
                      edgecolor='#e2e8f0')

            plt.tight_layout(pad=0.5)
            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=300, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return RLImage(buf, width=width_pt, height=dyn_h)
        except Exception:
            return None

    @staticmethod
    def _chart_comparativo_shannon(datos_por_muestra, width_pt=460, height_pt=170, modo="color"):
        """
        Dos subplots: Shannon H' (colores por umbral absoluto) e Índice de Salud por muestra.
        Umbrales Shannon: <1 rojo · 1-2 naranja · 2-3 amarillo · ≥3 verde.
        """
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            # Sans-serif (Arial/Helvetica) — lo que piden la mayoría de
            # revistas científicas para el texto DENTRO de las figuras;
            # DejaVu Sans (incluida con matplotlib) como respaldo si el
            # servidor no tiene Arial/Helvetica instalada.
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
            from matplotlib.patches import Patch

            if not datos_por_muestra:
                return None

            codigos  = [d["muestra"].codigo for d in datos_por_muestra]
            shannons = [float(d.get("diversidad", {}).get("shannon", 0) or 0) for d in datos_por_muestra]
            indices  = [d.get("indice_salud", 0) for d in datos_por_muestra]

            SHAN_PALETA = _resolver_colores(['#DC2626', '#F97316', '#EAB308', '#16A34A'], modo)  # bajo→alto
            SAL_PALETA  = _resolver_colores(['#dc2626', '#ca8a04', '#16a34a', '#14532d'], modo)   # crítico→excelente

            def _bucket_shannon(v):
                if v >= 3.0: return 3
                if v >= 2.0: return 2
                if v >= 1.0: return 1
                return 0

            def _bucket_indice(v):
                if v >= 80: return 3
                if v >= 65: return 2
                if v >= 50: return 1
                return 0

            shan_buckets = [_bucket_shannon(v) for v in shannons]
            sal_buckets  = [_bucket_indice(v) for v in indices]
            shan_colors  = [SHAN_PALETA[b] for b in shan_buckets]
            bar_colors   = [SAL_PALETA[b] for b in sal_buckets]

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(width_pt / 72, height_pt / 72))
            fig.patch.set_facecolor('#ffffff')

            # ── Subplot izquierdo: Shannon H' ───────────────────────────
            bars1 = ax1.bar(codigos, shannons, color=shan_colors, edgecolor='white', linewidth=0.6, width=0.55)
            if modo == "grises":
                for bar, b in zip(bars1, shan_buckets):
                    bar.set_hatch(_resolver_hatch(b, modo))
            for ref, lbl in [(1.0, "H'=1 (bajo)"), (2.0, "H'=2"), (3.0, "H'=3 (alto)")]:
                ax1.axhline(ref, color='#94a3b8', linewidth=0.7, linestyle='--', zorder=0)
                ax1.text(len(codigos) - 0.45, ref + 0.06, lbl,
                         fontsize=5, color='#94a3b8', va='bottom', ha='right')
            ax1.bar_label(ax1.containers[0], fmt='%.2f', fontsize=5.5, padding=2, color='#374151')
            ax1.set_title("Diversidad Alfa — Shannon H'",
                          fontsize=7.5, fontweight='bold', color='#1b4332', pad=4)
            ax1.set_ylabel("Índice H' (nats)", fontsize=6.5)
            ax1.tick_params(axis='x', labelsize=6, rotation=35)
            ax1.tick_params(axis='y', labelsize=6)
            ax1.spines[['top', 'right']].set_visible(False)
            # Mini leyenda de colores Shannon
            shan_leg = [
                Patch(facecolor=SHAN_PALETA[3], hatch=_resolver_hatch(3, modo), label='Alta (≥3)'),
                Patch(facecolor=SHAN_PALETA[2], hatch=_resolver_hatch(2, modo), label='Media-alta (2-3)'),
                Patch(facecolor=SHAN_PALETA[1], hatch=_resolver_hatch(1, modo), label='Media-baja (1-2)'),
                Patch(facecolor=SHAN_PALETA[0], hatch=_resolver_hatch(0, modo), label='Baja (<1)'),
            ]
            ax1.legend(handles=shan_leg, fontsize=5, framealpha=0.8,
                       ncol=2, loc='upper left', edgecolor='#e2e8f0')

            # ── Subplot derecho: Índice de Salud ────────────────────────
            bars2 = ax2.bar(codigos, indices, color=bar_colors, edgecolor='white', linewidth=0.6, width=0.55)
            if modo == "grises":
                for bar, b in zip(bars2, sal_buckets):
                    bar.set_hatch(_resolver_hatch(b, modo))
            for ref, lbl in [(50, "Crítico"), (65, "Moderado"), (80, "Bueno")]:
                ax2.axhline(ref, color='#94a3b8', linewidth=0.7, linestyle='--', zorder=0)
                ax2.text(len(codigos) - 0.45, ref + 1.5, lbl,
                         fontsize=5, color='#94a3b8', va='bottom', ha='right')
            ax2.bar_label(ax2.containers[0], fmt='%d', fontsize=5.5, padding=2, color='#374151')
            ax2.set_title("Índice de Salud del Suelo (0-100)",
                          fontsize=7.5, fontweight='bold', color='#1b4332', pad=4)
            ax2.set_ylabel("Puntuación", fontsize=6.5)
            ax2.set_ylim(0, 105)
            ax2.tick_params(axis='x', labelsize=6, rotation=35)
            ax2.tick_params(axis='y', labelsize=6)
            ax2.spines[['top', 'right']].set_visible(False)
            # Mini leyenda de niveles de salud
            sal_leg = [
                Patch(facecolor=SAL_PALETA[3], hatch=_resolver_hatch(3, modo), label='Excelente (≥80)'),
                Patch(facecolor=SAL_PALETA[2], hatch=_resolver_hatch(2, modo), label='Bueno (65-80)'),
                Patch(facecolor=SAL_PALETA[1], hatch=_resolver_hatch(1, modo), label='Moderado (50-65)'),
                Patch(facecolor=SAL_PALETA[0], hatch=_resolver_hatch(0, modo), label='Crítico (<50)'),
            ]
            ax2.legend(handles=sal_leg, fontsize=5, framealpha=0.8,
                       ncol=2, loc='upper left', edgecolor='#e2e8f0')

            plt.tight_layout(pad=0.6)
            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=300, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return RLImage(buf, width=width_pt, height=height_pt)
        except Exception:
            return None

    @staticmethod
    def _chart_barras_agrupadas_funcional(datos_por_muestra, width_pt=460, height_pt=175,
                                          titulo="Composición Funcional Comparativa",
                                          subtitulo="N.° de taxa por categoría funcional en cada muestra",
                                          modo="color"):
        """
        Barras agrupadas por clasificación funcional, una barra por muestra.
        Equivalente visual al modo multi-muestra del preview web.
        """
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            # Sans-serif (Arial/Helvetica) — lo que piden la mayoría de
            # revistas científicas para el texto DENTRO de las figuras;
            # DejaVu Sans (incluida con matplotlib) como respaldo si el
            # servidor no tiene Arial/Helvetica instalada.
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
            import numpy as np

            if not datos_por_muestra:
                return None

            codigos = [d["muestra"].codigo for d in datos_por_muestra]
            cats    = ['benefico', 'fitopatogeno', 'neutral', 'sin_clasificar']
            labels  = ['Benéfico', 'Fitopatógeno', 'Neutral', 'Sin clasificación']
            clrs    = _resolver_colores(['#16a34a', '#dc2626', '#64748b', '#94a3b8'], modo)

            x       = np.arange(len(codigos))
            n_c     = len(cats)
            w       = 0.18
            offsets = np.linspace(-(n_c - 1) * w / 2, (n_c - 1) * w / 2, n_c)

            fig, ax = plt.subplots(figsize=(width_pt / 72, height_pt / 72))
            fig.patch.set_facecolor('#ffffff')

            for i, (cat, lbl, clr, off) in enumerate(zip(cats, labels, clrs, offsets)):
                vals = [d.get("totales_clas", {}).get(cat, 0) for d in datos_por_muestra]
                if any(v > 0 for v in vals):
                    bars = ax.bar(x + off, vals, width=w, label=lbl,
                                  color=clr, edgecolor='white', linewidth=0.5,
                                  hatch=_resolver_hatch(i, modo))
                    ax.bar_label(bars, fmt='%d', fontsize=5.5, padding=2, color='#374151')

            ax.set_xticks(x)
            ax.set_xticklabels(codigos, rotation=30 if len(codigos) > 4 else 0, fontsize=7)
            ax.set_ylabel("N.° de taxa únicos", fontsize=7)
            ax.tick_params(axis='y', labelsize=6)
            ax.spines[['top', 'right']].set_visible(False)
            ax.set_title(titulo, fontsize=8, fontweight='bold', color='#1b4332', pad=4, loc='left')
            ax.annotate(subtitulo, xy=(0, 1.01), xycoords='axes fraction',
                        fontsize=6, color='#64748b', style='italic', va='bottom')
            ax.legend(fontsize=6.5, framealpha=0.8, ncol=2, loc='upper right',
                      edgecolor='#e2e8f0')

            plt.tight_layout(pad=0.5)
            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=300, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return RLImage(buf, width=width_pt, height=height_pt)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # PDF individual
    # ------------------------------------------------------------------

    @staticmethod
    def generar_pdf_individual(datos) -> bytes:
        """
        Genera reporte PDF individual de A4 con 6 páginas.
        datos keys: muestra, muestras, top_taxa, todos_taxa, diversidad,
                    detalle_clas, totales_clas, indice_salud, nivel_salud,
                    tipo, nivel, top_n, usuario
        """
        muestra      = datos.get("muestra")
        top_taxa     = datos.get("top_taxa", [])
        todos_taxa   = datos.get("todos_taxa", [])
        diversidad   = datos.get("diversidad", {})
        detalle_clas = datos.get("detalle_clas", {})
        totales_clas = datos.get("totales_clas", {})
        indice_salud = datos.get("indice_salud", 0)
        nivel_salud  = datos.get("nivel_salud", "MODERADO")
        tipo         = datos.get("tipo", "16S")
        nivel        = datos.get("nivel", "genus")
        top_n        = datos.get("top_n", 25)
        usuario      = datos.get("usuario")
        modo         = datos.get("modo_color", "color")

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=40, leftMargin=40,
            topMargin=36, bottomMargin=36,
        )
        S = _get_styles()
        contenido = []

        # Valores de muestra seguros
        def _safe(obj, attr, default="N/A"):
            val = getattr(obj, attr, None) if obj else None
            return str(val) if val not in (None, "") else default

        cultivo_nom = (muestra.cultivo.nombre if muestra and getattr(muestra, 'cultivo', None) else "N/A")
        var_nom     = (muestra.variedad_clon.nombre if muestra and getattr(muestra, 'variedad_clon', None) else "N/A")
        fecha_gen   = datetime.now().strftime("%d/%m/%Y %H:%M")
        analista    = str(usuario) if usuario else "Sistema"
        marcador_lbl = "BACTERIA 16S" if tipo == "16S" else "HONGOS ITS"

        ancho_util = A4[0] - 80  # 455 pt aprox

        # ── helpers locales ────────────────────────────────────────────────
        shannon_v = float(diversidad.get("shannon", 0.0) or 0.0)
        simpson_v = float(diversidad.get("simpson", 0.0) or 0.0)
        equit_v   = float(diversidad.get("equitatividad", 0.0) or 0.0)
        riqueza_v = diversidad.get("riqueza", len(todos_taxa))

        def _shannon_color(v):
            if v >= 3.0: return "#16A34A"
            if v >= 2.0: return "#CA8A04"
            if v >= 1.0: return "#EA580C"
            return "#DC2626"

        # ================================================================
        # PÁGINA 1 — Portada
        # ================================================================
        # Banner superior de institución (ancho completo)
        banner_rows = [
            [Paragraph(
                "<font size='16'><b>BioMicro UTC</b></font>",
                S["titulo"],
            )],
            [Paragraph(
                "Universidad Técnica de Cotopaxi · Laboratorio de Bioinformática de Suelos",
                S["subtitle"],
            )],
        ]
        t_banner = Table(banner_rows, colWidths=[ancho_util])
        t_banner.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), _C_PRIMARY),
            ('TOPPADDING',    (0, 0), (-1, -1), 22),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 22),
            ('BOTTOMPADDING', (0, 0), (0, 0), 4),
            ('LEFTPADDING',   (0, 0), (-1, -1), 18),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 18),
        ]))
        contenido.append(t_banner)

        # Franja de tipo de reporte (verde medio)
        tipo_style = ParagraphStyle('TipoBanner', parent=S["body_sm"],
            textColor=colors.white, fontName='Helvetica-Bold', fontSize=9)
        t_tipo = Table([[Paragraph(
            f"  REPORTE INDIVIDUAL DE SALUD MICROBIOLÓGICA · MARCADOR {marcador_lbl}",
            tipo_style,
        )]], colWidths=[ancho_util])
        t_tipo.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), _C_SECONDARY),
            ('TOPPADDING',    (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING',   (0, 0), (-1, -1), 18),
        ]))
        contenido.append(t_tipo)
        contenido.append(Spacer(1, 20))

        # Título del reporte
        title_style = ParagraphStyle('ReportTitle', parent=S["body"],
            fontSize=17, fontName='Helvetica-Bold',
            textColor=_C_PRIMARY, leading=21)
        contenido.append(Paragraph("Análisis de Comunidad Microbiana de Suelo", title_style))
        contenido.append(Spacer(1, 4))
        sub_style = ParagraphStyle('ReportSub', parent=S["body_sm"],
            textColor=colors.HexColor('#64748b'), fontSize=9.5)
        contenido.append(Paragraph(
            f"Nivel taxonómico: <b>{nivel.capitalize()}</b> · "
            f"Top <b>{top_n}</b> taxa más abundantes · {fecha_gen}",
            sub_style,
        ))
        contenido.append(Spacer(1, 16))

        # Tabla de identificación de la muestra (etiqueta oscura | valor claro)
        lbl_col  = ancho_util * 0.28
        val_col  = ancho_util * 0.22
        info_rows = [
            ("Código de muestra", _safe(muestra, "codigo"),
             "Cultivo", cultivo_nom),
            ("Variedad / Clon", var_nom,
             "Tipo de muestra", _safe(muestra, "tipo_muestra")),
            ("Localidad", _safe(muestra, "localidad"),
             "Finca / Lote", _safe(muestra, "finca_lote")),
            ("Altitud (m.s.n.m.)", _safe(muestra, "altitud", "—"),
             "Fecha de registro", _safe(muestra, "fecha_registro")),
        ]
        tbl_info_data = [
            [Paragraph(f"<b>{r[0]}</b>", S["body_sm"]), Paragraph(r[1], S["body_sm"]),
             Paragraph(f"<b>{r[2]}</b>", S["body_sm"]), Paragraph(r[3], S["body_sm"])]
            for r in info_rows
        ]
        t_info = Table(tbl_info_data, colWidths=[lbl_col, val_col, lbl_col, val_col])
        t_info.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (0, -1), colors.HexColor('#e8f5ef')),
            ('BACKGROUND',    (2, 0), (2, -1), colors.HexColor('#e8f5ef')),
            ('BACKGROUND',    (1, 0), (1, -1), colors.white),
            ('BACKGROUND',    (3, 0), (3, -1), colors.white),
            ('BOX',           (0, 0), (-1, -1), 1, _C_BORDER),
            ('INNERGRID',     (0, 0), (-1, -1), 0.4, _C_INNER),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 7),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_info)
        contenido.append(Spacer(1, 12))

        # Barra de metadatos del análisis
        meta_style = ParagraphStyle('MetaBar', parent=S["body_sm"],
            textColor=colors.HexColor('#374151'), fontSize=8.5)
        t_meta = Table([[
            Paragraph(f"<b>Analista:</b> {analista}", meta_style),
            Paragraph(f"<b>Marcador:</b> {marcador_lbl}", meta_style),
            Paragraph(f"<b>Nivel:</b> {nivel.capitalize()}", meta_style),
            Paragraph(f"<b>Generado:</b> {fecha_gen}", meta_style),
        ]], colWidths=[ancho_util / 4] * 4)
        t_meta.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#f1f5f9')),
            ('BOX',           (0, 0), (-1, -1), 0.5, _C_BORDER),
            ('INNERGRID',     (0, 0), (-1, -1), 0.4, colors.HexColor('#e2e8f0')),
            ('TOPPADDING',    (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING',   (0, 0), (-1, -1), 8),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_meta)
        contenido.append(Spacer(1, 16))

        # Nota al pie de portada
        contenido.append(HRFlowable(width=ancho_util, thickness=0.5,
                                    color=colors.HexColor('#cbd5e1')))
        contenido.append(Spacer(1, 6))
        contenido.append(Paragraph(
            "Este reporte ha sido generado automáticamente por el sistema BioMicro UTC. "
            "Los resultados deben ser interpretados por un profesional en microbiología de suelos.",
            S["muted"],
        ))

        contenido.append(PageBreak())

        # ================================================================
        # PÁGINA 2 — Resumen Ejecutivo
        # ================================================================
        contenido.append(_seccion_hdr("RESUMEN EJECUTIVO", ancho_util, S, numero=1))
        contenido.append(Spacer(1, 14))

        # ── Tarjeta Índice de Salud ─────────────────────────────────────
        nivel_color_hex = _NIVEL_COLORES.get(nivel_salud, "#64748b")
        nivel_color_rl  = colors.HexColor(nivel_color_hex)

        _barra_util = ancho_util * 0.75 - 24
        _fill_w  = max(_barra_util * (indice_salud / 100), 1.0)
        _empty_w = max(_barra_util - _fill_w, 1.0)
        t_bar = Table([["", ""]], colWidths=[_fill_w, _empty_w])
        t_bar.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (0, 0), nivel_color_rl),
            ('BACKGROUND',    (1, 0), (1, 0), colors.HexColor('#e2e8f0')),
            ('LEFTPADDING',   (0, 0), (-1, -1), 0),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
            ('TOPPADDING',    (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('ROWHEIGHT',     (0, 0), (-1, -1), 12),
        ]))

        salud_num_style = ParagraphStyle('SaludN', parent=S["body"],
            fontSize=40, fontName='Helvetica-Bold',
            textColor=nivel_color_rl, alignment=TA_CENTER)
        salud_lbl_style = ParagraphStyle('SaludL', parent=S["body"],
            fontSize=13, fontName='Helvetica-Bold', textColor=nivel_color_rl)
        salud_sub_style = ParagraphStyle('SaludS', parent=S["body_sm"],
            textColor=colors.HexColor('#64748b'))

        barra_data = [[
            Paragraph(str(indice_salud), salud_num_style),
            Table(
                [[Paragraph(f"<b>{nivel_salud}</b>", salud_lbl_style)],
                 [Paragraph("Índice de Salud del Suelo  (escala 0 – 100)", salud_sub_style)],
                 [Spacer(1, 4)],
                 [t_bar]],
                colWidths=[ancho_util * 0.70],
            ),
        ]]
        t_salud = Table(barra_data, colWidths=[ancho_util * 0.20, ancho_util * 0.80])
        t_salud.setStyle(TableStyle([
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING',   (0, 0), (-1, -1), 14),
            ('TOPPADDING',    (0, 0), (-1, -1), 14),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
            ('BOX',           (0, 0), (-1, -1), 2, nivel_color_rl),
            ('BACKGROUND',    (0, 0), (0, 0), colors.HexColor('#f0fdf4')),
            ('BACKGROUND',    (1, 0), (1, 0), colors.white),
        ]))
        contenido.append(t_salud)
        contenido.append(Spacer(1, 12))

        # ── Fila de 4 KPI tiles de diversidad ──────────────────────────
        shan_color = _shannon_color(shannon_v)
        shan_nivel = (
            "Alta (H'≥3)" if shannon_v >= 3 else
            "Media-alta" if shannon_v >= 2 else
            "Media-baja" if shannon_v >= 1 else "Baja (H'<1)"
        )
        kpi_div = _kpi_tiles([
            {"val": str(riqueza_v),     "lbl": "Riqueza (S)",   "color": "#185FA5", "sub": "Taxa detectados"},
            {"val": f"{shannon_v:.3f}", "lbl": "Shannon H'",    "color": shan_color, "sub": shan_nivel},
            {"val": f"{simpson_v:.3f}", "lbl": "Simpson (1-D)", "color": "#6B4E9E", "sub": "Gini-Simpson"},
            {"val": f"{equit_v:.3f}",   "lbl": "Pielou (J')",  "color": "#BA7517", "sub": "Equitatividad"},
        ], ancho_util, S)
        contenido.append(kpi_div)
        contenido.append(Spacer(1, 10))

        # ── Fila de 4 KPI tiles de clasificación funcional ─────────────
        kpi_func = _kpi_tiles([
            {"val": str(totales_clas.get("benefico", 0)),      "lbl": "Benéficos",     "color": "#16A34A", "sub": "Taxa"},
            {"val": str(totales_clas.get("fitopatogeno", 0)),  "lbl": "Fitopatógenos", "color": "#DC2626", "sub": "Taxa"},
            {"val": str(totales_clas.get("neutral", 0)),       "lbl": "Neutrales",     "color": "#64748b", "sub": "Taxa"},
            {"val": str(totales_clas.get("sin_clasificar", 0)),"lbl": "Sin clasificación", "color": "#94A3B8", "sub": "Taxa"},
        ], ancho_util, S)
        contenido.append(kpi_func)
        contenido.append(Spacer(1, 12))

        # ── Conclusión ─────────────────────────────────────────────────
        cod_muestra = _safe(muestra, "codigo", "la muestra seleccionada")
        conclusion = (
            f"La muestra <b>{cod_muestra}</b> del cultivo <b>{cultivo_nom}</b> presenta un "
            f"Índice de Salud del Suelo de <b>{indice_salud}/100</b> ({nivel_salud}). "
            f"El análisis con marcador <b>{marcador_lbl}</b> a nivel taxonómico de <b>{nivel}</b> detectó "
            f"<b>{riqueza_v}</b> taxa únicos con diversidad Shannon H' = <b>{shannon_v:.3f}</b> ({shan_nivel}). "
            f"La comunidad incluye <b>{totales_clas.get('benefico', 0)}</b> taxa benéficos y "
            f"<b>{totales_clas.get('fitopatogeno', 0)}</b> fitopatógenos potenciales."
        )
        contenido.append(Paragraph(conclusion, S["body"]))

        contenido.append(PageBreak())

        # ================================================================
        # PÁGINA 3 — Perfil Taxonómico
        # ================================================================
        contenido.append(_seccion_hdr("PERFIL DE ABUNDANCIA RELATIVA", ancho_util, S, numero=2))
        contenido.append(Spacer(1, 10))

        # ── Gráfica rankeada (principal) ────────────────────────────────
        chart_ranked = ExportService._chart_ranked_bar_taxa(
            top_taxa, width_pt=ancho_util,
            titulo=f"Perfil de Abundancia Relativa — Top {top_n} {nivel.capitalize()}",
            subtitulo=f"Marcador {tipo} · Muestra {cod_muestra} · Ordenado de mayor a menor abundancia relativa",
            modo=modo,
        )
        if chart_ranked:
            contenido.append(chart_ranked)
            contenido.append(Paragraph(
                f"Figura 1. Top {top_n} {nivel} detectados en la muestra {cod_muestra} "
                f"(marcador {tipo}). Barras coloreadas por rol funcional: "
                "verde = benéfico · rojo = fitopatógeno · gris = neutral · gris claro = sin clasificación.",
                S["caption"],
            ))

        # ── Donut composición + barras funcionales (fila complementaria) ─
        chart_donut = ExportService._chart_donut_taxa(
            top_taxa, width_pt=200, height_pt=158,
            titulo="Composición Taxonómica",
            subtitulo=f"Top 10 {nivel} · muestra {cod_muestra}",
            modo=modo,
        )
        chart_clas  = ExportService._chart_barras_clas(
            totales_clas, width_pt=200, height_pt=128,
            titulo="Categorías Funcionales",
            subtitulo=f"N.° taxa por rol · muestra {cod_muestra}",
            modo=modo,
        )
        if chart_donut or chart_clas:
            cap_d = Paragraph("Composición relativa (top 10 taxa)", S["caption"])
            cap_c = Paragraph("N.° taxa por categoría funcional", S["caption"])
            chart_cells = [
                Table([[chart_donut or Spacer(1,1)], [cap_d]], colWidths=[ancho_util * 0.52]),
                Table([[chart_clas  or Spacer(1,1)], [cap_c]], colWidths=[ancho_util * 0.48]),
            ]
            t_charts = Table([chart_cells], colWidths=[ancho_util * 0.52, ancho_util * 0.48])
            t_charts.setStyle(TableStyle([
                ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
                ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
                ('TOPPADDING',    (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            contenido.append(t_charts)
            contenido.append(Spacer(1, 8))

        # ── Tabla Top N taxa ────────────────────────────────────────────
        def _clas_badge(clas):
            if clas == 'benefico':     return Paragraph("<font color='#16a34a'>&#9679; Benéfico</font>",    S["body_sm"])
            if clas == 'fitopatogeno': return Paragraph("<font color='#dc2626'>&#9679; Fitopatógeno</font>", S["body_sm"])
            if clas == 'neutral':      return Paragraph("<font color='#64748b'>&#9675; Neutral</font>",      S["body_sm"])
            return Paragraph("<font color='#94a3b8'>· Sin clas.</font>", S["body_sm"])

        taxa_rows = [[
            Paragraph("<b>#</b>",           S["th"]),
            Paragraph("<b>Taxón</b>",        S["th"]),
            Paragraph("<b>Reads</b>",        S["th"]),
            Paragraph("<b>Abundancia %</b>", S["th"]),
            Paragraph("<b>Rol funcional</b>",S["th"]),
        ]]
        for i, r in enumerate(top_taxa, 1):
            taxa_rows.append([
                Paragraph(str(i), S["body_sm"]),
                Paragraph(f"<i>{r.get('taxonomia', r.get('nombre','?'))}</i>", S["body_sm"]),
                Paragraph(str(r.get("total_hits", r.get("hits", 0))), S["body_sm"]),
                Paragraph(f"{r.get('total_porcentaje', r.get('porcentaje', 0)):.2f}%", S["body_sm"]),
                _clas_badge(r.get("clasificacion", "sin_clasificar")),
            ])

        col_taxa = [26, ancho_util * 0.40, 55, 75, 100]
        t_taxa = Table(taxa_rows, colWidths=col_taxa, repeatRows=1)
        t_taxa.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0),  _C_PRIMARY),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#f8faf9')]),
            ('INNERGRID',     (0, 0), (-1, -1), 0.4, _C_INNER),
            ('BOX',           (0, 0), (-1, -1), 1,   _C_BORDER),
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN',         (0, 0), (0, -1),  'CENTER'),
            ('ALIGN',         (2, 1), (3, -1),  'RIGHT'),
        ]))
        contenido.append(t_taxa)

        contenido.append(PageBreak())

        # ================================================================
        # PÁGINA 4 — Diversidad Alfa
        # ================================================================
        contenido.append(_seccion_hdr("DIVERSIDAD ALFA", ancho_util, S, numero=3))
        contenido.append(Spacer(1, 14))

        # KPI tiles con los 4 índices (con color Shannon)
        contenido.append(_kpi_tiles([
            {"val": str(riqueza_v),     "lbl": "Riqueza (S)",   "color": "#185FA5", "sub": "Taxa únicos"},
            {"val": f"{shannon_v:.4f}", "lbl": "Shannon H'",    "color": _shannon_color(shannon_v), "sub": shan_nivel},
            {"val": f"{simpson_v:.4f}", "lbl": "Simpson (1-D)", "color": "#6B4E9E", "sub": "Gini-Simpson"},
            {"val": f"{equit_v:.4f}",   "lbl": "Pielou (J')",  "color": "#BA7517", "sub": "Equitatividad"},
        ], ancho_util, S))
        contenido.append(Spacer(1, 12))

        # Tabla de interpretación con barra de progreso
        _bar_total = max(ancho_util * 0.28 - 14, 10.0)

        def _interp_bar(valor, max_val, color_hex):
            pct    = min(max(float(valor or 0), 0.0) / max(float(max_val or 1), 1e-9), 1.0)
            fill_w = max(_bar_total * pct, 1.0)
            rest_w = max(_bar_total * (1.0 - pct), 1.0)
            t = Table([["", ""]], colWidths=[fill_w, rest_w])
            t.setStyle(TableStyle([
                ('BACKGROUND',    (0, 0), (0, 0), colors.HexColor(color_hex)),
                ('BACKGROUND',    (1, 0), (1, 0), colors.HexColor('#e2e8f0')),
                ('LEFTPADDING',   (0, 0), (-1, -1), 0),
                ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
                ('TOPPADDING',    (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ('ROWHEIGHT',     (0, 0), (-1, -1), 9),
            ]))
            return t

        div_rows = [
            [Paragraph("<b>Métrica</b>",        S["th"]),
             Paragraph("<b>Valor</b>",           S["th"]),
             Paragraph("<b>Escala</b>",          S["th"]),
             Paragraph("<b>Interpretación</b>",  S["th"])],
            [Paragraph("Riqueza de taxa (S)",    S["body_sm"]),
             Paragraph(str(riqueza_v),            S["body_sm"]),
             _interp_bar(riqueza_v, max(riqueza_v, 1), '#185FA5'),
             Paragraph("Alta >100 · Moderada >30 · Baja ≤30", S["body_sm"])],
            [Paragraph("Shannon H'",             S["body_sm"]),
             Paragraph(f"{shannon_v:.4f}",        S["body_sm"]),
             _interp_bar(shannon_v, 5.0, _shannon_color(shannon_v)),
             Paragraph(
                "Alta (H'≥3)" if shannon_v >= 3 else
                "Media-alta (2≤H'<3)" if shannon_v >= 2 else
                "Media-baja (1≤H'<2)" if shannon_v >= 1 else "Baja (H'<1)",
                S["body_sm"])],
            [Paragraph("Simpson (1-D)",          S["body_sm"]),
             Paragraph(f"{simpson_v:.4f}",        S["body_sm"]),
             _interp_bar(simpson_v, 1.0, '#6B4E9E'),
             Paragraph(
                "Buena equidad >0.7 · Moderada >0.4 · Dominancia marcada",
                S["body_sm"])],
            [Paragraph("Equitatividad Pielou J'",S["body_sm"]),
             Paragraph(f"{equit_v:.4f}",          S["body_sm"]),
             _interp_bar(equit_v, 1.0, '#BA7517'),
             Paragraph(
                "Equilibrada >0.7 · Media >0.4 · Dominancia fuerte",
                S["body_sm"])],
        ]
        col_div = [ancho_util * 0.28, 58, ancho_util * 0.28, ancho_util * 0.30]
        t_div = Table(div_rows, colWidths=col_div, repeatRows=1)
        t_div.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0),  _C_PRIMARY),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#f8faf9')]),
            ('INNERGRID',     (0, 0), (-1, -1), 0.4, _C_INNER),
            ('BOX',           (0, 0), (-1, -1), 1,   _C_BORDER),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_div)
        contenido.append(Spacer(1, 12))

        if shannon_v >= 3.0:
            div_concl = "La comunidad microbiana presenta alta diversidad alfa (H'≥3), indicando un ecosistema de suelo equilibrado, resiliente y funcionalmente diverso."
        elif shannon_v >= 2.0:
            div_concl = "Se observa diversidad alfa media-alta (2≤H'<3). La comunidad microbiana es funcional y bien distribuida; puede beneficiarse de prácticas agroecológicas de mantenimiento."
        elif shannon_v >= 1.0:
            div_concl = "La diversidad alfa es media-baja (1≤H'<2), con distribución irregular entre taxa. Se recomienda monitorear evolución y evaluar prácticas de mejora del suelo."
        else:
            div_concl = "La diversidad alfa es baja (H'<1), sugiriendo dominancia marcada de pocos taxa o condiciones de estrés edáfico. Se recomienda intervención agronómica."

        t_concl = Table([[Paragraph(div_concl, S["body"])]], colWidths=[ancho_util])
        t_concl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#f0fdf4')),
            ('BOX',           (0, 0), (-1, -1), 1, colors.HexColor('#86efac')),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
            ('TOPPADDING',    (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        contenido.append(t_concl)

        contenido.append(PageBreak())

        # ================================================================
        # PÁGINA 5 — Perfil Funcional
        # ================================================================
        contenido.append(_seccion_hdr("PERFIL FUNCIONAL DE LA COMUNIDAD MICROBIANA", ancho_util, S, numero=4))
        contenido.append(Spacer(1, 14))

        # KPI tiles funcionales
        contenido.append(_kpi_tiles([
            {"val": str(totales_clas.get("benefico", 0)),      "lbl": "Benéficos",     "color": "#16A34A", "sub": "Promotores de crecimiento"},
            {"val": str(totales_clas.get("fitopatogeno", 0)),  "lbl": "Fitopatógenos", "color": "#DC2626", "sub": "Riesgo fitosanitario"},
            {"val": str(totales_clas.get("neutral", 0)),       "lbl": "Neutrales",     "color": "#64748b", "sub": "Sin función definida"},
            {"val": str(totales_clas.get("sin_clasificar", 0)),"lbl": "Sin clasificación", "color": "#94A3B8", "sub": "No en catálogo"},
        ], ancho_util, S))
        contenido.append(Spacer(1, 12))

        # Tabla organismos benéficos
        beneficos = detalle_clas.get("benefico", [])[:20]
        if beneficos:
            contenido.append(Paragraph("Organismos Benéficos", S["h3"]))
            ben_rows = [[
                Paragraph("<b>Taxón</b>",          S["th"]),
                Paragraph("<b>Abundancia %</b>",   S["th"]),
                Paragraph("<b>Función agronómica</b>", S["th"]),
                Paragraph("<b>Referencia</b>",     S["th"]),
            ]]
            for item in beneficos:
                ben_rows.append([
                    Paragraph(f"<i>{item.get('nombre','')}</i>", S["body_sm"]),
                    Paragraph(f"{item.get('porcentaje', 0):.2f}%", S["body_sm"]),
                    Paragraph(str(item.get("descripcion", ""))[:130], S["body_sm"]),
                    Paragraph(str(item.get("referencia", ""))[:80], S["body_sm"]),
                ])
            col_ben = [ancho_util * 0.26, 65, ancho_util * 0.37, ancho_util * 0.23]
            t_ben = Table(ben_rows, colWidths=col_ben, repeatRows=1)
            t_ben.setStyle(TableStyle([
                ('BACKGROUND',    (0, 0), (-1, 0),  _C_BEN),
                ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#f0fdf4')]),
                ('INNERGRID',     (0, 0), (-1, -1), 0.4, _C_INNER),
                ('BOX',           (0, 0), (-1, -1), 1,   _C_BORDER),
                ('TOPPADDING',    (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING',   (0, 0), (-1, -1), 5),
                ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ]))
            contenido.append(t_ben)
            contenido.append(Spacer(1, 10))

        # Tabla fitopatógenos
        fitopatogenos = detalle_clas.get("fitopatogeno", [])[:15]
        if fitopatogenos:
            contenido.append(Paragraph("Fitopatógenos Potenciales", S["h3"]))
            fito_rows = [[
                Paragraph("<b>Taxón</b>",        S["th"]),
                Paragraph("<b>Abundancia %</b>", S["th"]),
                Paragraph("<b>Riesgo</b>",       S["th"]),
                Paragraph("<b>Referencia</b>",   S["th"]),
            ]]
            for item in fitopatogenos:
                fito_rows.append([
                    Paragraph(f"<i>{item.get('nombre','')}</i>", S["body_sm"]),
                    Paragraph(f"{item.get('porcentaje', 0):.2f}%", S["body_sm"]),
                    Paragraph(str(item.get("descripcion", ""))[:130], S["body_sm"]),
                    Paragraph(str(item.get("referencia", ""))[:80], S["body_sm"]),
                ])
            col_fito = [ancho_util * 0.26, 65, ancho_util * 0.37, ancho_util * 0.23]
            t_fito = Table(fito_rows, colWidths=col_fito, repeatRows=1)
            t_fito.setStyle(TableStyle([
                ('BACKGROUND',    (0, 0), (-1, 0),  _C_FITO),
                ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#fff1f2')]),
                ('INNERGRID',     (0, 0), (-1, -1), 0.4, _C_INNER),
                ('BOX',           (0, 0), (-1, -1), 1,   _C_BORDER),
                ('TOPPADDING',    (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING',   (0, 0), (-1, -1), 5),
                ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ]))
            contenido.append(t_fito)
            contenido.append(Spacer(1, 10))

        # Neutrales como lista legible
        neutrales = detalle_clas.get("neutral", [])[:30]
        if neutrales:
            contenido.append(Paragraph("Organismos Neutrales", S["h3"]))
            noms = ", ".join(f"<i>{n.get('nombre','?')}</i>" for n in neutrales)
            contenido.append(Paragraph(noms, S["body_sm"]))

        contenido.append(PageBreak())

        # ================================================================
        # PÁGINA 6 — Trazabilidad
        # ================================================================
        contenido.append(_seccion_hdr("TRAZABILIDAD Y NOTA METODOLÓGICA", ancho_util, S, numero=5))
        contenido.append(Spacer(1, 12))

        obs = _safe(muestra, "observaciones", "")
        if obs and obs != "N/A":
            t_obs = Table([[Paragraph(f"<b>Observaciones:</b> {obs}", S["body_sm"])]], colWidths=[ancho_util])
            t_obs.setStyle(TableStyle([
                ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#fefce8')),
                ('BOX',           (0, 0), (-1, -1), 0.5, colors.HexColor('#fde68a')),
                ('LEFTPADDING',   (0, 0), (-1, -1), 10),
                ('TOPPADDING',    (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ]))
            contenido.append(t_obs)
            contenido.append(Spacer(1, 10))

        marcador_txt = "16S rRNA" if tipo == "16S" else "ITS (Internal Transcribed Spacer)"
        total_cat    = totales_clas.get('benefico',0) + totales_clas.get('fitopatogeno',0) + totales_clas.get('neutral',0)
        nota_meto = (
            f"Marcador molecular: <b>{marcador_txt}</b> · Nivel: <b>{nivel}</b> · "
            f"Taxa únicos detectados: <b>{len(todos_taxa)}</b> · "
            f"Taxa catalogados: <b>{total_cat}</b> de {len(todos_taxa)}.<br/><br/>"
            f"La diversidad alfa se calculó con Shannon-Wiener (H') y Simpson (1–D). "
            f"El Índice de Salud del Suelo integra la proporción benéfico/fitopatógeno (70%) y "
            f"la diversidad normalizada Shannon/3.5 (30%). "
            f"Plataforma: BioMicro UTC — {fecha_gen}."
        )
        t_nota = Table([[Paragraph(nota_meto, S["body_sm"])]], colWidths=[ancho_util])
        t_nota.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), _C_LIGHT),
            ('BOX',           (0, 0), (-1, -1), 0.5, _C_BORDER),
            ('LEFTPADDING',   (0, 0), (-1, -1), 12),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 12),
            ('TOPPADDING',    (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        contenido.append(t_nota)
        contenido.append(Spacer(1, 14))

        contenido.append(Paragraph(
            "<i>Reporte técnico automatizado — BioMicro UTC. "
            "Los resultados deben ser interpretados por un profesional calificado en microbiología de suelos. "
            "Universidad Técnica de Cotopaxi · Laboratorio de Bioinformática de Suelos.</i>",
            S["italic"],
        ))

        doc.build(contenido, onFirstPage=_pdf_footer, onLaterPages=_pdf_footer)
        buffer.seek(0)
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # PDF comparativo
    # ------------------------------------------------------------------

    @staticmethod
    def generar_pdf_comparativo(datos) -> bytes:
        """
        Genera reporte PDF comparativo de A4 con 5 páginas.
        datos keys: muestras, datos_por_muestra, top_taxa, diversidad,
                    totales_clas, indice_salud, nivel_salud, tipo, nivel,
                    top_n, usuario
        """
        muestras          = datos.get("muestras", [])
        datos_por_muestra = datos.get("datos_por_muestra", [])
        top_taxa          = datos.get("top_taxa", [])
        todos_taxa        = datos.get("todos_taxa", [])
        diversidad        = datos.get("diversidad", {})
        totales_clas      = datos.get("totales_clas", {})
        tipo              = datos.get("tipo", "16S")
        nivel             = datos.get("nivel", "genus")
        usuario           = datos.get("usuario")
        modo              = datos.get("modo_color", "color")

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=40, leftMargin=40,
            topMargin=36, bottomMargin=36,
        )
        S = _get_styles()
        contenido = []
        ancho_util = A4[0] - 80
        fecha_gen  = datetime.now().strftime("%d/%m/%Y %H:%M")
        analista   = str(usuario) if usuario else "Sistema"
        marcador_lbl = "BACTERIA 16S" if tipo == "16S" else "HONGOS ITS"

        # ================================================================
        # PORTADA — Comparativo
        # ================================================================
        # Banda superior oscura
        t_banner = Table([[Paragraph(
            "<font color='#ffffff'><b>BioMicro UTC</b></font>",
            S["titulo"],
        )]], colWidths=[ancho_util])
        t_banner.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), _C_PRIMARY),
            ('TOPPADDING',    (0, 0), (-1, -1), 16),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 16),
            ('LEFTPADDING',   (0, 0), (-1, -1), 16),
        ]))
        contenido.append(t_banner)

        # Franja tipo comparativo
        t_franja = Table([[Paragraph(
            f"<font color='#ffffff'>Análisis Comparativo  ·  {marcador_lbl}  ·  {len(muestras)} muestras</font>",
            S["h2"],
        )]], colWidths=[ancho_util])
        t_franja.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#0d7a5f')),
            ('TOPPADDING',    (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING',   (0, 0), (-1, -1), 16),
        ]))
        contenido.append(t_franja)
        contenido.append(Spacer(1, 16))

        contenido.append(Paragraph(
            "REPORTE COMPARATIVO DE COMUNIDADES MICROBIANAS DE SUELO",
            S["titulo"],
        ))
        contenido.append(Paragraph(
            "Universidad Técnica de Cotopaxi — Laboratorio de Bioinformática de Suelos",
            S["subtitle"],
        ))
        contenido.append(Spacer(1, 20))

        # Tabla de muestras incluidas
        muestras_hdr = [[
            Paragraph("<b>Código</b>",   S["th_dark"]),
            Paragraph("<b>Cultivo</b>",  S["th_dark"]),
            Paragraph("<b>Variedad</b>", S["th_dark"]),
            Paragraph("<b>Localidad</b>",S["th_dark"]),
            Paragraph("<b>Finca/Lote</b>",S["th_dark"]),
            Paragraph("<b>Altitud</b>",  S["th_dark"]),
        ]]
        for i, m in enumerate(muestras):
            cult = m.cultivo.nombre if getattr(m, 'cultivo', None) else "N/A"
            var  = m.variedad_clon.nombre if getattr(m, 'variedad_clon', None) else "N/A"
            bg_row = colors.white if i % 2 == 0 else colors.HexColor('#f0fdf4')
            muestras_hdr.append([
                Paragraph(str(m.codigo), S["body_sm"]),
                Paragraph(cult,          S["body_sm"]),
                Paragraph(var,           S["body_sm"]),
                Paragraph(str(getattr(m, 'localidad',   'N/A') or 'N/A'), S["body_sm"]),
                Paragraph(str(getattr(m, 'finca_lote',  'N/A') or 'N/A'), S["body_sm"]),
                Paragraph(str(getattr(m, 'altitud',     'N/A') or 'N/A'), S["body_sm"]),
            ])
        col_m = [80, 80, 80, ancho_util * 0.22, ancho_util * 0.18, 50]
        t_muestras = Table(muestras_hdr, colWidths=col_m, repeatRows=1)
        t_muestras.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0),  _C_PRIMARY),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#f0fdf4')]),
            ('INNERGRID',     (0, 0), (-1, -1), 0.4, _C_INNER),
            ('BOX',           (0, 0), (-1, -1), 1,   _C_BORDER),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_muestras)
        contenido.append(Spacer(1, 14))

        # Barra de metadatos (4 celdas)
        meta_bar = Table([[
            Table([[Paragraph("Analista",  S["kpi_lbl"])], [Paragraph(analista,          S["label"])]], colWidths=[(ancho_util/4)-2]),
            Table([[Paragraph("Marcador",  S["kpi_lbl"])], [Paragraph(marcador_lbl,       S["label"])]], colWidths=[(ancho_util/4)-2]),
            Table([[Paragraph("Nivel",     S["kpi_lbl"])], [Paragraph(nivel.capitalize(), S["label"])]], colWidths=[(ancho_util/4)-2]),
            Table([[Paragraph("Generado",  S["kpi_lbl"])], [Paragraph(fecha_gen,          S["label"])]], colWidths=[(ancho_util/4)-2]),
        ]], colWidths=[ancho_util/4] * 4)
        meta_bar.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#f1f5f9')),
            ('BOX',           (0, 0), (-1, -1), 0.5, _C_BORDER),
            ('INNERGRID',     (0, 0), (-1, -1), 0.5, _C_INNER),
            ('TOPPADDING',    (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING',   (0, 0), (-1, -1), 12),
            ('ALIGN',         (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(meta_bar)

        contenido.append(PageBreak())

        # ================================================================
        # PÁGINA 2 — Cuadro comparativo de salud
        # ================================================================
        contenido.append(_seccion_hdr("CUADRO COMPARATIVO DE SALUD DEL SUELO", ancho_util, S, numero=1))
        contenido.append(Spacer(1, 14))

        # Ordenar por indice_salud desc
        sorted_dpm = sorted(datos_por_muestra, key=lambda x: x.get("indice_salud", 0), reverse=True)

        comp_hdr = [[
            Paragraph("<b>Muestra</b>",       S["th_dark"]),
            Paragraph("<b>Índice Salud</b>",  S["th_dark"]),
            Paragraph("<b>Nivel</b>",          S["th_dark"]),
            Paragraph("<b>Taxa</b>",           S["th_dark"]),
            Paragraph("<b>Shannon H'</b>",     S["th_dark"]),
            Paragraph("<b>Benéficos</b>",      S["th_dark"]),
            Paragraph("<b>Fitopatógenos</b>",  S["th_dark"]),
        ]]
        for d in sorted_dpm:
            m    = d["muestra"]
            tc   = d.get("totales_clas", {})
            shan = float(d.get("diversidad", {}).get("shannon", 0) or 0)
            # "Taxa" en la misma fila que "Benéficos"/"Fitopatógenos" — ambos
            # deben venir del universo completo de la muestra (todos_taxa), no
            # del Top N recortado (top_taxa). Con top_taxa, cualquier muestra
            # con más taxa que el Top N elegido mostraba siempre el mismo
            # número (el propio top_n) sin importar su riqueza real.
            comp_hdr.append([
                Paragraph(str(m.codigo),                     S["body_sm"]),
                Paragraph(str(d.get("indice_salud", 0)),     S["body_sm"]),
                Paragraph(str(d.get("nivel_salud", "N/A")),  S["body_sm"]),
                Paragraph(str(len(d.get("todos_taxa", []))), S["body_sm"]),
                Paragraph(f"{shan:.3f}",                     S["body_sm"]),
                Paragraph(str(tc.get("benefico", 0)),        S["body_sm"]),
                Paragraph(str(tc.get("fitopatogeno", 0)),    S["body_sm"]),
            ])
        col_comp = [80, 68, 72, 48, 65, 65, 70]
        t_comp = Table(comp_hdr, colWidths=col_comp, repeatRows=1)
        t_comp.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0),  _C_PRIMARY),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#f8faf9')]),
            ('INNERGRID',     (0, 0), (-1, -1), 0.4, _C_INNER),
            ('BOX',           (0, 0), (-1, -1), 1,   _C_BORDER),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN',         (1, 1), (3, -1),  'RIGHT'),
        ]))
        contenido.append(t_comp)
        contenido.append(Spacer(1, 14))

        # Gráfica comparativa Shannon + Salud
        chart_comp = ExportService._chart_comparativo_shannon(sorted_dpm, width_pt=ancho_util, height_pt=160, modo=modo)
        if chart_comp:
            contenido.append(chart_comp)
            contenido.append(Paragraph(
                "Figura 1. Comparación de Shannon H' (izq.) e Índice de Salud del Suelo (der.) entre muestras. "
                "Colores Shannon: verde H'≥3 · amarillo 2-3 · naranja 1-2 · rojo <1.",
                S["caption"],
            ))

        contenido.append(PageBreak())

        # ================================================================
        # PÁGINA 3 — Composición global (Top N)
        # ================================================================
        contenido.append(_seccion_hdr("COMPOSICIÓN GLOBAL POR MUESTRA", ancho_util, S, numero=2))
        contenido.append(Spacer(1, 14))

        # Gráfica rankeada global
        chart_ranked_g = ExportService._chart_ranked_bar_taxa(
            top_taxa, width_pt=ancho_util,
            titulo=f"Perfil de Abundancia Relativa — Top {datos.get('top_n', len(top_taxa))} {nivel.capitalize()} (acumulado comparativo)",
            subtitulo=f"Marcador {tipo} · {len(muestras)} muestras · Ordenado de mayor a menor abundancia relativa global",
            modo=modo,
        )
        if chart_ranked_g:
            contenido.append(chart_ranked_g)
            contenido.append(Paragraph(
                f"Figura 2. Abundancia relativa acumulada de los principales {nivel} en el conjunto comparativo ({len(muestras)} muestras, marcador {tipo}). "
                "Color: verde = benéfico · rojo = fitopatógeno · gris = neutral · gris claro = sin clasificación.",
                S["caption"],
            ))
            contenido.append(Spacer(1, 8))

        # Tabla top taxa global
        _clas_clr = {"benefico": "#16a34a", "fitopatogeno": "#dc2626", "neutral": "#64748b"}
        g_rows = [[
            Paragraph("<b>#</b>",             S["th_dark"]),
            Paragraph("<b>Taxón</b>",          S["th_dark"]),
            Paragraph("<b>Total reads</b>",    S["th_dark"]),
            Paragraph("<b>Abundancia %</b>",   S["th_dark"]),
            Paragraph("<b>Rol funcional</b>",  S["th_dark"]),
        ]]
        for i, r in enumerate(top_taxa, 1):
            clas = r.get("clasificacion", "sin_clasificar")
            clas_color = _clas_clr.get(clas, "#94a3b8")
            clas_txt   = {"benefico": "Benéfico", "fitopatogeno": "Fitopatógeno",
                          "neutral": "Neutral"}.get(clas, "Sin clas.")
            g_rows.append([
                Paragraph(str(i), S["body_sm"]),
                Paragraph(f"<i>{r.get('taxonomia', '?')}</i>", S["body_sm"]),
                Paragraph(str(r.get("total_hits", 0)), S["body_sm"]),
                Paragraph(f"{r.get('total_porcentaje', 0):.2f}%", S["body_sm"]),
                Paragraph(f"<font color='{clas_color}'>{clas_txt}</font>", S["body_sm"]),
            ])
        col_g = [26, ancho_util * 0.42, 65, 75, 90]
        t_g = Table(g_rows, colWidths=col_g, repeatRows=1)
        t_g.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0),  _C_PRIMARY),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#f8faf9')]),
            ('INNERGRID',     (0, 0), (-1, -1), 0.4, _C_INNER),
            ('BOX',           (0, 0), (-1, -1), 1,   _C_BORDER),
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN',         (0, 0), (0, -1),  'CENTER'),
            ('ALIGN',         (2, 1), (3, -1),  'RIGHT'),
        ]))
        contenido.append(t_g)

        contenido.append(PageBreak())

        # ================================================================
        # PÁGINA 4 — Perfil funcional comparativo
        # ================================================================
        contenido.append(_seccion_hdr("PERFIL FUNCIONAL COMPARATIVO", ancho_util, S, numero=3))
        contenido.append(Spacer(1, 14))

        # KPI tiles globales
        contenido.append(_kpi_tiles([
            {"val": str(totales_clas.get("benefico", 0)),      "lbl": "Benéficos",     "color": "#16A34A", "sub": "Global acumulado"},
            {"val": str(totales_clas.get("fitopatogeno", 0)),  "lbl": "Fitopatógenos", "color": "#DC2626", "sub": "Global acumulado"},
            {"val": str(totales_clas.get("neutral", 0)),       "lbl": "Neutrales",     "color": "#64748b", "sub": "Global acumulado"},
            {"val": str(totales_clas.get("sin_clasificar", 0)),"lbl": "Sin clasificación", "color": "#94A3B8", "sub": "Global acumulado"},
        ], ancho_util, S))
        contenido.append(Spacer(1, 12))

        # Gráfica agrupada por muestra
        chart_agrupada = ExportService._chart_barras_agrupadas_funcional(
            datos_por_muestra, width_pt=ancho_util, height_pt=175,
            titulo="Composición Funcional Comparativa por Muestra",
            subtitulo=f"N.° de taxa por categoría funcional en cada muestra · Marcador {tipo} · Nivel {nivel}",
            modo=modo,
        )
        if chart_agrupada:
            contenido.append(chart_agrupada)
            contenido.append(Paragraph(
                f"Figura 3. Número de taxa por categoría funcional en cada una de las {len(muestras)} muestras analizadas. "
                "Permite comparar el balance benéfico/fitopatógeno entre localidades o tratamientos.",
                S["caption"],
            ))
            contenido.append(Spacer(1, 10))

        # Tabla por muestra
        por_m_hdr = [[
            Paragraph("<b>Muestra</b>",        S["th_dark"]),
            Paragraph("<b>Benéficos</b>",      S["th_dark"]),
            Paragraph("<b>Fitopatógenos</b>",  S["th_dark"]),
            Paragraph("<b>Neutrales</b>",      S["th_dark"]),
            Paragraph("<b>Sin clasificación</b>",  S["th_dark"]),
        ]]
        for d in datos_por_muestra:
            tc = d.get("totales_clas", {})
            por_m_hdr.append([
                Paragraph(str(d["muestra"].codigo),       S["body_sm"]),
                Paragraph(str(tc.get("benefico", 0)),     S["body_sm"]),
                Paragraph(str(tc.get("fitopatogeno", 0)), S["body_sm"]),
                Paragraph(str(tc.get("neutral", 0)),      S["body_sm"]),
                Paragraph(str(tc.get("sin_clasificar",0)),S["body_sm"]),
            ])
        col_pm = [ancho_util * 0.30, 80, 90, 80, 80]
        t_pm = Table(por_m_hdr, colWidths=col_pm, repeatRows=1)
        t_pm.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0),  _C_PRIMARY),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#f8faf9')]),
            ('INNERGRID',     (0, 0), (-1, -1), 0.4, _C_INNER),
            ('BOX',           (0, 0), (-1, -1), 1,   _C_BORDER),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN',         (1, 1), (-1, -1), 'RIGHT'),
        ]))
        contenido.append(t_pm)

        contenido.append(PageBreak())

        # ================================================================
        # PÁGINA 5 — Trazabilidad
        # ================================================================
        contenido.append(_seccion_hdr("TRAZABILIDAD Y NOTA METODOLÓGICA", ancho_util, S, numero=4))
        contenido.append(Spacer(1, 12))

        # Tabla completa de metadatos por muestra
        meta_hdr = [[
            Paragraph("<b>Código</b>",    S["th_dark"]),
            Paragraph("<b>Cultivo</b>",   S["th_dark"]),
            Paragraph("<b>Variedad</b>",  S["th_dark"]),
            Paragraph("<b>Localidad</b>", S["th_dark"]),
            Paragraph("<b>Finca/Lote</b>",S["th_dark"]),
            Paragraph("<b>Altitud</b>",   S["th_dark"]),
            Paragraph("<b>Fecha</b>",     S["th_dark"]),
        ]]
        for m in muestras:
            cult = m.cultivo.nombre if getattr(m, 'cultivo', None) else "N/A"
            var  = m.variedad_clon.nombre if getattr(m, 'variedad_clon', None) else "N/A"
            meta_hdr.append([
                Paragraph(str(m.codigo),                               S["body_sm"]),
                Paragraph(cult,                                         S["body_sm"]),
                Paragraph(var,                                          S["body_sm"]),
                Paragraph(str(getattr(m, 'localidad',     'N/A') or 'N/A'), S["body_sm"]),
                Paragraph(str(getattr(m, 'finca_lote',    'N/A') or 'N/A'), S["body_sm"]),
                Paragraph(str(getattr(m, 'altitud',       'N/A') or 'N/A'), S["body_sm"]),
                Paragraph(str(getattr(m, 'fecha_registro','N/A') or 'N/A'), S["body_sm"]),
            ])
        col_meta = [62, 62, 65, ancho_util * 0.18, ancho_util * 0.15, 44, 58]
        t_meta = Table(meta_hdr, colWidths=col_meta, repeatRows=1)
        t_meta.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0),  _C_PRIMARY),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor('#f8faf9')]),
            ('INNERGRID',     (0, 0), (-1, -1), 0.4, _C_INNER),
            ('BOX',           (0, 0), (-1, -1), 1,   _C_BORDER),
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING',   (0, 0), (-1, -1), 5),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_meta)
        contenido.append(Spacer(1, 14))

        marcador_txt = "16S rRNA" if tipo == "16S" else "ITS (Internal Transcribed Spacer)"
        shannon_g    = float(diversidad.get("shannon", 0) or 0)
        # Universo completo de taxa (todos_taxa), no el Top N recortado
        # (top_taxa) — mismo criterio de respaldo que el resto del reporte
        # (ver _div_valor / líneas 544, 1284, 2852, 3211) para que "Taxa
        # únicos detectados" no dependa de qué Top N se haya elegido.
        riqueza_g    = diversidad.get("riqueza") or len(todos_taxa)
        nota_meto = (
            f"Análisis comparativo de <b>{len(muestras)}</b> muestras · Marcador: <b>{marcador_txt}</b> "
            f"· Nivel: <b>{nivel}</b>.<br/>"
            f"Taxa únicos detectados: <b>{riqueza_g}</b> · Shannon H' global: <b>{shannon_g:.3f}</b>.<br/><br/>"
            f"El Índice de Salud del Suelo integra la proporción benéfico/fitopatógeno (70%) y la diversidad "
            f"normalizada Shannon/3.5 (30%). Plataforma: BioMicro UTC — {fecha_gen}."
        )
        t_nota = Table([[Paragraph(nota_meto, S["body_sm"])]], colWidths=[ancho_util])
        t_nota.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), _C_LIGHT),
            ('BOX',           (0, 0), (-1, -1), 0.5, _C_BORDER),
            ('LEFTPADDING',   (0, 0), (-1, -1), 12),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 12),
            ('TOPPADDING',    (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        contenido.append(t_nota)
        contenido.append(Spacer(1, 14))
        contenido.append(Paragraph(
            "<i>Reporte técnico automatizado — BioMicro UTC. "
            "Los resultados deben ser interpretados por un profesional calificado en microbiología de suelos. "
            "Universidad Técnica de Cotopaxi · Laboratorio de Bioinformática de Suelos.</i>",
            S["italic"],
        ))

        doc.build(contenido, onFirstPage=_pdf_footer, onLaterPages=_pdf_footer)
        buffer.seek(0)
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # Excel multi-hoja
    # ------------------------------------------------------------------

    @staticmethod
    def generar_excel_multisheet(datos) -> HttpResponse:  # noqa: C901
        """
        Genera Excel con hojas completas para revisión de expertos.
        Modo INDIVIDUAL (1 muestra): 9-10 hojas.
        Modo COMPARATIVO (N muestras): 11 hojas.
        """
        # ── Extracción de datos ──────────────────────────────────────────
        muestra          = datos.get("muestra")
        muestras         = datos.get("muestras", [])
        top_taxa         = datos.get("top_taxa", [])
        todos_taxa       = datos.get("todos_taxa", [])
        diversidad       = datos.get("diversidad") or {}
        detalle_clas     = datos.get("detalle_clas", {})
        totales_clas     = datos.get("totales_clas", {})
        indice_salud     = datos.get("indice_salud", 0)
        nivel_salud      = datos.get("nivel_salud", "N/A")
        tipo             = datos.get("tipo", "16S")
        nivel            = datos.get("nivel", "genus")
        top_n            = datos.get("top_n", 25)
        usuario          = datos.get("usuario")
        datos_por_muestra = datos.get("datos_por_muestra", [])
        analisis_dif     = datos.get("analisis_diferencial") or {}
        jerarquia_taxonomica  = datos.get("jerarquia_taxonomica", [])
        nivel_campo_jerarquia = datos.get("nivel_campo_jerarquia", "genus")
        is_comparativo   = len(muestras) > 1
        # Modo de color de los gráficos Plotly/Kaleido embebidos (no afecta
        # el resto del formato de la hoja: encabezados, fills, tablas).
        modo             = datos.get("modo_color", "color")

        # ── Constantes de estilo ──────────────────────────────────────────
        CV        = "1D9E75"   # verde medio
        CV_OSC    = "0F6E56"   # verde oscuro (headers principales)
        CV_CLAR   = "E8F5EF"   # verde muy claro (secciones)
        CA        = "BA7517"   # ámbar
        CR        = "A32D2D"   # rojo
        CAZUL     = "185FA5"   # azul diversidad
        CGRIS     = "888888"   # gris neutro
        CBLANCO   = "FFFFFF"

        fill_hdr       = PatternFill("solid", fgColor=CV_OSC)
        fill_seccion   = PatternFill("solid", fgColor=CV_CLAR)
        fill_titulo    = PatternFill("solid", fgColor=CV)
        fill_azul      = PatternFill("solid", fgColor=CAZUL)

        fnt_hdr        = Font(bold=True, color=CBLANCO, size=11)
        fnt_titulo     = Font(bold=True, color=CBLANCO, size=13)
        fnt_seccion    = Font(bold=True, color=CV_OSC, size=10)
        fnt_normal     = Font(size=10)
        fnt_bold       = Font(bold=True, size=10)
        fnt_gris       = Font(italic=True, color=CGRIS, size=9)

        al_c  = Alignment(horizontal="center", vertical="center", wrap_text=True)
        al_l  = Alignment(horizontal="left",   vertical="center", wrap_text=True)

        borde = Border(
            left=Side(style="thin", color="D0D0D0"),
            right=Side(style="thin", color="D0D0D0"),
            top=Side(style="thin", color="D0D0D0"),
            bottom=Side(style="thin", color="D0D0D0"),
        )

        # ── Interpretaciones biológicas ───────────────────────────────────
        INTERP_SALUD = {
            "ÓPTIMO":    "Comunidad microbiana altamente funcional. Condiciones óptimas para el cultivo.",
            "FAVORABLE": "Condiciones adecuadas. Relación benéfico/fitopatógeno favorable al cultivo.",
            "MODERADO":  "Equilibrio funcional con margen de mejora. Monitorear evolución del suelo.",
            "EN RIESGO": "Desequilibrio funcional detectado. Intervención agronómica recomendada.",
            "CRÍTICO":   "Microbioma significativamente perturbado. Intervención urgente requerida.",
        }

        def _interp_shannon(v):
            v = float(v or 0)
            if v > 3:   return "Alta diversidad — comunidad equilibrada y resiliente"
            if v > 2:   return "Diversidad moderada-alta — ecosistema funcional"
            if v > 1:   return "Diversidad moderada — distribución irregular de taxa"
            return "Diversidad baja — dominancia marcada de uno o pocos taxa"

        def _interp_simpson(v):
            v = float(v or 0)
            if v > 0.85: return "Alta equidad — distribución uniforme de la comunidad"
            if v > 0.60: return "Buena equidad — múltiples taxa con abundancia relevante"
            if v > 0.30: return "Dominancia moderada — pocos taxa dominan el perfil"
            return "Dominancia alta — 1-2 taxa concentran la mayoría de la abundancia"

        def _interp_equit(v):
            v = float(v or 0)
            if v > 0.80: return "Comunidad equilibrada — distribución uniforme de la abundancia"
            if v > 0.60: return "Comunidad bien distribuida"
            if v > 0.30: return "Distribución con cierta desigualdad"
            return "Dominancia fuerte — distribución muy desigual entre taxa"

        def _interp_jaccard(v):
            v = float(v or 0)
            if v > 0.70: return "Muy alta similitud — comunidades prácticamente idénticas"
            if v > 0.50: return "Alta similitud — comparten la mayoría de taxa"
            if v > 0.30: return "Similitud moderada — comunidades parcialmente diferenciadas"
            if v > 0.10: return "Baja similitud — comunidades con perfiles distintos"
            return "Muy baja similitud — comunidades completamente diferenciadas"

        # ── Interpretaciones cortas debajo de tablas clave (Fase 1) ────────
        def _caption(ws, fila, texto, ancho_cols=5):
            c = ws.cell(row=fila, column=1, value=f"ℹ  {texto}")
            c.font = fnt_gris
            c.alignment = al_l
            ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=ancho_cols)
            ws.row_dimensions[fila].height = 16

        def _caption_top_taxa(ws, n_filas, top_taxón, ancho_cols=5):
            if not top_taxón:
                return
            _caption(ws, n_filas + 2,
                     f"El taxón más abundante es {top_taxón}, ordenado de mayor a menor abundancia relativa.",
                     ancho_cols)

        def _caption_diversidad(ws, fila, shanval, simpval, ancho_cols=4):
            _caption(ws, fila,
                     f"{_interp_shannon(shanval)}. {_interp_simpson(simpval)}.",
                     ancho_cols)

        def _caption_clasificacion(ws, fila, totales_clas_local, ancho_cols=4):
            ben  = totales_clas_local.get("benefico", 0)
            fito = totales_clas_local.get("fitopatogeno", 0)
            if ben > fito:
                texto = "La comunidad presenta una abundancia de microorganismos benéficos mayor que la de fitopatógenos."
            elif fito > ben:
                texto = "La comunidad presenta una abundancia de microorganismos fitopatógenos mayor que la de benéficos."
            else:
                texto = "La comunidad presenta un equilibrio entre microorganismos benéficos y fitopatógenos."
            _caption(ws, fila, texto, ancho_cols)

        # ── Funciones auxiliares ──────────────────────────────────────────
        def _safe(obj, attr, default="N/A"):
            val = getattr(obj, attr, None) if obj else None
            return str(val) if val not in (None, "") else default

        def _div_valor(div, clave, fallback_taxa=None):
            val = div.get(clave)
            if val is None and clave == "riqueza" and fallback_taxa is not None:
                return float(len(fallback_taxa))
            return float(val or 0)

        def _aplicar_tabla(ws, df, nombre, estilo="TableStyleMedium7"):
            if df.empty:
                return
            ref = f"A1:{get_column_letter(len(df.columns))}{len(df)+1}"
            tbl = XLTable(displayName=nombre, ref=ref)
            tbl.tableStyleInfo = TableStyleInfo(
                name=estilo, showFirstColumn=False, showLastColumn=False,
                showRowStripes=True, showColumnStripes=False,
            )
            ws.add_table(tbl)

        def _hdr(ws, n_cols, fill=None, font=None):
            """Estiliza fila 1 como encabezado."""
            for col in range(1, n_cols + 1):
                c = ws.cell(row=1, column=col)
                c.fill   = fill or fill_hdr
                c.font   = font or fnt_hdr
                c.alignment = al_c
                c.border = borde

        def _ajustar_cols(ws, anchos: dict):
            """Fija anchos específicos {letra: ancho}."""
            for letra, ancho in anchos.items():
                ws.column_dimensions[letra].width = ancho

        def _auto_ancho(ws, min_w=12, max_w=55):
            for col in ws.columns:
                ancho = min_w
                for cell in col:
                    try:
                        if cell.value:
                            ancho = max(ancho, min(len(str(cell.value)) + 3, max_w))
                    except Exception:
                        pass
                ws.column_dimensions[get_column_letter(col[0].column)].width = ancho

        def _wrap(ws, min_row=2, h=32):
            """Activa ajuste de texto y fija altura de fila."""
            for i, row in enumerate(ws.iter_rows(min_row=min_row), start=min_row):
                for cell in row:
                    prev = cell.alignment
                    cell.alignment = Alignment(
                        wrap_text=True,
                        horizontal=prev.horizontal if prev else "left",
                        vertical="center",
                    )
                ws.row_dimensions[i].height = h

        # ── Motor único de formato de tabla (Fase 1.3) ──────────────────────
        # Reemplaza la combinación _hdr+_datos_filas+_aplicar_tabla+_ajustar_cols
        # +_wrap repetida en cada hoja: encabezado institucional verde/azul,
        # Excel Table con autofiltro + bandas cebra, alineación y
        # number_format por tipo de dato inferido del dtype de cada columna,
        # ancho automático por contenido, e insignias de color por fila en la
        # columna de clasificación funcional (en vez de pintar el encabezado
        # completo de rojo/ámbar/gris como antes).
        _BADGE_CLASIF = {
            "benefico":         ("D4EDDA", "14532D"),
            "fitopatogeno":     ("FADBD8", "7F1D1D"),
            "neutral":          ("D6E4F0", "1E3A5F"),
            "sin_clasificar":   ("E5E7EB", "374151"),
            # variantes con etiqueta+emoji (p. ej. columna "Categoría" de
            # Clasificacion_Funcional / Microorganismos_Detalle)
            "🟢 Benéficos":      ("D4EDDA", "14532D"),
            "🔴 Fitopatógenos":  ("FADBD8", "7F1D1D"),
            "🔵 Neutrales":      ("D6E4F0", "1E3A5F"),
            "⚪ Sin clasificación":  ("E5E7EB", "374151"),
        }

        def _formatear_tabla(ws, df, nombre, header="verde", col_clasif=None,
                             min_w=10, max_w=48):
            if df.empty:
                return
            fill = fill_hdr if header == "verde" else fill_azul
            estilo = "TableStyleMedium7" if header == "verde" else "TableStyleMedium2"
            n_cols = len(df.columns)

            _hdr(ws, n_cols, fill=fill)

            for j, col in enumerate(df.columns, start=1):
                dtype = df[col].dtype
                es_id = col in ("#", "N°") or str(col).lower() in ("id", "código", "codigo")
                if es_id:
                    alin, fmt = al_c, None
                elif pd.api.types.is_integer_dtype(dtype):
                    alin, fmt = Alignment(horizontal="right", vertical="center"), "#,##0"
                elif pd.api.types.is_float_dtype(dtype):
                    alin, fmt = Alignment(horizontal="right", vertical="center"), "0.00"
                else:
                    alin, fmt = al_l, None
                for i in range(len(df)):
                    c = ws.cell(row=2 + i, column=j)
                    c.font = fnt_normal
                    c.border = borde
                    c.alignment = alin
                    if fmt:
                        c.number_format = fmt

            if col_clasif and col_clasif in df.columns:
                j = list(df.columns).index(col_clasif) + 1
                for i, val in enumerate(df[col_clasif]):
                    bg, fg = _BADGE_CLASIF.get(val, _BADGE_CLASIF["sin_clasificar"])
                    c = ws.cell(row=2 + i, column=j)
                    c.fill = PatternFill("solid", fgColor=bg)
                    c.font = Font(bold=True, size=10, color=fg)

            _aplicar_tabla(ws, df, nombre, estilo)
            _auto_ancho(ws, min_w=min_w, max_w=max_w)

            # Alto de fila dinámico: solo las filas con texto largo en
            # columnas no numéricas necesitan más alto que una línea.
            text_cols = [j for j, col in enumerate(df.columns, start=1)
                         if not pd.api.types.is_numeric_dtype(df[col].dtype)]
            for i in range(len(df)):
                largo = max((len(str(ws.cell(row=2 + i, column=j).value or ""))
                            for j in text_cols), default=0)
                if largo > 40:
                    ws.row_dimensions[2 + i].height = 30

        def _titulo_celda(ws, celda, texto, color=None):
            c = ws[celda]
            c.value = texto
            c.font  = Font(bold=True, size=12, color=color or CV_OSC)
            c.alignment = al_l

        def _seccion_row(ws, row_num, texto, n_cols):
            """Pinta una fila completa como cabecera de sección."""
            ws.cell(row=row_num, column=1, value=texto).font = fnt_seccion
            for col in range(1, n_cols + 1):
                c = ws.cell(row=row_num, column=col)
                c.fill   = fill_seccion
                c.border = borde
            ws.row_dimensions[row_num].height = 18

        def _titulo_hoja(ws, texto, n_cols, color=None):
            """Fila 1: título combinado visual."""
            ws.row_dimensions[1].height = 24
            for col in range(1, n_cols + 1):
                c = ws.cell(row=1, column=col)
                c.fill   = PatternFill("solid", fgColor=color or CV_OSC)
                c.font   = fnt_titulo
                c.border = borde
            ws.cell(row=1, column=1).value = texto

        # ── Gráficos Plotly → PNG embebido (Fase 1.2) ───────────────────────
        # Reemplaza los gráficos nativos de openpyxl (BarChart/DoughnutChart)
        # por imágenes Plotly de alta resolución, con el mismo criterio de
        # lectura de datos que las versiones nativas: leen directamente de
        # las celdas ya escritas en la hoja en vez de duplicar los datos.

        def _fig_barras_h(ws, n_filas, col_datos, col_cats, color_fill=None,
                          titulo_celda=None, titulo_txt="", col_clasif=None,
                          ancho_px=820, fila_inicio=2):
            """Barras horizontales (Top Taxa). Si col_clasif se indica,
            colorea cada barra según la clasificación ecológica de esa fila.
            fila_inicio es la primera fila de datos (por defecto 2, asumiendo
            encabezado en la fila 1)."""
            if titulo_celda:
                _titulo_celda(ws, titulo_celda, titulo_txt)
            categorias, valores, marker_colores, marker_hatches = [], [], [], []
            _clas_orden = ["benefico", "fitopatogeno", "neutral", "sin_clasificar"]
            for i in range(n_filas):
                fila = fila_inicio + i
                categorias.append(str(ws.cell(row=fila, column=col_cats).value or ""))
                valores.append(float(ws.cell(row=fila, column=col_datos).value or 0))
                if col_clasif:
                    clas = str(ws.cell(row=fila, column=col_clasif).value or "sin_clasificar")
                    marker_colores.append(_resolver_color(COLOR_POR_CLAS.get(clas, PLOTLY_GRIS), modo))
                    marker_hatches.append(_resolver_hatch_plotly(
                        _clas_orden.index(clas) if clas in _clas_orden else 3, modo))
                else:
                    marker_colores.append(_resolver_color(color_fill or PLOTLY_VERDE, modo))
                    marker_hatches.append(_resolver_hatch_plotly(0, modo))
            # Invertido: Plotly dibuja barras horizontales de abajo hacia
            # arriba, así que el taxón más abundante debe ir al final de la
            # lista para quedar arriba (igual que el gráfico nativo original).
            categorias, valores, marker_colores, marker_hatches = (
                categorias[::-1], valores[::-1], marker_colores[::-1], marker_hatches[::-1])
            marker_kwargs = dict(color=marker_colores, line=dict(width=0))
            if modo == "grises":
                marker_kwargs["pattern"] = dict(shape=marker_hatches, fgcolor="#ffffff", size=6)
            fig = go.Figure(go.Bar(
                x=valores, y=categorias, orientation="h",
                marker=marker_kwargs,
                text=[f"{v:.2f}%" for v in valores], textposition="outside",
                cliponaxis=False,
            ))
            layout = _plotly_layout_base(titulo_txt or "Abundancia relativa")
            layout["xaxis"] = dict(title="Abundancia (%)", gridcolor="#c8c8c8", zeroline=False)
            layout["yaxis"] = dict(title="Taxonomía", automargin=True)
            fig.update_layout(layout)
            alto_px = max(360, min(int(n_filas * 28) + 110, 900))
            return _fig_a_imagen_xl(fig, ancho_px, alto_px)

        def _fig_barras_v(ws, col_datos, col_cats, min_row, max_row,
                          colores=None, color_fill=None, titulo_celda=None,
                          titulo_txt="", y_titulo="Valor", y_max=None,
                          ancho_px=760, alto_px=440):
            """Barras verticales. `colores` es una lista paralela a las
            categorías (para pintar por nivel/umbral); si no se indica,
            usa `color_fill` como color único."""
            if titulo_celda:
                _titulo_celda(ws, titulo_celda, titulo_txt)
            categorias, valores = [], []
            for fila in range(min_row, max_row + 1):
                categorias.append(str(ws.cell(row=fila, column=col_cats).value or ""))
                valores.append(float(ws.cell(row=fila, column=col_datos).value or 0))
            marker_colores = colores if colores else [color_fill or PLOTLY_VERDE] * len(valores)
            marker_colores = _resolver_colores(marker_colores, modo)
            marker_kwargs = dict(color=marker_colores, line=dict(width=0))
            if modo == "grises":
                marker_kwargs["pattern"] = dict(
                    shape=[_resolver_hatch_plotly(i, modo) for i in range(len(valores))],
                    fgcolor="#ffffff", size=6)
            fig = go.Figure(go.Bar(
                x=categorias, y=valores,
                marker=marker_kwargs,
                text=[f"{v:.2f}" for v in valores], textposition="outside",
                cliponaxis=False,
            ))
            layout = _plotly_layout_base(titulo_txt)
            layout["yaxis"] = dict(title=y_titulo, gridcolor="#c8c8c8", zeroline=False,
                                    range=[0, y_max] if y_max else None)
            layout["xaxis"] = dict(showgrid=False)
            fig.update_layout(layout)
            return _fig_a_imagen_xl(fig, ancho_px, alto_px)

        def _fig_donut(ws, col_datos, col_cats, min_row, max_row,
                       titulo_celda=None, titulo_txt="", colores=None,
                       ancho_px=560, alto_px=420):
            """Donut de clasificación funcional — reemplaza el pastel nativo."""
            if titulo_celda:
                _titulo_celda(ws, titulo_celda, titulo_txt)
            categorias, valores = [], []
            for fila in range(min_row, max_row + 1):
                categorias.append(str(ws.cell(row=fila, column=col_cats).value or ""))
                valores.append(float(ws.cell(row=fila, column=col_datos).value or 0))
            palette = colores or [PLOTLY_VERDE, PLOTLY_ROJO, PLOTLY_AMBAR, PLOTLY_GRIS]
            palette = _resolver_colores(palette[:len(categorias)], modo)
            marker_kwargs = dict(colors=palette, line=dict(color="white", width=2))
            if modo == "grises":
                marker_kwargs["pattern"] = dict(
                    shape=[_resolver_hatch_plotly(i, modo) for i in range(len(categorias))])
            fig = go.Figure(go.Pie(
                labels=categorias, values=valores, hole=0.55,
                marker=marker_kwargs,
                textinfo="percent", textfont=dict(size=13),
            ))
            layout = _plotly_layout_base(titulo_txt)
            layout["showlegend"] = True
            layout["legend"] = dict(orientation="h", yanchor="bottom", y=-0.18,
                                     x=0.5, xanchor="center")
            fig.update_layout(layout)
            return _fig_a_imagen_xl(fig, ancho_px, alto_px)

        def _fig_treemap(ids, labels, parents, values, colores=None,
                         titulo_txt="Treemap de Abundancias",
                         ancho_px=820, alto_px=520):
            """Los valores de los nodos padre (categorías) se pasan como
            None a propósito: Plotly los calcula automáticamente como la
            suma de sus hijos en vez de exigir que coincidan manualmente."""
            gris_scale = [[0, "#F3F4F6"], [1, "#4B5563"]]
            fig = go.Figure(go.Treemap(
                ids=ids, labels=labels, parents=parents, values=values,
                marker=(dict(colors=_resolver_colores(colores, modo)) if colores else
                        dict(colorscale=gris_scale if modo == "grises"
                             else [[0, PLOTLY_TURQUESA], [1, PLOTLY_VERDE_OS]])),
                textinfo="label+percent parent",
                root_color="white",
            ))
            fig.update_layout(_plotly_layout_base(titulo_txt))
            return _fig_a_imagen_xl(fig, ancho_px, alto_px)

        def _fig_sunburst(ids, labels, parents, values,
                          titulo_txt="Jerarquía Taxonómica",
                          ancho_px=760, alto_px=680):
            """ids compuestos (no solo labels) para no fusionar nodos con
            el mismo nombre en ramas distintas del árbol taxonómico."""
            colorscale_sb = ([[0, "#F3F4F6"], [0.5, "#9CA3AF"], [1, "#374151"]] if modo == "grises"
                              else [[0, PLOTLY_TURQUESA], [0.5, PLOTLY_VERDE], [1, PLOTLY_VERDE_OS]])
            fig = go.Figure(go.Sunburst(
                ids=ids, labels=labels, parents=parents, values=values,
                marker=dict(colorscale=colorscale_sb),
            ))
            fig.update_layout(_plotly_layout_base(titulo_txt))
            return _fig_a_imagen_xl(fig, ancho_px, alto_px)

        def _fig_heatmap(matriz, filas, columnas,
                         titulo_txt="Distribución de Abundancia por Muestra",
                         ancho_px=900, alto_px=520):
            colorscale_hm = ([[0, "#F9FAFB"], [0.5, "#9CA3AF"], [1, "#1F2937"]] if modo == "grises"
                              else [[0, "#F0FDF9"], [0.5, PLOTLY_TURQUESA], [1, PLOTLY_VERDE_OS]])
            fig = go.Figure(go.Heatmap(
                z=matriz, x=columnas, y=filas,
                colorscale=colorscale_hm,
                colorbar=dict(title="Abundancia (%)"),
            ))
            layout = _plotly_layout_base(titulo_txt)
            layout["xaxis"] = dict(title="Muestra", side="bottom")
            layout["yaxis"] = dict(title="Taxón", automargin=True)
            fig.update_layout(layout)
            return _fig_a_imagen_xl(fig, ancho_px, alto_px)

        def _fig_radar(categorias, valores, titulo_txt="Indicadores Ecológicos",
                       ancho_px=560, alto_px=520):
            linea_color  = _resolver_color(PLOTLY_TURQUESA, modo)
            marker_color = _resolver_color(PLOTLY_VERDE_OS, modo)
            fill_color   = "rgba(107,114,128,0.25)" if modo == "grises" else "rgba(20,184,166,0.25)"
            fig = go.Figure(go.Scatterpolar(
                r=valores + valores[:1], theta=categorias + categorias[:1],
                fill="toself", fillcolor=fill_color,
                line=dict(color=linea_color, width=2),
                marker=dict(color=marker_color, size=6),
            ))
            layout = _plotly_layout_base(titulo_txt)
            layout["polar"] = dict(
                radialaxis=dict(visible=True, range=[0, 1], gridcolor="#E5E7EB"),
                angularaxis=dict(gridcolor="#E5E7EB"),
            )
            fig.update_layout(layout)
            return _fig_a_imagen_xl(fig, ancho_px, alto_px)

        def _fig_gauge(valor, nivel_salud_g="N/A", titulo_txt="Índice de Salud del Suelo",
                      ancho_px=520, alto_px=380):
            color_aguja = _resolver_color(_NIVEL_COLORES.get(nivel_salud_g, "#64748b"), modo)
            pasos_color = _resolver_colores(["#FEE2E2", "#FEF3C7", "#D1FAE5", "#A7F3D0"], modo)
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=valor,
                number=dict(font=dict(size=36, color=color_aguja)),
                gauge=dict(
                    axis=dict(range=[0, 100], tickcolor="#9CA3AF"),
                    bar=dict(color=color_aguja, thickness=0.28),
                    bgcolor="white",
                    borderwidth=0,
                    steps=[
                        dict(range=[0, 40],   color=pasos_color[0]),
                        dict(range=[40, 60],  color=pasos_color[1]),
                        dict(range=[60, 80],  color=pasos_color[2]),
                        dict(range=[80, 100], color=pasos_color[3]),
                    ],
                ),
            ))
            fig.update_layout(_plotly_layout_base(titulo_txt, subtitulo=nivel_salud_g))
            return _fig_a_imagen_xl(fig, ancho_px, alto_px)

        # ── Datos para las visualizaciones nuevas (Fase 1.2) ────────────────
        _CLASES_LBL = {
            "benefico":       "🟢 Benéficos",
            "fitopatogeno":   "🔴 Fitopatógenos",
            "neutral":        "🔵 Neutrales",
            "sin_clasificar": "⚪ Sin clasificación",
        }

        def _datos_treemap_taxa(registros, top=20):
            """A partir de una lista de dicts con Taxón/Total_Hits/Clasificación
            (misma forma que top_rec/todos_rec), arma ids/labels/parents/values
            para un treemap de 2 niveles: Clasificación → Taxón."""
            regs = sorted(registros, key=lambda r: r.get("Total_Hits", 0) or 0,
                          reverse=True)[:top]
            ids, labels, parents, values, colores = [], [], [], [], []
            clases_usadas = {}
            for i, r in enumerate(regs):
                clas = r.get("Clasificación", "sin_clasificar")
                lbl_clas = _CLASES_LBL.get(clas, clas)
                clases_usadas.setdefault(lbl_clas, clas)
                ids.append(f"T::{i}::{r.get('Taxón','?')}")
                labels.append(str(r.get("Taxón", "?"))[:40])
                parents.append(lbl_clas)
                values.append(max(float(r.get("Total_Hits", 0) or 0), 0))
                colores.append(COLOR_POR_CLAS.get(clas, PLOTLY_GRIS))
            for lbl_clas, clas in clases_usadas.items():
                ids.append(lbl_clas)
                labels.append(lbl_clas)
                parents.append("")
                values.append(None)
                colores.append(COLOR_POR_CLAS.get(clas, PLOTLY_GRIS))
            return ids, labels, parents, values, colores

        def _datos_sunburst_taxonomia(jerarquia, nivel_campo):
            """A partir de datos['jerarquia_taxonomica'] (agregación
            kingdom→phylum→<nivel>), arma ids/labels/parents/values."""
            ids, labels, parents, values = ["Todos"], ["Todos"], [""], [None]
            vistos = set()
            for r in jerarquia:
                reino = str(r.get("kingdom") or "Sin clasificar")
                filo  = str(r.get("phylum") or "Sin clasificar")
                hoja  = str(r.get(nivel_campo) or "Sin clasificar")
                hits  = float(r.get("hits", 0) or 0)
                if hits <= 0:
                    continue
                id_reino = f"R::{reino}"
                if id_reino not in vistos:
                    vistos.add(id_reino)
                    ids.append(id_reino); labels.append(reino)
                    parents.append("Todos"); values.append(None)
                id_filo = f"F::{reino}::{filo}"
                if id_filo not in vistos:
                    vistos.add(id_filo)
                    ids.append(id_filo); labels.append(filo)
                    parents.append(id_reino); values.append(None)
                id_hoja = f"H::{reino}::{filo}::{hoja}::{len(ids)}"
                ids.append(id_hoja); labels.append(hoja)
                parents.append(id_filo); values.append(hits)
            return ids, labels, parents, values

        def _datos_heatmap_muestras(datos_por_muestra_local, top=15):
            """Matriz muestra × taxón (Top N por abundancia máxima entre
            muestras) para el heatmap de distribución — solo modo comparativo."""
            todas = {}
            for dpm in datos_por_muestra_local:
                cod = str(dpm["muestra"].codigo)
                for r in dpm.get("top_taxa", []):
                    taxon = str(r.get("taxonomia", r.get("nombre", "?")))
                    val = float(r.get("total_porcentaje", r.get("porcentaje", 0)) or 0)
                    todas.setdefault(taxon, {})[cod] = val
            if not todas:
                return [], [], []
            taxa_top = sorted(todas.keys(), key=lambda t: max(todas[t].values()),
                              reverse=True)[:top]
            columnas = [str(dpm["muestra"].codigo) for dpm in datos_por_muestra_local]
            matriz = [[todas[t].get(c, 0.0) for c in columnas] for t in taxa_top]
            return matriz, taxa_top, columnas

        def _datos_radar_diversidad(riqval_r, shanval_r, simpval_r, equival_r, indice_salud_r):
            """Normaliza los 5 indicadores a escala 0-1 para el radar. La
            riqueza se normaliza contra un techo de referencia (150 taxa,
            valor generoso para suelos agrícolas); Shannon contra su techo
            teórico habitual (~5); el resto ya vive en escala 0-1 o 0-100."""
            return (
                ["Riqueza", "Shannon H'", "Simpson D", "Equitatividad J'", "Salud del suelo"],
                [
                    round(min(riqval_r / 150, 1.0), 3),
                    round(min(shanval_r / 5.0, 1.0), 3),
                    round(min(simpval_r, 1.0), 3),
                    round(min(equival_r, 1.0), 3),
                    round(min(indice_salud_r / 100, 1.0), 3),
                ],
            )

        # ── Valores derivados ─────────────────────────────────────────────
        cultivo_nom = (muestra.cultivo.nombre
                       if muestra and getattr(muestra, "cultivo", None) else "N/A")
        var_nom = (muestra.variedad_clon.nombre
                   if muestra and getattr(muestra, "variedad_clon", None) else "N/A")
        fecha_gen = datetime.now().strftime("%d/%m/%Y %H:%M")
        analista  = str(usuario) if usuario else "Sistema"
        marcador_lbl = "16S rRNA (bacterias)" if tipo == "16S" else "ITS (hongos)"
        total_taxa_global = len(todos_taxa)
        total_catalogados = (totales_clas.get("benefico", 0)
                             + totales_clas.get("fitopatogeno", 0)
                             + totales_clas.get("neutral", 0))

        buffer = BytesIO()

        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            wb = writer.book

            # ════════════════════════════════════════════════════════════
            # ██  MODO INDIVIDUAL — 1 muestra
            # ════════════════════════════════════════════════════════════
            if not is_comparativo:

                # ─────────────────────────────────────────────────────
                # H-01  RESUMEN EJECUTIVO
                # ─────────────────────────────────────────────────────
                shanval  = _div_valor(diversidad, "shannon")
                simpval  = _div_valor(diversidad, "simpson")
                equival  = _div_valor(diversidad, "equitatividad")
                riqval   = int(_div_valor(diversidad, "riqueza", todos_taxa))

                res_rows = [
                    ["Campo", "Valor", "Notas / Interpretación"],
                ]
                # Bloque encabezado
                res_rows += [
                    ["BioMicro — Reporte Individual de Salud Microbiológica", "", ""],
                    ["Fecha de generación", fecha_gen, ""],
                    ["Analista", analista, ""],
                    ["", "", ""],
                ]
                # Identificación de la muestra
                res_rows += [
                    ["IDENTIFICACIÓN DE LA MUESTRA", "", ""],
                    ["Código de muestra",   _safe(muestra, "codigo"), ""],
                    ["Cultivo",             cultivo_nom, ""],
                    ["Variedad / Clon",     var_nom, ""],
                    ["Tipo de muestra",     _safe(muestra, "tipo_muestra"), ""],
                    ["Localidad",           _safe(muestra, "localidad"), ""],
                    ["Finca / Lote",        _safe(muestra, "finca_lote"), ""],
                    ["Altitud (m.s.n.m.)",  _safe(muestra, "altitud"), ""],
                    ["Fecha de registro",   _safe(muestra, "fecha_registro"), ""],
                    ["Observaciones",       _safe(muestra, "observaciones"), ""],
                    ["", "", ""],
                ]
                # Parámetros analíticos
                res_rows += [
                    ["PARÁMETROS DEL ANÁLISIS", "", ""],
                    ["Marcador molecular",  marcador_lbl, ""],
                    ["Nivel taxonómico",    nivel.capitalize(), ""],
                    ["Top N seleccionado",  str(top_n), "Taxa más abundantes mostrados"],
                    ["Total taxa detectados", str(total_taxa_global), "Todos los taxa únicos identificados"],
                    ["Taxa catalogados",    str(total_catalogados), "Con clasificación funcional en catálogo"],
                    ["", "", ""],
                ]
                # Índice de salud
                res_rows += [
                    ["ÍNDICE DE SALUD DEL SUELO", "", ""],
                    ["Índice (0 – 100)",    str(indice_salud),
                     INTERP_SALUD.get(nivel_salud, "")],
                    ["Nivel cualitativo",   nivel_salud, ""],
                    ["", "", ""],
                ]
                # Diversidad alfa
                res_rows += [
                    ["DIVERSIDAD ALFA", "", ""],
                    ["Riqueza de taxa",    str(riqval),
                     "Alta >100 | Moderada >30 | Baja ≤30"],
                    ["Shannon H'",         f"{shanval:.4f}",
                     _interp_shannon(shanval)],
                    ["Simpson D",          f"{simpval:.4f}",
                     _interp_simpson(simpval)],
                    ["Equitatividad J'",   f"{equival:.4f}",
                     _interp_equit(equival)],
                    ["N° muestras usadas", str(diversidad.get("n_muestras", "—")),
                     "Número de muestras sobre las que se promedia la diversidad"],
                    ["", "", ""],
                ]
                # Clasificación funcional
                total_clf = max(total_catalogados, 1)
                res_rows += [
                    ["CLASIFICACIÓN FUNCIONAL", "", ""],
                    ["🟢 Taxa Benéficos",
                     str(totales_clas.get("benefico", 0)),
                     f"{totales_clas.get('benefico',0)/total_clf*100:.1f}% del total catalogado"],
                    ["🔴 Taxa Fitopatógenos",
                     str(totales_clas.get("fitopatogeno", 0)),
                     f"{totales_clas.get('fitopatogeno',0)/total_clf*100:.1f}% del total catalogado"],
                    ["🔵 Taxa Neutrales",
                     str(totales_clas.get("neutral", 0)),
                     f"{totales_clas.get('neutral',0)/total_clf*100:.1f}% del total catalogado"],
                    ["⚪ Taxa Sin Clasificación",
                     str(totales_clas.get("sin_clasificar", 0)),
                     "No presentes en el catálogo funcional"],
                ]

                df_res = pd.DataFrame(res_rows[1:], columns=res_rows[0])
                _excel_safe_df(df_res).to_excel(writer, index=False, sheet_name="Resumen")
                ws_r = writer.sheets["Resumen"]

                SECCIONES_R = {
                    "IDENTIFICACIÓN DE LA MUESTRA",
                    "PARÁMETROS DEL ANÁLISIS",
                    "ÍNDICE DE SALUD DEL SUELO",
                    "DIVERSIDAD ALFA",
                    "CLASIFICACIÓN FUNCIONAL",
                }
                _hdr(ws_r, 3)
                for row in ws_r.iter_rows(min_row=2):
                    v = str(row[0].value or "")
                    if v in SECCIONES_R:
                        for cell in row:
                            cell.fill = fill_seccion
                            cell.font = fnt_seccion
                            cell.border = borde
                        ws_r.row_dimensions[row[0].row].height = 18
                    elif v == "BioMicro — Reporte Individual de Salud Microbiológica":
                        for cell in row:
                            cell.fill = fill_titulo
                            cell.font = Font(bold=True, color=CBLANCO, size=12)
                            cell.border = borde
                        ws_r.row_dimensions[row[0].row].height = 22
                    elif v:
                        for cell in row:
                            cell.font = fnt_normal
                            cell.border = borde
                            cell.alignment = al_l
                _ajustar_cols(ws_r, {"A": 30, "B": 22, "C": 65})
                _wrap(ws_r, min_row=2, h=28)

                # ── Resumen ejecutivo interpretado (Fase 1) ─────────────
                fila_hs = ws_r.max_row + 2
                ws_r.cell(row=fila_hs, column=1, value="RESUMEN EJECUTIVO INTERPRETADO").font = fnt_seccion
                for col in range(1, 4):
                    c_sec = ws_r.cell(row=fila_hs, column=col)
                    c_sec.fill = fill_seccion
                    c_sec.border = borde
                ws_r.row_dimensions[fila_hs].height = 18
                fila_hs += 1

                for col in range(4, 20):
                    ws_r.column_dimensions[get_column_letter(col)].width = 4
                ws_r.add_image(_fig_gauge(indice_salud, nivel_salud),
                                f"{get_column_letter(4)}{fila_hs}")
                fila_hs += 2

                for parrafo in _generar_interpretacion_ejecutiva(datos):
                    c_par = ws_r.cell(row=fila_hs, column=1, value=parrafo)
                    c_par.font = fnt_normal
                    c_par.alignment = al_l
                    ws_r.merge_cells(start_row=fila_hs, start_column=1, end_row=fila_hs, end_column=3)
                    ws_r.row_dimensions[fila_hs].height = 40
                    fila_hs += 1

                # ─────────────────────────────────────────────────────
                # H-02  TOP N TAXA
                # ─────────────────────────────────────────────────────
                top_rec = [{
                    "#": i + 1,
                    "Taxón":          r.get("taxonomia", r.get("nombre", "?")),
                    "Total_Hits":     int(r.get("total_hits", r.get("hits", 0)) or 0),
                    "Abundancia_%":   round(float(r.get("total_porcentaje",
                                                  r.get("porcentaje", 0)) or 0), 4),
                    "Clasificación":  r.get("clasificacion", "sin_clasificar"),
                } for i, r in enumerate(top_taxa)]
                df_top = (pd.DataFrame(top_rec) if top_rec
                          else pd.DataFrame(columns=["#","Taxón","Total_Hits",
                                                     "Abundancia_%","Clasificación"]))
                _excel_safe_df(df_top).to_excel(writer, index=False, sheet_name="Top_N_Taxa")
                ws_top = writer.sheets["Top_N_Taxa"]
                _formatear_tabla(ws_top, df_top, "TablaTopN", col_clasif="Clasificación")
                _caption_top_taxa(ws_top, len(df_top), top_rec[0]["Taxón"] if top_rec else None)

                if len(df_top) > 0:
                    ws_top.add_image(_fig_barras_h(
                        ws_top, n_filas=len(df_top), col_datos=4, col_cats=2, col_clasif=5,
                        titulo_celda="G2",
                        titulo_txt=f"Top {top_n} Taxa — Abundancia (%) · Marcador {tipo}",
                    ), "G3")
                    ids_tm, lbl_tm, par_tm, val_tm, col_tm = _datos_treemap_taxa(top_rec)
                    ws_top.add_image(_fig_treemap(
                        ids_tm, lbl_tm, par_tm, val_tm, colores=col_tm,
                        titulo_txt="Treemap de Abundancias por Clasificación",
                    ), "V3")

                # ─────────────────────────────────────────────────────
                # H-03  TAXONOMÍA COMPLETA
                # ─────────────────────────────────────────────────────
                todos_rec = [{
                    "#": i + 1,
                    "Taxón":         r.get("taxonomia", r.get("nombre", "?")),
                    "Total_Hits":    int(r.get("total_hits", r.get("hits", 0)) or 0),
                    "Abundancia_%":  round(float(r.get("total_porcentaje",
                                                 r.get("porcentaje", 0)) or 0), 4),
                    "Clasificación": r.get("clasificacion", "sin_clasificar"),
                } for i, r in enumerate(todos_taxa)]
                df_tod = (pd.DataFrame(todos_rec) if todos_rec
                          else pd.DataFrame(columns=["#","Taxón","Total_Hits",
                                                     "Abundancia_%","Clasificación"]))
                _excel_safe_df(df_tod).to_excel(writer, index=False, sheet_name="Taxonomia_Completa")
                ws_tod = writer.sheets["Taxonomia_Completa"]
                _formatear_tabla(ws_tod, df_tod, "TablaTaxonomia", col_clasif="Clasificación")
                if jerarquia_taxonomica:
                    ids_sb, lbl_sb, par_sb, val_sb = _datos_sunburst_taxonomia(
                        jerarquia_taxonomica, nivel_campo_jerarquia)
                    _titulo_celda(ws_tod, "G1", "Jerarquía Taxonómica", CV_OSC)
                    ws_tod.add_image(_fig_sunburst(ids_sb, lbl_sb, par_sb, val_sb), "G2")

                # ─────────────────────────────────────────────────────
                # H-04  DIVERSIDAD ALFA
                # ─────────────────────────────────────────────────────
                div_rec = [
                    {"Métrica": "Riqueza de taxa",
                     "Valor": riqval,
                     "Unidad": "n.° taxa únicos",
                     "Interpretación": _interp_shannon.__doc__ or
                         ("Alta >100 | Moderada >30 | Baja ≤30")},
                    {"Métrica": "Shannon H'",
                     "Valor": round(shanval, 4),
                     "Unidad": "bits (log natural)",
                     "Interpretación": _interp_shannon(shanval)},
                    {"Métrica": "Simpson D",
                     "Valor": round(simpval, 4),
                     "Unidad": "índice (0–1)",
                     "Interpretación": _interp_simpson(simpval)},
                    {"Métrica": "Equitatividad J'",
                     "Valor": round(equival, 4),
                     "Unidad": "índice (0–1)",
                     "Interpretación": _interp_equit(equival)},
                    {"Métrica": "N° muestras",
                     "Valor": float(diversidad.get("n_muestras", 0) or 0),
                     "Unidad": "muestras",
                     "Interpretación": "Número de muestras sobre las que se calculan los promedios"},
                ]
                # Corregir interpretación de riqueza
                div_rec[0]["Interpretación"] = (
                    "Alta riqueza >100 taxa | Moderada 30-100 | Baja <30 taxa"
                )
                df_div = pd.DataFrame(div_rec)
                _excel_safe_df(df_div).to_excel(writer, index=False, sheet_name="Diversidad_Alfa")
                ws_div = writer.sheets["Diversidad_Alfa"]
                _formatear_tabla(ws_div, df_div, "TablaDiversidad", header="azul")
                _caption_diversidad(ws_div, 7, shanval, simpval)

                # Gráfico 4 índices (sin N° muestras)
                ws_div.add_image(_fig_barras_v(
                    ws_div, col_datos=2, col_cats=1, min_row=2, max_row=5,
                    colores=[PLOTLY_AZUL, PLOTLY_VERDE, PLOTLY_AMBAR, PLOTLY_TURQUESA],
                    titulo_celda="F2", titulo_txt="Índices de Diversidad Alfa",
                ), "F3")

                # ─────────────────────────────────────────────────────
                # H-05  CLASIFICACIÓN FUNCIONAL
                # ─────────────────────────────────────────────────────
                total_det = max(total_catalogados + totales_clas.get("sin_clasificar", 0), 1)
                clf_rec = [
                    {"Categoría": "🟢 Benéficos",
                     "N°_Taxa": totales_clas.get("benefico", 0),
                     "%_Total": round(totales_clas.get("benefico",0)/total_det*100, 2),
                     "Descripción_del_Rol":
                         "Promueven el crecimiento vegetal, fijan nitrógeno, solubilizan fósforo "
                         "o antagonizan patógenos"},
                    {"Categoría": "🔴 Fitopatógenos",
                     "N°_Taxa": totales_clas.get("fitopatogeno", 0),
                     "%_Total": round(totales_clas.get("fitopatogeno",0)/total_det*100, 2),
                     "Descripción_del_Rol":
                         "Causan o pueden causar enfermedades en el cultivo. "
                         "Su presencia en alta abundancia es señal de alerta fitosanitaria"},
                    {"Categoría": "🔵 Neutrales",
                     "N°_Taxa": totales_clas.get("neutral", 0),
                     "%_Total": round(totales_clas.get("neutral",0)/total_det*100, 2),
                     "Descripción_del_Rol":
                         "Sin función agronómica conocida o con efecto dependiente del contexto"},
                    {"Categoría": "⚪ Sin clasificación",
                     "N°_Taxa": totales_clas.get("sin_clasificar", 0),
                     "%_Total": round(totales_clas.get("sin_clasificar",0)/total_det*100, 2),
                     "Descripción_del_Rol":
                         "No presentes en el catálogo funcional del sistema"},
                ]
                df_clf = pd.DataFrame(clf_rec)
                _excel_safe_df(df_clf).to_excel(writer, index=False, sheet_name="Clasificacion_Funcional")
                ws_clf = writer.sheets["Clasificacion_Funcional"]
                _formatear_tabla(ws_clf, df_clf, "TablaClasificacion", col_clasif="Categoría")
                _caption_clasificacion(ws_clf, 6, totales_clas)

                # Donut funcional
                ws_clf.add_image(_fig_donut(
                    ws_clf, col_datos=2, col_cats=1, min_row=2, max_row=5,
                    titulo_celda="F1", titulo_txt="Distribución Funcional de Taxa",
                    colores=[PLOTLY_VERDE, PLOTLY_ROJO, PLOTLY_AMBAR, PLOTLY_GRIS],
                ), "F2")

                # ─────────────────────────────────────────────────────
                # H-06  MICROORGANISMOS — detalle por categoría (fusión de
                # Benéficos + Fitopatógenos + Neutrales en una sola tabla
                # filtrable/ordenable en vez de 3 hojas casi idénticas)
                # ─────────────────────────────────────────────────────
                micro_datos = []
                for b in detalle_clas.get("benefico", []):
                    micro_datos.append(("🟢 Benéficos", b.get("nombre", ""),
                        round(float(b.get("porcentaje", 0) or 0), 4),
                        b.get("descripcion", ""), b.get("referencia", "")))
                for f in detalle_clas.get("fitopatogeno", []):
                    micro_datos.append(("🔴 Fitopatógenos", f.get("nombre", ""),
                        round(float(f.get("porcentaje", 0) or 0), 4),
                        f.get("descripcion", ""), f.get("referencia", "")))
                for n in detalle_clas.get("neutral", []):
                    micro_datos.append(("🔵 Neutrales", n.get("nombre", ""),
                        round(float(n.get("porcentaje", 0) or 0), 4),
                        n.get("descripcion", "") or "Sin clasificación funcional definida", ""))
                micro_rec = [{
                    "#": i + 1, "Organismo": org, "Categoría": cat,
                    "Abundancia_%": pct, "Descripción": desc, "Referencia": ref,
                } for i, (cat, org, pct, desc, ref) in enumerate(micro_datos)]
                df_micro = (pd.DataFrame(micro_rec) if micro_rec else
                            pd.DataFrame(columns=["#", "Organismo", "Categoría",
                                                  "Abundancia_%", "Descripción", "Referencia"]))
                _excel_safe_df(df_micro).to_excel(writer, index=False, sheet_name="Microorganismos_Detalle")
                ws_micro = writer.sheets["Microorganismos_Detalle"]
                _formatear_tabla(ws_micro, df_micro, "TablaMicroorganismos", col_clasif="Categoría")

                # ─────────────────────────────────────────────────────
                # H-09  ANÁLISIS DIFERENCIAL (si disponible)
                # ─────────────────────────────────────────────────────
                diferencial = analisis_dif.get("diferencial", [])
                beta_dif    = analisis_dif.get("beta", {})
                if diferencial:
                    dif_rec = [{
                        "#": i + 1,
                        "Taxón":              d.get("taxon", ""),
                        "Abundancia_Muestra_%": round(float(d.get("abundancia_a", 0)), 4),
                        "Abundancia_Ref_%":   round(float(d.get("abundancia_b", 0)), 4),
                        "Diferencia_pp":      round(float(d.get("diferencia", 0)), 4),
                        "Sentido":            (
                            "↑ Mayor en muestra" if d.get("diferencia", 0) > 0
                            else "↓ Menor en muestra" if d.get("diferencia", 0) < 0
                            else "= Sin diferencia"),
                    } for i, d in enumerate(diferencial)]
                    df_dif = pd.DataFrame(dif_rec)
                    _excel_safe_df(df_dif).to_excel(writer, index=False, sheet_name="Analisis_Diferencial")
                    ws_dif = writer.sheets["Analisis_Diferencial"]
                    _formatear_tabla(ws_dif, df_dif, "TablaDiferencial", header="azul")

                    # Info beta-diversidad vs. referencia
                    if beta_dif:
                        row_b = len(df_dif) + 4
                        ws_dif.cell(row=row_b, column=1,
                                    value="DIVERSIDAD BETA — Muestra vs. Referencia").font = fnt_seccion
                        for c in range(1, 7):
                            ws_dif.cell(row=row_b, column=c).fill = fill_seccion
                        metadatos = [
                            ("Taxa compartidos con referencia",
                             str(beta_dif.get("compartidos", "—"))),
                            ("Taxa exclusivos de esta muestra",
                             str(len(beta_dif.get("exclusivos", {}).get("exclusivos_a", [])))),
                            ("Taxa exclusivos de la referencia",
                             str(len(beta_dif.get("exclusivos", {}).get("exclusivos_b", [])))),
                            ("Índice de Jaccard",
                             f"{beta_dif.get('jaccard', 0):.4f}"),
                            ("Interpretación Jaccard",
                             _interp_jaccard(beta_dif.get("jaccard", 0))),
                        ]
                        for j, (k, v) in enumerate(metadatos, start=row_b + 1):
                            ws_dif.cell(row=j, column=1, value=k).font = fnt_bold
                            ws_dif.cell(row=j, column=2, value=v).font = fnt_normal
                            for c in range(1, 7):
                                ws_dif.cell(row=j, column=c).border = borde

            # ════════════════════════════════════════════════════════════
            # ██  MODO COMPARATIVO — N muestras
            # ════════════════════════════════════════════════════════════
            else:
                # ─────────────────────────────────────────────────────
                # H-01  RESUMEN COMPARATIVO
                # ─────────────────────────────────────────────────────
                shanval  = _div_valor(diversidad, "shannon")
                simpval  = _div_valor(diversidad, "simpson")
                equival  = _div_valor(diversidad, "equitatividad")
                riqval   = int(_div_valor(diversidad, "riqueza", todos_taxa))

                res2 = [["Campo", "Valor", "Notas"]]
                res2 += [
                    ["BioMicro — Reporte Comparativo de Salud Microbiológica", "", ""],
                    ["Fecha de generación", fecha_gen, ""],
                    ["Analista", analista, ""],
                    ["N° muestras comparadas", str(len(muestras)), ""],
                    ["", "", ""],
                    ["MUESTRAS INCLUIDAS", "", ""],
                ]
                for m in muestras:
                    cult = m.cultivo.nombre if getattr(m, "cultivo", None) else "N/A"
                    var  = m.variedad_clon.nombre if getattr(m, "variedad_clon", None) else "N/A"
                    res2.append([
                        str(m.codigo),
                        f"{cult} / {var}",
                        str(getattr(m, "localidad", "") or ""),
                    ])
                res2 += [
                    ["", "", ""],
                    ["PARÁMETROS DEL ANÁLISIS", "", ""],
                    ["Marcador molecular",   marcador_lbl, ""],
                    ["Nivel taxonómico",     nivel.capitalize(), ""],
                    ["Top N seleccionado",   str(top_n), ""],
                    ["Total taxa (global)",  str(total_taxa_global), "Unión de todos los taxa detectados"],
                    ["", "", ""],
                    ["DIVERSIDAD ALFA GLOBAL (promedios)", "", ""],
                    ["Riqueza de taxa (prom.)", str(riqval),
                     "Alta >100 | Moderada >30 | Baja ≤30"],
                    ["Shannon H' (prom.)", f"{shanval:.4f}", _interp_shannon(shanval)],
                    ["Simpson D (prom.)",  f"{simpval:.4f}", _interp_simpson(simpval)],
                    ["Equitatividad J' (prom.)", f"{equival:.4f}", _interp_equit(equival)],
                    ["", "", ""],
                    ["CLASIFICACIÓN FUNCIONAL GLOBAL", "", ""],
                    ["🟢 Taxa Benéficos",    str(totales_clas.get("benefico", 0)), ""],
                    ["🔴 Taxa Fitopatógenos",str(totales_clas.get("fitopatogeno", 0)), ""],
                    ["🔵 Taxa Neutrales",    str(totales_clas.get("neutral", 0)), ""],
                    ["⚪ Taxa Sin Clasificación",str(totales_clas.get("sin_clasificar", 0)), ""],
                    ["Índice Salud Global", str(indice_salud),
                     INTERP_SALUD.get(nivel_salud, "")],
                    ["Nivel cualitativo global", nivel_salud, ""],
                ]

                df_res2 = pd.DataFrame(res2[1:], columns=res2[0])
                _excel_safe_df(df_res2).to_excel(writer, index=False, sheet_name="Resumen_Comparativo")
                ws_rc = writer.sheets["Resumen_Comparativo"]

                SECCIONES_RC = {
                    "MUESTRAS INCLUIDAS", "PARÁMETROS DEL ANÁLISIS",
                    "DIVERSIDAD ALFA GLOBAL (promedios)", "CLASIFICACIÓN FUNCIONAL GLOBAL",
                }
                _hdr(ws_rc, 3)
                for row in ws_rc.iter_rows(min_row=2):
                    v = str(row[0].value or "")
                    if v in SECCIONES_RC:
                        for cell in row:
                            cell.fill = fill_seccion; cell.font = fnt_seccion
                            cell.border = borde
                    elif v.startswith("BioMicro"):
                        for cell in row:
                            cell.fill = fill_titulo
                            cell.font = Font(bold=True, color=CBLANCO, size=12)
                            cell.border = borde
                    elif v:
                        for cell in row:
                            cell.font = fnt_normal; cell.border = borde; cell.alignment = al_l
                _ajustar_cols(ws_rc, {"A": 34, "B": 25, "C": 65})
                _wrap(ws_rc, h=28)

                # ── Resumen ejecutivo interpretado (Fase 1) ─────────────
                fila_hsc = ws_rc.max_row + 2
                ws_rc.cell(row=fila_hsc, column=1, value="RESUMEN EJECUTIVO INTERPRETADO").font = fnt_seccion
                for col in range(1, 4):
                    c_sec = ws_rc.cell(row=fila_hsc, column=col)
                    c_sec.fill = fill_seccion
                    c_sec.border = borde
                ws_rc.row_dimensions[fila_hsc].height = 18
                fila_hsc += 1

                for col in range(4, 20):
                    ws_rc.column_dimensions[get_column_letter(col)].width = 4
                ws_rc.add_image(_fig_gauge(indice_salud, nivel_salud),
                                 f"{get_column_letter(4)}{fila_hsc}")
                fila_hsc += 2

                for parrafo in _generar_interpretacion_ejecutiva(datos):
                    c_par = ws_rc.cell(row=fila_hsc, column=1, value=parrafo)
                    c_par.font = fnt_normal
                    c_par.alignment = al_l
                    ws_rc.merge_cells(start_row=fila_hsc, start_column=1, end_row=fila_hsc, end_column=3)
                    ws_rc.row_dimensions[fila_hsc].height = 40
                    fila_hsc += 1

                # ─────────────────────────────────────────────────────
                # H-02  CUADRO COMPARATIVO POR MUESTRA
                # ─────────────────────────────────────────────────────
                cuad_rec = []
                for dpm in datos_por_muestra:
                    m    = dpm["muestra"]
                    div  = dpm.get("diversidad") or {}
                    tc   = dpm.get("totales_clas", {})
                    cult = m.cultivo.nombre if getattr(m, "cultivo", None) else "N/A"
                    var  = m.variedad_clon.nombre if getattr(m, "variedad_clon", None) else "N/A"
                    cuad_rec.append({
                        "Muestra":          str(m.codigo),
                        "Cultivo":          cult,
                        "Variedad":         var,
                        "Localidad":        str(getattr(m, "localidad", "") or ""),
                        "Índice_Salud":     dpm.get("indice_salud", 0),
                        "Nivel":            dpm.get("nivel_salud", "N/A"),
                        "Riqueza":          int(_div_valor(div, "riqueza")),
                        "Shannon_H'":       round(_div_valor(div, "shannon"), 4),
                        "Simpson_D":        round(_div_valor(div, "simpson"), 4),
                        "Equitatividad_J'": round(_div_valor(div, "equitatividad"), 4),
                        "Benéficos":        tc.get("benefico", 0),
                        "Fitopatógenos":    tc.get("fitopatogeno", 0),
                        "Neutrales":        tc.get("neutral", 0),
                        "Sin_Clasificacion":    tc.get("sin_clasificar", 0),
                    })
                df_cuad = (pd.DataFrame(cuad_rec) if cuad_rec
                           else pd.DataFrame(columns=["Muestra","Cultivo","Variedad",
                               "Localidad","Índice_Salud","Nivel","Riqueza",
                               "Shannon_H'","Simpson_D","Equitatividad_J'",
                               "Benéficos","Fitopatógenos","Neutrales","Sin_Clasificacion"]))
                _excel_safe_df(df_cuad).to_excel(writer, index=False, sheet_name="Cuadro_Comparativo")
                ws_cuad = writer.sheets["Cuadro_Comparativo"]
                _formatear_tabla(ws_cuad, df_cuad, "TablaCuadroComp")

                # Gráfico: Índice de salud por muestra
                if len(df_cuad) > 0:
                    colores_sal = [_NIVEL_COLORES.get(f.get("Nivel"), PLOTLY_VERDE)
                                   for f in cuad_rec]
                    ws_cuad.add_image(_fig_barras_v(
                        ws_cuad, col_datos=5, col_cats=1, min_row=2, max_row=len(df_cuad) + 1,
                        colores=colores_sal, titulo_celda="P2",
                        titulo_txt="Índice de Salud por Muestra",
                        y_titulo="Índice (0-100)", y_max=100,
                    ), "P3")

                # ─────────────────────────────────────────────────────
                # H-03  DIVERSIDAD ALFA DETALLADA POR MUESTRA
                # ─────────────────────────────────────────────────────
                def _interp_shannon_nivel(v):
                    v = float(v or 0)
                    if v >= 3.0: return "Alta (H'≥3)"
                    if v >= 2.0: return "Media-alta (2≤H'<3)"
                    if v >= 1.0: return "Media-baja (1≤H'<2)"
                    return "Baja (H'<1)"

                alfa_rec = []
                for dpm in datos_por_muestra:
                    div = dpm.get("diversidad") or {}
                    shan = round(_div_valor(div, "shannon"), 4)
                    alfa_rec.append({
                        "Muestra":                str(dpm["muestra"].codigo),
                        "Riqueza":                int(_div_valor(div, "riqueza")),
                        "Shannon_H'":             shan,
                        "Nivel_Diversidad":       _interp_shannon_nivel(shan),
                        "Simpson_D":              round(_div_valor(div, "simpson"), 4),
                        "Equitatividad_J'":       round(_div_valor(div, "equitatividad"), 4),
                    })
                # Fila promedio al final
                if alfa_rec:
                    n_r = len(alfa_rec)
                    prom_shan = round(sum(r["Shannon_H'"] for r in alfa_rec) / n_r, 4)
                    alfa_rec.append({
                        "Muestra":          "PROMEDIO",
                        "Riqueza":          round(sum(r["Riqueza"] for r in alfa_rec) / n_r, 1),
                        "Shannon_H'":       prom_shan,
                        "Nivel_Diversidad": _interp_shannon_nivel(prom_shan),
                        "Simpson_D":        round(sum(r["Simpson_D"]       for r in alfa_rec) / n_r, 4),
                        "Equitatividad_J'": round(sum(r["Equitatividad_J'"] for r in alfa_rec) / n_r, 4),
                    })

                df_alfa = (pd.DataFrame(alfa_rec) if alfa_rec
                           else pd.DataFrame(columns=["Muestra","Riqueza","Shannon_H'",
                                                      "Nivel_Diversidad","Simpson_D",
                                                      "Equitatividad_J'"]))
                _excel_safe_df(df_alfa).to_excel(writer, index=False, sheet_name="Diversidad_Alfa")
                ws_alfa = writer.sheets["Diversidad_Alfa"]
                _formatear_tabla(ws_alfa, df_alfa, "TablaDivAlfa", header="azul")
                # Fila promedio en negrita (después de _formatear_tabla, que
                # ya fijó la fuente normal en todas las celdas de datos)
                if alfa_rec:
                    for c in range(1, 7):
                        ws_alfa.cell(row=len(df_alfa) + 1, column=c).font = fnt_bold
                _caption_diversidad(ws_alfa, ws_alfa.max_row + 2, shanval, simpval)

                # Gráfico Shannon por muestra — colores por umbral absoluto
                # (<1 rojo, 1-2 naranja, 2-3 amarillo, ≥3 verde)
                n_data = len(alfa_rec) - 1 if alfa_rec else 0  # excluye fila PROMEDIO
                if n_data > 0:
                    colores_sh = []
                    for row_data in alfa_rec[:n_data]:
                        sv = float(row_data.get("Shannon_H'", 0) or 0)
                        if sv >= 3.0:   colores_sh.append("#16A34A")
                        elif sv >= 2.0: colores_sh.append("#EAB308")
                        elif sv >= 1.0: colores_sh.append("#F97316")
                        else:           colores_sh.append("#DC2626")
                    ws_alfa.add_image(_fig_barras_v(
                        ws_alfa, col_datos=3, col_cats=1, min_row=2, max_row=n_data + 1,
                        colores=colores_sh, titulo_celda="H2",
                        titulo_txt="Shannon H' por Muestra (colores por umbral)",
                        y_titulo="Shannon H'",
                    ), "H3")

                # ─────────────────────────────────────────────────────
                # H-04  DIVERSIDAD BETA
                # ─────────────────────────────────────────────────────
                # Construir sets de taxa por muestra
                taxa_sets: dict = {}
                for dpm in datos_por_muestra:
                    # _excel_safe: cod y los nombres de taxón terminan como valores de
                    # celda en esta hoja (Diversidad_Beta se escribe con openpyxl directo,
                    # no vía DataFrame, así que _excel_safe_df no los cubre).
                    cod = _excel_safe(str(dpm["muestra"].codigo))
                    if "todos_taxa_nombres" in dpm:
                        taxa_sets[cod] = {_excel_safe(n) for n in dpm["todos_taxa_nombres"]}
                    else:
                        taxa_sets[cod] = {
                            _excel_safe(str(r.get("taxonomia", ""))) for r in dpm.get("top_taxa", [])
                            if r.get("taxonomia")
                        }

                codigos_m = list(taxa_sets.keys())
                ws_beta = wb.create_sheet("Diversidad_Beta")

                # — Sección 1: Matriz Jaccard —
                fila = 1
                ws_beta.cell(row=fila, column=1,
                             value="SIMILITUD DE JACCARD (DIVERSIDAD BETA)").font = fnt_seccion
                for c in range(1, len(codigos_m) + 2):
                    ws_beta.cell(row=fila, column=c).fill = fill_seccion
                    ws_beta.cell(row=fila, column=c).border = borde
                ws_beta.row_dimensions[fila].height = 20
                fila += 1

                # Encabezados columnas
                ws_beta.cell(row=fila, column=1, value="Muestra").font = fnt_bold
                ws_beta.cell(row=fila, column=1).fill = fill_hdr
                ws_beta.cell(row=fila, column=1).font = fnt_hdr
                ws_beta.cell(row=fila, column=1).alignment = al_c
                for j, cod in enumerate(codigos_m, start=2):
                    c = ws_beta.cell(row=fila, column=j, value=cod)
                    c.fill = fill_hdr; c.font = fnt_hdr; c.alignment = al_c
                    c.border = borde

                for i, cod_a in enumerate(codigos_m):
                    fila_j = fila + 1 + i
                    ws_beta.cell(row=fila_j, column=1, value=cod_a).font = fnt_bold
                    ws_beta.cell(row=fila_j, column=1).fill = fill_hdr
                    ws_beta.cell(row=fila_j, column=1).alignment = al_c
                    ws_beta.cell(row=fila_j, column=1).border = borde
                    for j, cod_b in enumerate(codigos_m, start=2):
                        set_a = taxa_sets.get(cod_a, set())
                        set_b = taxa_sets.get(cod_b, set())
                        if cod_a == cod_b:
                            val = 1.0
                        else:
                            union = len(set_a | set_b)
                            val   = round(len(set_a & set_b) / union, 4) if union else 0.0
                        c_cell = ws_beta.cell(row=fila_j, column=j, value=val)
                        c_cell.font   = fnt_normal
                        c_cell.border = borde
                        c_cell.alignment = al_c
                        c_cell.number_format = "0.0000"
                        # Coloreado: verde oscuro si similar, rojo si distinto
                        if val == 1.0:
                            c_cell.fill = PatternFill("solid", fgColor="D4EDDA")
                        elif val >= 0.5:
                            c_cell.fill = PatternFill("solid", fgColor=CV_CLAR)
                        elif val >= 0.3:
                            c_cell.fill = PatternFill("solid", fgColor="FFF3CD")
                        else:
                            c_cell.fill = PatternFill("solid", fgColor="FAD7D7")

                for col_idx in range(1, len(codigos_m) + 2):
                    ws_beta.column_dimensions[get_column_letter(col_idx)].width = 16

                # Heatmap de distribución de abundancia (muestra × taxón) —
                # solo tiene sentido en modo comparativo, con 2+ muestras.
                matriz_hm, taxa_hm, cols_hm = _datos_heatmap_muestras(datos_por_muestra)
                if matriz_hm:
                    col_hm = get_column_letter(len(codigos_m) + 3)
                    _titulo_celda(ws_beta, f"{col_hm}1", "Distribución de Abundancia (Top taxa)", CV_OSC)
                    ws_beta.add_image(
                        _fig_heatmap(matriz_hm, taxa_hm, cols_hm), f"{col_hm}2")

                # — Sección 2: Taxa compartidos por par —
                fila_shared = fila + len(codigos_m) + 3
                ws_beta.cell(row=fila_shared, column=1,
                             value="TAXA COMPARTIDOS ENTRE PARES").font = fnt_seccion
                for c in range(1, len(codigos_m) + 2):
                    ws_beta.cell(row=fila_shared, column=c).fill = fill_seccion
                    ws_beta.cell(row=fila_shared, column=c).border = borde
                ws_beta.row_dimensions[fila_shared].height = 18
                fila_shared += 1

                ws_beta.cell(row=fila_shared, column=1, value="Muestra").font = fnt_hdr
                ws_beta.cell(row=fila_shared, column=1).fill = fill_hdr
                ws_beta.cell(row=fila_shared, column=1).alignment = al_c
                for j, cod in enumerate(codigos_m, start=2):
                    c = ws_beta.cell(row=fila_shared, column=j, value=cod)
                    c.fill = fill_hdr; c.font = fnt_hdr; c.alignment = al_c; c.border = borde
                for i, cod_a in enumerate(codigos_m):
                    fi = fila_shared + 1 + i
                    ws_beta.cell(row=fi, column=1, value=cod_a).font = fnt_bold
                    ws_beta.cell(row=fi, column=1).fill = fill_hdr
                    ws_beta.cell(row=fi, column=1).alignment = al_c
                    ws_beta.cell(row=fi, column=1).border = borde
                    for j, cod_b in enumerate(codigos_m, start=2):
                        n_comp = len(taxa_sets.get(cod_a, set()) & taxa_sets.get(cod_b, set()))
                        c = ws_beta.cell(row=fi, column=j, value=n_comp)
                        c.font = fnt_normal; c.border = borde; c.alignment = al_c

                # — Sección 3: Microbioma core y taxa únicos —
                fila_core = fila_shared + len(codigos_m) + 3
                ws_beta.cell(row=fila_core, column=1,
                             value="MICROBIOMA CORE (taxa presentes en TODAS las muestras)").font = fnt_seccion
                ws_beta.cell(row=fila_core, column=1).fill = fill_seccion
                ws_beta.row_dimensions[fila_core].height = 18

                if taxa_sets:
                    all_sets = list(taxa_sets.values())
                    core_taxa = all_sets[0].copy()
                    for s in all_sets[1:]:
                        core_taxa &= s
                else:
                    core_taxa = set()

                fila_core += 1
                ws_beta.cell(row=fila_core, column=1,
                             value=f"Total taxa core: {len(core_taxa)}").font = fnt_bold
                fila_core += 1
                for taxon in sorted(core_taxa):
                    ws_beta.cell(row=fila_core, column=1, value=taxon).font = fnt_normal
                    ws_beta.cell(row=fila_core, column=1).border = borde
                    fila_core += 1

                # Taxa únicos por muestra
                fila_uniq = fila_core + 2
                ws_beta.cell(row=fila_uniq, column=1,
                             value="TAXA EXCLUSIVOS POR MUESTRA (únicos en cada muestra)").font = fnt_seccion
                ws_beta.cell(row=fila_uniq, column=1).fill = fill_seccion
                fila_uniq += 1
                for cod, taxa in taxa_sets.items():
                    otros = set()
                    for other_cod, other_set in taxa_sets.items():
                        if other_cod != cod:
                            otros |= other_set
                    unicos = sorted(taxa - otros)
                    ws_beta.cell(row=fila_uniq, column=1,
                                 value=f"{cod} — {len(unicos)} taxa únicos").font = fnt_bold
                    fila_uniq += 1
                    for taxon in unicos:
                        ws_beta.cell(row=fila_uniq, column=1, value=taxon).font = fnt_normal
                        ws_beta.cell(row=fila_uniq, column=1).border = borde
                        fila_uniq += 1
                    fila_uniq += 1

                # ─────────────────────────────────────────────────────
                # H-05  TOP N GLOBAL
                # ─────────────────────────────────────────────────────
                top_rec = [{
                    "#": i + 1,
                    "Taxón":          r.get("taxonomia", r.get("nombre", "?")),
                    "Total_Hits":     int(r.get("total_hits", r.get("hits", 0)) or 0),
                    "Abundancia_%":   round(float(r.get("total_porcentaje",
                                                  r.get("porcentaje", 0)) or 0), 4),
                    "Clasificación":  r.get("clasificacion", "sin_clasificar"),
                } for i, r in enumerate(top_taxa)]
                df_top = (pd.DataFrame(top_rec) if top_rec
                          else pd.DataFrame(columns=["#","Taxón","Total_Hits",
                                                     "Abundancia_%","Clasificación"]))
                _excel_safe_df(df_top).to_excel(writer, index=False, sheet_name="Top_N_Global")
                ws_top = writer.sheets["Top_N_Global"]
                _formatear_tabla(ws_top, df_top, "TablaTopNGlobal", col_clasif="Clasificación")
                _caption_top_taxa(ws_top, len(df_top), top_rec[0]["Taxón"] if top_rec else None)
                if len(df_top) > 0:
                    ws_top.add_image(_fig_barras_h(
                        ws_top, n_filas=len(df_top), col_datos=4, col_cats=2, col_clasif=5,
                        titulo_celda="G2",
                        titulo_txt=f"Top {top_n} Taxa Global — Abundancia (%) · {tipo}",
                    ), "G3")
                    ids_tm2, lbl_tm2, par_tm2, val_tm2, col_tm2 = _datos_treemap_taxa(top_rec)
                    ws_top.add_image(_fig_treemap(
                        ids_tm2, lbl_tm2, par_tm2, val_tm2, colores=col_tm2,
                        titulo_txt="Treemap de Abundancias por Clasificación",
                    ), "V3")

                # ─────────────────────────────────────────────────────
                # H-06  TAXONOMÍA COMPLETA
                # ─────────────────────────────────────────────────────
                todos_rec = [{
                    "#": i + 1,
                    "Taxón":         r.get("taxonomia", r.get("nombre", "?")),
                    "Total_Hits":    int(r.get("total_hits", r.get("hits", 0)) or 0),
                    "Abundancia_%":  round(float(r.get("total_porcentaje",
                                                 r.get("porcentaje", 0)) or 0), 4),
                    "Clasificación": r.get("clasificacion", "sin_clasificar"),
                } for i, r in enumerate(todos_taxa)]
                df_tod = (pd.DataFrame(todos_rec) if todos_rec
                          else pd.DataFrame(columns=["#","Taxón","Total_Hits",
                                                     "Abundancia_%","Clasificación"]))
                _excel_safe_df(df_tod).to_excel(writer, index=False, sheet_name="Taxonomia_Completa")
                ws_tod = writer.sheets["Taxonomia_Completa"]
                _formatear_tabla(ws_tod, df_tod, "TablaTaxonomia", col_clasif="Clasificación")
                if jerarquia_taxonomica:
                    ids_sb, lbl_sb, par_sb, val_sb = _datos_sunburst_taxonomia(
                        jerarquia_taxonomica, nivel_campo_jerarquia)
                    _titulo_celda(ws_tod, "G1", "Jerarquía Taxonómica", CV_OSC)
                    ws_tod.add_image(_fig_sunburst(ids_sb, lbl_sb, par_sb, val_sb), "G2")

                # ─────────────────────────────────────────────────────
                # H-07  CLASIFICACIÓN POR MUESTRA
                # ─────────────────────────────────────────────────────
                cls_rec = []
                for dpm in datos_por_muestra:
                    tc   = dpm.get("totales_clas", {})
                    tot  = max(sum(tc.values()), 1)
                    cls_rec.append({
                        "Muestra":         str(dpm["muestra"].codigo),
                        "Benéficos":       tc.get("benefico", 0),
                        "Fitopatógenos":   tc.get("fitopatogeno", 0),
                        "Neutrales":       tc.get("neutral", 0),
                        "Sin_Clasificacion":   tc.get("sin_clasificar", 0),
                        "Total_Taxa":      tot,
                        "%_Benéficos":     round(tc.get("benefico",0)/tot*100, 2),
                        "%_Fitopatógenos": round(tc.get("fitopatogeno",0)/tot*100, 2),
                    })
                df_cls = (pd.DataFrame(cls_rec) if cls_rec
                          else pd.DataFrame(columns=[
                              "Muestra","Benéficos","Fitopatógenos","Neutrales",
                              "Sin_Clasificacion","Total_Taxa","%_Benéficos","%_Fitopatógenos"]))
                _excel_safe_df(df_cls).to_excel(writer, index=False, sheet_name="Clas_Por_Muestra")
                ws_cls = writer.sheets["Clas_Por_Muestra"]
                _formatear_tabla(ws_cls, df_cls, "TablaClsPorMuestra")
                _caption_clasificacion(ws_cls, ws_cls.max_row + 2, totales_clas, ancho_cols=7)

                # ─────────────────────────────────────────────────────
                # H-08  MICROORGANISMOS — detalle por categoría (global,
                # fusión de Benéficos + Fitopatógenos + Neutrales)
                # ─────────────────────────────────────────────────────
                micro_datos = []
                for b in detalle_clas.get("benefico", []):
                    micro_datos.append(("🟢 Benéficos", b.get("nombre", ""),
                        round(float(b.get("porcentaje", 0) or 0), 4),
                        b.get("descripcion", ""), b.get("referencia", "")))
                for f in detalle_clas.get("fitopatogeno", []):
                    micro_datos.append(("🔴 Fitopatógenos", f.get("nombre", ""),
                        round(float(f.get("porcentaje", 0) or 0), 4),
                        f.get("descripcion", ""), f.get("referencia", "")))
                for n in detalle_clas.get("neutral", []):
                    micro_datos.append(("🔵 Neutrales", n.get("nombre", ""),
                        round(float(n.get("porcentaje", 0) or 0), 4),
                        n.get("descripcion", "") or "Sin clasificación funcional definida", ""))
                micro_rec = [{
                    "#": i + 1, "Organismo": org, "Categoría": cat,
                    "Abundancia_%": pct, "Descripción": desc, "Referencia": ref,
                } for i, (cat, org, pct, desc, ref) in enumerate(micro_datos)]
                df_micro = (pd.DataFrame(micro_rec) if micro_rec else
                            pd.DataFrame(columns=["#", "Organismo", "Categoría",
                                                  "Abundancia_%", "Descripción", "Referencia"]))
                _excel_safe_df(df_micro).to_excel(writer, index=False, sheet_name="Microorganismos_Detalle")
                ws_micro = writer.sheets["Microorganismos_Detalle"]
                _formatear_tabla(ws_micro, df_micro, "TablaMicroorganismos", col_clasif="Categoría")

            # ─────────────────────────────────────────────────────────────
            # DASHBOARD — tarjetas KPI + visualizaciones consolidadas (Fase 1.2)
            # ─────────────────────────────────────────────────────────────
            ws_dash = wb.create_sheet("Dashboard")
            ws_dash.sheet_view.showGridLines = False

            ws_dash.merge_cells(start_row=1, start_column=1, end_row=1, end_column=24)
            c_tit_d = ws_dash.cell(row=1, column=1, value="🌱  Dashboard — BioMicro")
            c_tit_d.font = Font(bold=True, color=CBLANCO, size=16)
            c_tit_d.fill = fill_titulo
            c_tit_d.alignment = al_c
            ws_dash.row_dimensions[1].height = 30

            def _kpi_card(fila, col, titulo, valor, color_hex, ancho_cols=4):
                color = str(color_hex).lstrip("#")
                fill = PatternFill("solid", fgColor=color)
                ws_dash.merge_cells(start_row=fila, start_column=col,
                                     end_row=fila + 1, end_column=col + ancho_cols - 1)
                c_val = ws_dash.cell(row=fila, column=col, value=valor)
                c_val.font = Font(bold=True, color="FFFFFF", size=20)
                c_val.alignment = al_c
                ws_dash.merge_cells(start_row=fila + 2, start_column=col,
                                     end_row=fila + 2, end_column=col + ancho_cols - 1)
                c_lbl = ws_dash.cell(row=fila + 2, column=col, value=titulo)
                c_lbl.font = Font(bold=True, color="FFFFFF", size=9)
                c_lbl.alignment = al_c
                for r in range(fila, fila + 3):
                    for c in range(col, col + ancho_cols):
                        ws_dash.cell(row=r, column=c).fill = fill
                ws_dash.row_dimensions[fila].height = 34
                ws_dash.row_dimensions[fila + 1].height = 10
                ws_dash.row_dimensions[fila + 2].height = 18

            color_salud_d = _NIVEL_COLORES.get(nivel_salud, "#64748b")
            _kpi_card(3, 1,  "Total Taxa Detectados", total_taxa_global, PLOTLY_VERDE_OS)
            _kpi_card(3, 6,  "Shannon H'", f"{shanval:.2f}", PLOTLY_AZUL)
            _kpi_card(3, 11, "Índice de Salud", f"{indice_salud}/100", color_salud_d)
            _kpi_card(3, 16, "Taxa Benéficos", totales_clas.get("benefico", 0), PLOTLY_VERDE)
            _kpi_card(3, 21, "Taxa Fitopatógenos", totales_clas.get("fitopatogeno", 0), PLOTLY_ROJO)

            # Gauge + Radar
            ws_dash.add_image(_fig_gauge(indice_salud, nivel_salud), "A8")
            cat_radar, val_radar = _datos_radar_diversidad(
                riqval, shanval, simpval, equival, indice_salud)
            ws_dash.add_image(_fig_radar(cat_radar, val_radar), "N8")

            # ── Tablas de apoyo (no visibles en el panel, alimentan los
            # gráficos de abajo con el mismo criterio de lectura-desde-celda
            # que usa el resto del reporte) ─────────────────────────────
            fila_ap = 160
            ws_dash.cell(row=fila_ap, column=1,
                         value="Datos de apoyo (alimentan los gráficos de este panel)").font = fnt_gris
            fila_ap += 1
            ws_dash.cell(row=fila_ap, column=1, value="Categoría").font = fnt_hdr
            ws_dash.cell(row=fila_ap, column=2, value="N°_Taxa").font = fnt_hdr
            fila_clf0 = fila_ap + 1
            for i, (cod, lbl) in enumerate([
                ("benefico", "Benéficos"), ("fitopatogeno", "Fitopatógenos"),
                ("neutral", "Neutrales"), ("sin_clasificar", "Sin clasificación"),
            ]):
                ws_dash.cell(row=fila_clf0 + i, column=1, value=lbl)
                ws_dash.cell(row=fila_clf0 + i, column=2, value=totales_clas.get(cod, 0))

            # Donut + Top 20 microorganismos
            ws_dash.add_image(_fig_donut(
                ws_dash, col_datos=2, col_cats=1, min_row=fila_clf0, max_row=fila_clf0 + 3,
                titulo_txt="Distribución Funcional",
            ), "A36")

            fila_top0 = fila_clf0 + 6
            top20 = todos_taxa[:20]
            for i, r in enumerate(top20):
                fr = fila_top0 + i
                ws_dash.cell(row=fr, column=1,
                             value=_excel_safe(str(r.get("taxonomia", r.get("nombre", "?")))))
                ws_dash.cell(row=fr, column=2,
                             value=round(float(r.get("total_porcentaje",
                                                r.get("porcentaje", 0)) or 0), 4))
                ws_dash.cell(row=fr, column=3, value=r.get("clasificacion", "sin_clasificar"))
            if top20:
                ws_dash.add_image(_fig_barras_h(
                    ws_dash, n_filas=len(top20), col_datos=2, col_cats=1, col_clasif=3,
                    fila_inicio=fila_top0, titulo_txt="Top 20 Microorganismos — Abundancia (%)",
                ), "N36")

            # Sunburst taxonómico + Treemap de abundancias
            if jerarquia_taxonomica:
                ids_sb_d, lbl_sb_d, par_sb_d, val_sb_d = _datos_sunburst_taxonomia(
                    jerarquia_taxonomica, nivel_campo_jerarquia)
                ws_dash.add_image(_fig_sunburst(ids_sb_d, lbl_sb_d, par_sb_d, val_sb_d), "A72")
            if todos_taxa:
                todos_rec_dash = [{
                    "Taxón": r.get("taxonomia", r.get("nombre", "?")),
                    "Total_Hits": int(r.get("total_hits", r.get("hits", 0)) or 0),
                    "Clasificación": r.get("clasificacion", "sin_clasificar"),
                } for r in todos_taxa]
                ids_tm_d, lbl_tm_d, par_tm_d, val_tm_d, col_tm_d = _datos_treemap_taxa(
                    todos_rec_dash, top=25)
                ws_dash.add_image(_fig_treemap(
                    ids_tm_d, lbl_tm_d, par_tm_d, val_tm_d, colores=col_tm_d,
                    titulo_txt="Treemap de Abundancias",
                ), "N72")

            # Heatmap de distribución — solo modo comparativo (2+ muestras)
            if is_comparativo:
                matriz_hm_d, taxa_hm_d, cols_hm_d = _datos_heatmap_muestras(datos_por_muestra)
                if matriz_hm_d:
                    ws_dash.add_image(_fig_heatmap(
                        matriz_hm_d, taxa_hm_d, cols_hm_d, ancho_px=1600, alto_px=520,
                    ), "A108")

            ws_dash.cell(row=157, column=1,
                         value="Generado por BioMicro").font = fnt_gris

            # ── Fase 1: Portada / Índice / Conclusiones / Recomendaciones ──
            # Aditivo: agrega hojas y una fila de navegación al tope de las
            # que ya existen, sin tocar su contenido (ver _retro_freeze_y_nav).
            hojas_originales = list(wb.sheetnames)
            # El Dashboard se construyó al final (necesita datos ya calculados
            # en ambos modos), pero visualmente debe ir primero, justo
            # después del Índice.
            hojas_originales.remove("Dashboard")
            hojas_originales.insert(0, "Dashboard")

            FREEZE_OVERRIDES = {"Diversidad_Beta": "B4"}
            for _nombre_hoja in hojas_originales:
                _retro_freeze_y_nav(
                    wb[_nombre_hoja],
                    freeze_cell=FREEZE_OVERRIDES.get(_nombre_hoja, "A3"),
                    titulo_extra=_TITULO_EXTRA_HOJAS.get(_nombre_hoja),
                )

            _construir_hoja_conclusiones_recomendaciones(wb, datos)
            _construir_hoja_portada(wb, datos)
            _construir_hoja_indice(wb, hojas_originales + ["Conclusiones_Recomendaciones"])

            _orden_final = ["Portada", "Índice"] + hojas_originales + ["Conclusiones_Recomendaciones"]
            wb._sheets = [wb[_n] for _n in _orden_final]
            wb.active = 0

        # ── Respuesta HTTP ────────────────────────────────────────────────
        buffer.seek(0)
        fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
        modo  = "comparativo" if is_comparativo else "individual"
        nombre = f"reporte_{modo}_{tipo}_{nivel}_top{top_n}_{fecha}.xlsx"
        response = HttpResponse(
            buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return response

    # ------------------------------------------------------------------
    # Métodos legacy
    # ------------------------------------------------------------------

    @staticmethod
    def exportar_json(datos, nombre_archivo=None):
        """Exporta estructuras de datos o DataFrames a formato JSON unificado."""
        if isinstance(datos, pd.DataFrame):
            json_str = datos.to_json(orient='records', indent=2)
        elif isinstance(datos, dict):
            json_str = json.dumps(datos, indent=2, default=str)
        elif isinstance(datos, list):
            json_str = json.dumps(datos, indent=2, default=str)
        else:
            return None

        if nombre_archivo is None:
            return json_str

        nombre_seguro = slugify(nombre_archivo.replace('.json', '')) + '.json'
        response = HttpResponse(json_str, content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="{nombre_seguro}"'
        return response

    @staticmethod
    def exportar_csv_avanzado(df, nombre_archivo=None, incluir_estadisticas=False):
        """Exporta DataFrames biológicos a CSV."""
        if df.empty:
            return None

        buffer = BytesIO()
        df.to_csv(buffer, index=False, encoding='utf-8')

        if incluir_estadisticas:
            stats_data = {}
            for col in df.columns:
                if df[col].dtype in ['float64', 'int64']:
                    stats_data[col] = [f"Media: {df[col].mean():.4f}"]
                else:
                    stats_data[col] = ["N/A"]
            stats_df = pd.DataFrame(stats_data)
            stats_df.to_csv(buffer, index=False, encoding='utf-8', mode='a')

        buffer.seek(0)

        if nombre_archivo is None:
            return buffer.getvalue()

        nombre_seguro = slugify(nombre_archivo.replace('.csv', '')) + '.csv'
        response = HttpResponse(buffer.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{nombre_seguro}"'
        return response

    @staticmethod
    def generar_pdf_completo(titulo, datos_analisis, df_datos=None,
                             usuario=None, formato_pagina="A4", muestra_obj=None,
                             chart_images=None):
        """Genera un reporte PDF formal de calidad científica utilizando ReportLab Platypus."""
        pagesize = A4 if formato_pagina == "A4" else letter
        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=pagesize,
            rightMargin=36, leftMargin=36,
            topMargin=40, bottomMargin=40
        )

        styles = getSampleStyleSheet()

        COLOR_PRIMARY   = colors.HexColor('#1b4332')
        COLOR_SECONDARY = colors.HexColor('#2d6a4f')
        COLOR_LIGHT     = colors.HexColor('#f8f9fa')

        style_titulo = ParagraphStyle(
            'ScientificTitle', parent=styles['Heading1'], fontSize=20, leading=24,
            textColor=COLOR_PRIMARY, spaceAfter=15, alignment=TA_LEFT, fontName='Helvetica-Bold',
        )
        style_heading = ParagraphStyle(
            'ScientificHeading', parent=styles['Heading2'], fontSize=12, leading=16,
            textColor=COLOR_SECONDARY, spaceBefore=12, spaceAfter=6, fontName='Helvetica-Bold',
        )
        style_body = ParagraphStyle(
            'ScientificBody', parent=styles['Normal'], fontSize=9.5, leading=13,
            textColor=colors.HexColor('#212529'),
        )
        style_th = ParagraphStyle(
            'TableTh', parent=styles['Normal'], fontSize=9, leading=11,
            textColor=colors.white, fontName='Helvetica-Bold',
        )

        contenido = []

        contenido.append(Paragraph(titulo, style_titulo))
        contenido.append(Paragraph(f"<b>Fecha de Generación:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", style_body))
        contenido.append(Paragraph(f"<b>Investigador/Analista:</b> {usuario or 'Sistema Central'}", style_body))
        contenido.append(Spacer(1, 10))

        if muestra_obj is not None:
            contenido.append(Paragraph("Control de Trazabilidad Geoclimática", style_heading))

            cultivo_nom = muestra_obj.cultivo.nombre if hasattr(muestra_obj, 'cultivo') and muestra_obj.cultivo else "N/A"
            var_nom = muestra_obj.variedad_clon.nombre if hasattr(muestra_obj, 'variedad_clon') and muestra_obj.variedad_clon else "N/A"
            obs_text = muestra_obj.observaciones if getattr(muestra_obj, 'observaciones', None) else "Sin novedades"

            meta_tabla = [
                [Paragraph("<b>Muestra Código:</b>", style_body), Paragraph(str(muestra_obj.codigo), style_body),
                 Paragraph("<b>Cultivo Base:</b>", style_body), Paragraph(str(cultivo_nom), style_body)],
                [Paragraph("<b>Variedad / Clon:</b>", style_body), Paragraph(str(var_nom), style_body),
                 Paragraph("<b>Tipo de Muestra:</b>", style_body), Paragraph(str(getattr(muestra_obj, 'tipo_muestra', 'N/A')), style_body)],
                [Paragraph("<b>Localidad:</b>", style_body), Paragraph(str(getattr(muestra_obj, 'localidad', 'N/A')), style_body),
                 Paragraph("<b>Finca / Lote:</b>", style_body), Paragraph(str(getattr(muestra_obj, 'finca_lote', 'N/A')), style_body)],
                [Paragraph("<b>Altitud:</b>", style_body), Paragraph(f"{getattr(muestra_obj, 'altitud', 0)} msnm", style_body),
                 Paragraph("<b>Observaciones:</b>", style_body), Paragraph(str(obs_text), style_body)],
            ]
            t_meta = Table(meta_tabla, colWidths=[100, 160, 100, 160])
            t_meta.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), COLOR_LIGHT),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e9ecef')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            contenido.append(t_meta)
            contenido.append(Spacer(1, 10))

        if datos_analisis:
            contenido.append(Paragraph("Métricas Analíticas de la Comunidad Microbiana", style_heading))
            for seccion, valores in datos_analisis.items():
                contenido.append(Paragraph(f"<b>• {seccion}:</b>", style_body))
                if isinstance(valores, dict):
                    for k, v in valores.items():
                        contenido.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;- {k}: {v}", style_body))
                elif isinstance(valores, list):
                    for item in valores:
                        contenido.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;- {item}", style_body))
                else:
                    contenido.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;{str(valores)}", style_body))
            contenido.append(Spacer(1, 10))

        if df_datos is not None and not df_datos.empty:
            contenido.append(Paragraph("Distribución de Abundancia Taxonómica Relativa", style_heading))

            num_cols = len(df_datos.columns)
            anchura_disponible = pagesize[0] - 72
            ancho_tax = 180
            ancho_resto = (anchura_disponible - ancho_tax) / (num_cols - 1) if num_cols > 1 else anchura_disponible
            col_widths = [ancho_tax] + [ancho_resto] * (num_cols - 1)

            tabla_header = [Paragraph(str(col), style_th) for col in df_datos.columns]
            tabla_filas = []
            for _, fila in df_datos.iterrows():
                fila_convertida = []
                for val in fila:
                    texto_celda = f"{val:.4f}%" if isinstance(val, (float, int)) and val <= 100.0 and val > 0.0 else str(val)
                    fila_convertida.append(Paragraph(texto_celda, style_body))
                tabla_filas.append(fila_convertida)

            datos_reportlab = [tabla_header] + tabla_filas
            tabla_datos = Table(datos_reportlab, colWidths=col_widths, repeatRows=1)
            tabla_datos.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), COLOR_SECONDARY),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f4f9f4')]),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#94a3b8')),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            contenido.append(tabla_datos)

        if chart_images:
            TITULOS_GRAFICAS = {
                'clasificacion': 'Microorganismos por Muestra y Clasificación Funcional',
            }
            ancho_disponible = pagesize[0] - 72
            for clave, b64_str in chart_images.items():
                if not b64_str or ',' not in b64_str:
                    continue
                try:
                    titulo_graf = TITULOS_GRAFICAS.get(clave, clave.replace('_', ' ').title())
                    contenido.append(Spacer(1, 18))
                    contenido.append(Paragraph(titulo_graf, style_heading))
                    img_data = base64.b64decode(b64_str.split(',')[1])
                    img_buf = BytesIO(img_data)
                    rl_img = RLImage(img_buf, width=ancho_disponible, height=ancho_disponible * 0.38)
                    contenido.append(rl_img)
                except Exception as exc:
                    contenido.append(Paragraph(f"[Error al renderizar gráfica: {exc}]", style_body))

        contenido.append(Spacer(1, 15))
        contenido.append(Paragraph(
            "<font color='#64748b'><i>Nota: Este documento constituye un reporte técnico automatizado emitido por el "
            "Pipeline Bioinformático de Análisis de Suelos. Los resultados están sujetos al umbral del Top N seleccionado "
            "y las taxonomías remanentes han sido consolidadas de forma proporcional.</i></font>",
            style_body,
        ))

        doc.build(contenido, onFirstPage=_pdf_footer, onLaterPages=_pdf_footer)
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def exportar_pdf_response(titulo, datos_analisis, df_datos=None,
                              usuario=None, nombre_archivo=None, muestra_obj=None,
                              chart_images=None):
        """Envuelve el binario del PDF en una respuesta de descarga HTTP protegida para Django."""
        pdf_bytes = ExportService.generar_pdf_completo(
            titulo, datos_analisis, df_datos, usuario,
            muestra_obj=muestra_obj, chart_images=chart_images,
        )

        if nombre_archivo is None:
            fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
            nombre_archivo = f"reporte_microbioma_{fecha}.pdf"

        nombre_seguro = slugify(nombre_archivo.replace('.pdf', '')) + '.pdf'
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{nombre_seguro}"'
        return response

    @staticmethod
    def generar_html_reporte(titulo, datos_analisis, df_datos=None,
                             usuario=None, nombre_archivo=None, muestra_obj=None):
        """Genera un reporte interpretativo interactivo en HTML limpio estructurado."""
        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <title>{titulo}</title>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 30px; background-color: #f1f5f9; color: #1e293b; }}
                .container {{ max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }}
                h1 {{ color: #1b4332; text-align: center; border-bottom: 4px solid #2d6a4f; padding-bottom: 12px; margin-bottom: 25px; }}
                h2 {{ color: #2d6a4f; margin-top: 25px; border-left: 5px solid #2d6a4f; padding-left: 12px; font-size: 1.3em; }}
                .grid-meta {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; background: #f8f9fa; padding: 20px; border: 1px solid #e2e8f0; border-radius: 6px; margin-bottom: 20px; }}
                .meta-item {{ font-size: 14px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; }}
                th {{ background-color: #2d6a4f; color: white; padding: 10px; text-align: left; font-weight: 600; }}
                td {{ border: 1px solid #e2e8f0; padding: 10px; }}
                tr:nth-child(even) {{ background-color: #f8fafc; }}
                tr:hover {{ background-color: #f1f5f9; }}
                .footer {{ margin-top: 40px; text-align: center; color: #64748b; font-size: 12px; border-top: 1px solid #e2e8f0; padding-top: 15px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>{titulo}</h1>
                <div class="grid-meta">
                    <div class="meta-item"><strong>Fecha de Reporte:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</div>
                    <div class="meta-item"><strong>Usuario:</strong> {usuario or 'Sistema Central'}</div>
        """

        if muestra_obj is not None:
            cultivo_nom = muestra_obj.cultivo.nombre if hasattr(muestra_obj, 'cultivo') and muestra_obj.cultivo else "N/A"
            var_nom = muestra_obj.variedad_clon.nombre if hasattr(muestra_obj, 'variedad_clon') and muestra_obj.variedad_clon else "N/A"

            html += f"""
                    <div class="meta-item"><strong>Localidad:</strong> {getattr(muestra_obj, 'localidad', 'N/A')}</div>
                    <div class="meta-item"><strong>Finca / Lote:</strong> {getattr(muestra_obj, 'finca_lote', 'N/A')}</div>
                    <div class="meta-item"><strong>Altitud:</strong> {getattr(muestra_obj, 'altitud', 0)} msnm</div>
                    <div class="meta-item"><strong>Cultivo / Variedad:</strong> {cultivo_nom} ({var_nom})</div>
            """

        html += """
                </div>
        """

        for seccion, valores in datos_analisis.items():
            html += f"<h2>{seccion}</h2>"
            if isinstance(valores, dict):
                html += "<table>"
                for k, v in valores.items():
                    html += f"<tr><td style='width:30%; font-weight:600;'>{k}</td><td>{v}</td></tr>"
                html += "</table>"
            elif isinstance(valores, list):
                html += "<ul style='padding-left:20px; line-height: 1.6;'>"
                for item in valores:
                    html += f"<li>{item}</li>"
                html += "</ul>"
            else:
                html += f"<p style='padding-left:5px;'>{valores}</p>"

        if df_datos is not None and not df_datos.empty:
            html += "<h2>Matriz de Distribución Coherente Basal</h2>"
            html += df_datos.to_html(index=False, classes='data-table')

        html += """
                <div class="footer">
                    <p>Reporte Técnico Generado de forma Atómica por el Módulo de Salida de Resultados.</p>
                </div>
            </div>
        </body>
        </html>
        """

        if nombre_archivo is None:
            return html

        nombre_seguro = slugify(nombre_archivo.replace('.html', '')) + '.html'
        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = f'attachment; filename="{nombre_seguro}"'
        return response

    @staticmethod
    def exportar_zip_completo(datos_dict, nombre_base=None):
        """Empaqueta los archivos generados en un archivo comprimido ZIP para descarga masiva."""
        import zipfile

        if nombre_base is None:
            nombre_base = f"paquete_analisis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for formato, datos in datos_dict.items():
                if formato == 'json':
                    json_str = json.dumps(datos, indent=2, default=str)
                    zf.writestr(f"{nombre_base}.json", json_str)
                elif formato == 'csv' and isinstance(datos, pd.DataFrame):
                    csv_str = datos.to_csv(index=False)
                    zf.writestr(f"{nombre_base}.csv", csv_str)
                elif formato == 'html':
                    zf.writestr(f"{nombre_base}.html", datos)

        buffer.seek(0)
        return buffer.getvalue()
