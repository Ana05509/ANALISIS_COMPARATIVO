# services/business/export_service.py
# Módulo de exportación avanzada (PDF, JSON, CSV, HTML) optimizado para consistencia de biodiversidad.

import json
import pandas as pd
from datetime import datetime
from io import BytesIO
from django.http import HttpResponse
from django.utils.text import slugify

import base64

from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table as XLTable, TableStyleInfo
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.chart.label import DataLabelList

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
    canvas.drawString(40, 20, "TerraBioLab UTC — Análisis Microbiológico de Suelos")
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


class ExportService:
    """Servicio de exportación avanzada a múltiples formatos con soporte biogeográfico."""

    # ------------------------------------------------------------------
    # Charts matplotlib
    # ------------------------------------------------------------------

    @staticmethod
    def _chart_donut_taxa(top_taxa, width_pt=250, height_pt=200,
                          titulo="Composición Taxonómica", subtitulo="Top 10 taxa por abundancia relativa (%)"):
        """Donut chart de top 10 taxa con título interno. Devuelve RLImage o None."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

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

            fig, ax = plt.subplots(figsize=(width_pt / 72, height_pt / 72))
            fig.patch.set_facecolor('#ffffff')

            wedges, _ = ax.pie(
                sizes, labels=None, colors=palette,
                startangle=90, counterclock=False,
                wedgeprops=dict(width=0.48, edgecolor='white', linewidth=0.8),
            )
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
            fig.savefig(buf, format='png', dpi=120, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return RLImage(buf, width=width_pt, height=height_pt)
        except Exception:
            return None

    @staticmethod
    def _chart_barras_clas(totales, width_pt=220, height_pt=130,
                           titulo="Categorías Funcionales", subtitulo="N.° de taxa por rol en el suelo"):
        """Barras horizontales de resumen funcional (4 categorías) con título interno."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            cats   = ["Benéfico", "Fitopatógeno", "Neutral", "Sin clas."]
            keys   = ["benefico", "fitopatogeno", "neutral", "sin_clasificar"]
            clrs   = ['#16a34a', '#dc2626', '#64748b', '#94a3b8']
            values = [totales.get(k, 0) for k in keys]

            fig, ax = plt.subplots(figsize=(width_pt / 72, height_pt / 72))
            fig.patch.set_facecolor('#ffffff')

            bars = ax.barh(cats, values, color=clrs, edgecolor='white', linewidth=0.6, height=0.55)
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
            fig.savefig(buf, format='png', dpi=120, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return RLImage(buf, width=width_pt, height=height_pt)
        except Exception:
            return None

    @staticmethod
    def _chart_ranked_bar_taxa(top_taxa, width_pt=440, height_pt=None,
                               titulo="Perfil de Abundancia Relativa",
                               subtitulo="Taxa ordenados de mayor a menor — color indica rol funcional"):
        """
        Barras horizontales rankeadas de top taxa, coloreadas por clasificación funcional.
        Forma estándar para perfiles de abundancia en microbiología de suelos.
        """
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from matplotlib.patches import Patch

            if not top_taxa:
                return None

            CLR_MAP = {
                'benefico':      '#16a34a',
                'fitopatogeno':  '#dc2626',
                'neutral':       '#64748b',
                'sin_clasificar':'#94a3b8',
            }

            # Ordenar: menor→mayor abundancia (el de mayor abundancia queda arriba en el eje Y)
            sorted_taxa = sorted(
                top_taxa,
                key=lambda r: float(r.get("total_porcentaje", r.get("porcentaje", 0)) or 0)
            )

            nombres = [str(r.get("taxonomia", r.get("nombre", "?"))) for r in sorted_taxa]
            valores = [float(r.get("total_porcentaje", r.get("porcentaje", 0)) or 0) for r in sorted_taxa]
            colores = [CLR_MAP.get(r.get("clasificacion", "sin_clasificar"), '#94a3b8') for r in sorted_taxa]

            n     = len(nombres)
            dyn_h = height_pt or min(max(n * 14 + 80, 140), 520)
            max_v = max(valores) if valores else 1

            fig, ax = plt.subplots(figsize=(width_pt / 72, dyn_h / 72))
            fig.patch.set_facecolor('#ffffff')

            bars = ax.barh(nombres, valores, color=colores, edgecolor='white', linewidth=0.5, height=0.70)

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
                Patch(facecolor='#16a34a', label='Benéfico'),
                Patch(facecolor='#dc2626', label='Fitopatógeno'),
                Patch(facecolor='#64748b', label='Neutral'),
                Patch(facecolor='#94a3b8', label='Sin catalogar'),
            ]
            ax.legend(handles=legend_elements, loc='lower right',
                      fontsize=6, framealpha=0.8, ncol=2,
                      edgecolor='#e2e8f0')

            plt.tight_layout(pad=0.5)
            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=130, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return RLImage(buf, width=width_pt, height=dyn_h)
        except Exception:
            return None

    @staticmethod
    def _chart_comparativo_shannon(datos_por_muestra, width_pt=460, height_pt=170):
        """
        Dos subplots: Shannon H' (colores por umbral absoluto) e Índice de Salud por muestra.
        Umbrales Shannon: <1 rojo · 1-2 naranja · 2-3 amarillo · ≥3 verde.
        """
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from matplotlib.patches import Patch

            if not datos_por_muestra:
                return None

            codigos  = [d["muestra"].codigo for d in datos_por_muestra]
            shannons = [float(d.get("diversidad", {}).get("shannon", 0) or 0) for d in datos_por_muestra]
            indices  = [d.get("indice_salud", 0) for d in datos_por_muestra]

            def _color_shannon(v):
                if v >= 3.0:  return '#16A34A'
                if v >= 2.0:  return '#EAB308'
                if v >= 1.0:  return '#F97316'
                return '#DC2626'

            def _color_indice(v):
                if v >= 80:  return '#14532d'
                if v >= 65:  return '#16a34a'
                if v >= 50:  return '#ca8a04'
                return '#dc2626'

            shan_colors = [_color_shannon(v) for v in shannons]
            bar_colors  = [_color_indice(v)  for v in indices]

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(width_pt / 72, height_pt / 72))
            fig.patch.set_facecolor('#ffffff')

            # ── Subplot izquierdo: Shannon H' ───────────────────────────
            ax1.bar(codigos, shannons, color=shan_colors, edgecolor='white', linewidth=0.6, width=0.55)
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
                Patch(facecolor='#16A34A', label='Alta (≥3)'),
                Patch(facecolor='#EAB308', label='Media-alta (2-3)'),
                Patch(facecolor='#F97316', label='Media-baja (1-2)'),
                Patch(facecolor='#DC2626', label='Baja (<1)'),
            ]
            ax1.legend(handles=shan_leg, fontsize=5, framealpha=0.8,
                       ncol=2, loc='upper left', edgecolor='#e2e8f0')

            # ── Subplot derecho: Índice de Salud ────────────────────────
            ax2.bar(codigos, indices, color=bar_colors, edgecolor='white', linewidth=0.6, width=0.55)
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
                Patch(facecolor='#14532d', label='Excelente (≥80)'),
                Patch(facecolor='#16a34a', label='Bueno (65-80)'),
                Patch(facecolor='#ca8a04', label='Moderado (50-65)'),
                Patch(facecolor='#dc2626', label='Crítico (<50)'),
            ]
            ax2.legend(handles=sal_leg, fontsize=5, framealpha=0.8,
                       ncol=2, loc='upper left', edgecolor='#e2e8f0')

            plt.tight_layout(pad=0.6)
            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=130, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return RLImage(buf, width=width_pt, height=height_pt)
        except Exception:
            return None

    @staticmethod
    def _chart_barras_agrupadas_funcional(datos_por_muestra, width_pt=460, height_pt=175,
                                          titulo="Composición Funcional Comparativa",
                                          subtitulo="N.° de taxa por categoría funcional en cada muestra"):
        """
        Barras agrupadas por clasificación funcional, una barra por muestra.
        Equivalente visual al modo multi-muestra del preview web.
        """
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import numpy as np

            if not datos_por_muestra:
                return None

            codigos = [d["muestra"].codigo for d in datos_por_muestra]
            cats    = ['benefico', 'fitopatogeno', 'neutral', 'sin_clasificar']
            labels  = ['Benéfico', 'Fitopatógeno', 'Neutral', 'Sin catalogar']
            clrs    = ['#16a34a', '#dc2626', '#64748b', '#94a3b8']

            x       = np.arange(len(codigos))
            n_c     = len(cats)
            w       = 0.18
            offsets = np.linspace(-(n_c - 1) * w / 2, (n_c - 1) * w / 2, n_c)

            fig, ax = plt.subplots(figsize=(width_pt / 72, height_pt / 72))
            fig.patch.set_facecolor('#ffffff')

            for cat, lbl, clr, off in zip(cats, labels, clrs, offsets):
                vals = [d.get("totales_clas", {}).get(cat, 0) for d in datos_por_muestra]
                if any(v > 0 for v in vals):
                    bars = ax.bar(x + off, vals, width=w, label=lbl,
                                  color=clr, edgecolor='white', linewidth=0.5)
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
            fig.savefig(buf, format='png', dpi=130, bbox_inches='tight')
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
                "<font size='16'><b>TerraBioLab UTC</b></font>",
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
            "Este reporte ha sido generado automáticamente por el sistema TerraBioLab UTC. "
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
            {"val": str(totales_clas.get("sin_clasificar", 0)),"lbl": "Sin catalogar", "color": "#94A3B8", "sub": "Taxa"},
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
        )
        if chart_ranked:
            contenido.append(chart_ranked)
            contenido.append(Paragraph(
                f"Figura 1. Top {top_n} {nivel} detectados en la muestra {cod_muestra} "
                f"(marcador {tipo}). Barras coloreadas por rol funcional: "
                "verde = benéfico · rojo = fitopatógeno · gris = neutral · gris claro = sin catalogar.",
                S["caption"],
            ))

        # ── Donut composición + barras funcionales (fila complementaria) ─
        chart_donut = ExportService._chart_donut_taxa(
            top_taxa, width_pt=200, height_pt=158,
            titulo="Composición Taxonómica",
            subtitulo=f"Top 10 {nivel} · muestra {cod_muestra}",
        )
        chart_clas  = ExportService._chart_barras_clas(
            totales_clas, width_pt=200, height_pt=128,
            titulo="Categorías Funcionales",
            subtitulo=f"N.° taxa por rol · muestra {cod_muestra}",
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
            {"val": str(totales_clas.get("sin_clasificar", 0)),"lbl": "Sin catalogar", "color": "#94A3B8", "sub": "No en catálogo"},
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
            f"Plataforma: TerraBioLab UTC — {fecha_gen}."
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
            "<i>Reporte técnico automatizado — TerraBioLab UTC. "
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
        diversidad        = datos.get("diversidad", {})
        totales_clas      = datos.get("totales_clas", {})
        tipo              = datos.get("tipo", "16S")
        nivel             = datos.get("nivel", "genus")
        usuario           = datos.get("usuario")

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
            "<font color='#ffffff'><b>TerraBioLab UTC</b></font>",
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
            comp_hdr.append([
                Paragraph(str(m.codigo),                   S["body_sm"]),
                Paragraph(str(d.get("indice_salud", 0)),   S["body_sm"]),
                Paragraph(str(d.get("nivel_salud", "N/A")),S["body_sm"]),
                Paragraph(str(len(d.get("top_taxa", []))), S["body_sm"]),
                Paragraph(f"{shan:.3f}",                   S["body_sm"]),
                Paragraph(str(tc.get("benefico", 0)),      S["body_sm"]),
                Paragraph(str(tc.get("fitopatogeno", 0)),  S["body_sm"]),
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
        chart_comp = ExportService._chart_comparativo_shannon(sorted_dpm, width_pt=ancho_util, height_pt=160)
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
        )
        if chart_ranked_g:
            contenido.append(chart_ranked_g)
            contenido.append(Paragraph(
                f"Figura 2. Abundancia relativa acumulada de los principales {nivel} en el conjunto comparativo ({len(muestras)} muestras, marcador {tipo}). "
                "Color: verde = benéfico · rojo = fitopatógeno · gris = neutral · gris claro = sin catalogar.",
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
            {"val": str(totales_clas.get("sin_clasificar", 0)),"lbl": "Sin catalogar", "color": "#94A3B8", "sub": "Global acumulado"},
        ], ancho_util, S))
        contenido.append(Spacer(1, 12))

        # Gráfica agrupada por muestra
        chart_agrupada = ExportService._chart_barras_agrupadas_funcional(
            datos_por_muestra, width_pt=ancho_util, height_pt=175,
            titulo="Composición Funcional Comparativa por Muestra",
            subtitulo=f"N.° de taxa por categoría funcional en cada muestra · Marcador {tipo} · Nivel {nivel}",
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
            Paragraph("<b>Sin catalogar</b>",  S["th_dark"]),
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
        riqueza_g    = diversidad.get("riqueza", len(top_taxa))
        nota_meto = (
            f"Análisis comparativo de <b>{len(muestras)}</b> muestras · Marcador: <b>{marcador_txt}</b> "
            f"· Nivel: <b>{nivel}</b>.<br/>"
            f"Taxa únicos detectados: <b>{riqueza_g}</b> · Shannon H' global: <b>{shannon_g:.3f}</b>.<br/><br/>"
            f"El Índice de Salud del Suelo integra la proporción benéfico/fitopatógeno (70%) y la diversidad "
            f"normalizada Shannon/3.5 (30%). Plataforma: TerraBioLab UTC — {fecha_gen}."
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
            "<i>Reporte técnico automatizado — TerraBioLab UTC. "
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
        is_comparativo   = len(muestras) > 1

        # ── Constantes de estilo ──────────────────────────────────────────
        CV        = "1D9E75"   # verde medio
        CV_OSC    = "0F6E56"   # verde oscuro (headers principales)
        CV_CLAR   = "E8F5EF"   # verde muy claro (secciones)
        CA        = "BA7517"   # ámbar
        CR        = "A32D2D"   # rojo
        CAZUL     = "185FA5"   # azul diversidad
        CGRIS     = "888888"   # gris neutro
        CGRIS_H   = "4A4A4A"   # gris oscuro headers neutros
        CBLANCO   = "FFFFFF"

        fill_hdr       = PatternFill("solid", fgColor=CV_OSC)
        fill_seccion   = PatternFill("solid", fgColor=CV_CLAR)
        fill_titulo    = PatternFill("solid", fgColor=CV)
        fill_azul      = PatternFill("solid", fgColor=CAZUL)
        fill_rojo      = PatternFill("solid", fgColor=CR)

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

        def _datos_filas(ws, min_row, max_row, alin=None):
            """Aplica estilo a filas de datos."""
            for row in ws.iter_rows(min_row=min_row, max_row=max_row):
                for cell in row:
                    cell.font   = fnt_normal
                    cell.border = borde
                    cell.alignment = alin or al_l

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

        def _chart_bars_h(ws, anchor, n_filas, col_datos, col_cats,
                          color_fill=None, titulo_celda=None, titulo_txt=""):
            """Gráfico barras horizontales."""
            if titulo_celda:
                _titulo_celda(ws, titulo_celda, titulo_txt)
            ch = BarChart()
            ch.type = "bar"; ch.grouping = "clustered"
            ch.title = None
            ch.y_axis.title = "Taxonomía"
            ch.x_axis.title = "Abundancia (%)"
            ch.style = 10; ch.width = 22
            ch.height = max(10, min(n_filas * 0.65, 18))
            dr = Reference(ws, min_col=col_datos, max_col=col_datos,
                           min_row=1, max_row=n_filas + 1)
            cr = Reference(ws, min_col=col_cats,  max_col=col_cats,
                           min_row=2, max_row=n_filas + 1)
            ch.add_data(dr, titles_from_data=True)
            ch.set_categories(cr)
            ch.series[0].graphicalProperties.solidFill = color_fill or CV
            ws.add_chart(ch, anchor)

        def _chart_bars_v(ws, anchor, data_ref, cats_ref,
                          color_fill=None, titulo_celda=None, titulo_txt="",
                          w=16, h=12):
            """Gráfico barras verticales."""
            if titulo_celda:
                _titulo_celda(ws, titulo_celda, titulo_txt)
            ch = BarChart()
            ch.type = "col"; ch.grouping = "clustered"
            ch.title = None; ch.y_axis.title = "Valor"
            ch.style = 2; ch.width = w; ch.height = h
            ch.add_data(data_ref, titles_from_data=True)
            ch.set_categories(cats_ref)
            ch.series[0].graphicalProperties.solidFill = color_fill or CV
            ws.add_chart(ch, anchor)

        def _pie_chart(ws, anchor, data_ref, cats_ref,
                       titulo_celda=None, titulo_txt="",
                       colores=None, w=18, h=14):
            """Gráfico pastel con etiquetas % y categoría."""
            if titulo_celda:
                _titulo_celda(ws, titulo_celda, titulo_txt)
            from openpyxl.chart.series import DataPoint
            pie = PieChart()
            pie.title = None; pie.style = 10
            pie.width = w; pie.height = h
            pie.add_data(data_ref, titles_from_data=True)
            pie.set_categories(cats_ref)
            palette = colores or [CV, CR, CA, "9E9E9E"]
            for i, color in enumerate(palette):
                dp = DataPoint(idx=i)
                dp.graphicalProperties.solidFill = color
                pie.series[0].dPt.append(dp)
            pie.dataLabels = DataLabelList()
            pie.dataLabels.showPercent = True
            pie.dataLabels.showCatName = True
            pie.dataLabels.showVal = False
            ws.add_chart(pie, anchor)

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
                    ["BioSuelo — Reporte Individual de Salud Microbiológica", "", ""],
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
                    ["Taxa Benéficos",
                     str(totales_clas.get("benefico", 0)),
                     f"{totales_clas.get('benefico',0)/total_clf*100:.1f}% del total catalogado"],
                    ["Taxa Fitopatógenos",
                     str(totales_clas.get("fitopatogeno", 0)),
                     f"{totales_clas.get('fitopatogeno',0)/total_clf*100:.1f}% del total catalogado"],
                    ["Taxa Neutrales",
                     str(totales_clas.get("neutral", 0)),
                     f"{totales_clas.get('neutral',0)/total_clf*100:.1f}% del total catalogado"],
                    ["Taxa Sin Catalogar",
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
                    elif v == "BioSuelo — Reporte Individual de Salud Microbiológica":
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
                _hdr(ws_top, len(df_top.columns))
                _datos_filas(ws_top, 2, len(df_top) + 1)
                _aplicar_tabla(ws_top, df_top, "TablaTopN")
                _ajustar_cols(ws_top, {"A": 6, "B": 42, "C": 14, "D": 16, "E": 20})
                _wrap(ws_top)

                if len(df_top) > 0:
                    _chart_bars_h(
                        ws_top, anchor="G3", n_filas=len(df_top),
                        col_datos=4, col_cats=2,
                        color_fill=CV,
                        titulo_celda="G2",
                        titulo_txt=f"Top {top_n} Taxa — Abundancia (%) · Marcador {tipo}",
                    )

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
                _hdr(ws_tod, len(df_tod.columns))
                _datos_filas(ws_tod, 2, len(df_tod) + 1)
                _aplicar_tabla(ws_tod, df_tod, "TablaTaxonomia", "TableStyleMedium9")
                _ajustar_cols(ws_tod, {"A": 6, "B": 42, "C": 14, "D": 16, "E": 20})
                _wrap(ws_tod)

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
                _hdr(ws_div, 4, fill=fill_azul)
                _datos_filas(ws_div, 2, 6)
                _aplicar_tabla(ws_div, df_div, "TablaDiversidad", "TableStyleMedium2")
                _ajustar_cols(ws_div, {"A": 22, "B": 14, "C": 20, "D": 65})
                _wrap(ws_div, h=28)

                # Gráfico 4 índices (sin N° muestras)
                _titulo_celda(ws_div, "F2", "Índices de Diversidad Alfa", CAZUL)
                ch_div = BarChart()
                ch_div.type = "col"; ch_div.grouping = "clustered"
                ch_div.title = None; ch_div.y_axis.title = "Valor"
                ch_div.style = 2; ch_div.width = 16; ch_div.height = 12
                dv_dat = Reference(ws_div, min_col=2, max_col=2, min_row=1, max_row=5)
                dv_cat = Reference(ws_div, min_col=1, max_col=1, min_row=2, max_row=5)
                ch_div.add_data(dv_dat, titles_from_data=True)
                ch_div.set_categories(dv_cat)
                ch_div.series[0].graphicalProperties.solidFill = CAZUL
                ws_div.add_chart(ch_div, "F3")

                # ─────────────────────────────────────────────────────
                # H-05  CLASIFICACIÓN FUNCIONAL
                # ─────────────────────────────────────────────────────
                total_det = max(total_catalogados + totales_clas.get("sin_clasificar", 0), 1)
                clf_rec = [
                    {"Categoría": "Benéficos",
                     "N°_Taxa": totales_clas.get("benefico", 0),
                     "%_Total": round(totales_clas.get("benefico",0)/total_det*100, 2),
                     "Descripción_del_Rol":
                         "Promueven el crecimiento vegetal, fijan nitrógeno, solubilizan fósforo "
                         "o antagonizan patógenos"},
                    {"Categoría": "Fitopatógenos",
                     "N°_Taxa": totales_clas.get("fitopatogeno", 0),
                     "%_Total": round(totales_clas.get("fitopatogeno",0)/total_det*100, 2),
                     "Descripción_del_Rol":
                         "Causan o pueden causar enfermedades en el cultivo. "
                         "Su presencia en alta abundancia es señal de alerta fitosanitaria"},
                    {"Categoría": "Neutrales",
                     "N°_Taxa": totales_clas.get("neutral", 0),
                     "%_Total": round(totales_clas.get("neutral",0)/total_det*100, 2),
                     "Descripción_del_Rol":
                         "Sin función agronómica conocida o con efecto dependiente del contexto"},
                    {"Categoría": "Sin catalogar",
                     "N°_Taxa": totales_clas.get("sin_clasificar", 0),
                     "%_Total": round(totales_clas.get("sin_clasificar",0)/total_det*100, 2),
                     "Descripción_del_Rol":
                         "No presentes en el catálogo funcional del sistema"},
                ]
                df_clf = pd.DataFrame(clf_rec)
                _excel_safe_df(df_clf).to_excel(writer, index=False, sheet_name="Clasificacion_Funcional")
                ws_clf = writer.sheets["Clasificacion_Funcional"]
                _hdr(ws_clf, 4, fill=PatternFill("solid", fgColor=CA),
                     font=Font(bold=True, color=CBLANCO, size=11))
                _datos_filas(ws_clf, 2, 5)
                _aplicar_tabla(ws_clf, df_clf, "TablaClasificacion", "TableStyleMedium4")
                _ajustar_cols(ws_clf, {"A": 20, "B": 10, "C": 12, "D": 70})
                _wrap(ws_clf, h=40)

                # Pastel funcional
                _pie_chart(
                    ws_clf, anchor="F2",
                    data_ref=Reference(ws_clf, min_col=2, max_col=2, min_row=1, max_row=5),
                    cats_ref=Reference(ws_clf, min_col=1, max_col=1, min_row=2, max_row=5),
                    titulo_celda="F1",
                    titulo_txt="Distribución Funcional de Taxa",
                    colores=[CV, CR, CA, "9E9E9E"],
                )

                # ─────────────────────────────────────────────────────
                # H-06  BENÉFICOS
                # ─────────────────────────────────────────────────────
                beneficos = detalle_clas.get("benefico", [])
                ben_rec = [{
                    "#": i + 1,
                    "Organismo":          b.get("nombre", ""),
                    "Abundancia_%":       round(float(b.get("porcentaje", 0) or 0), 4),
                    "Función_Agronómica": b.get("descripcion", ""),
                    "Referencia":         b.get("referencia", ""),
                } for i, b in enumerate(beneficos)]
                df_ben = (pd.DataFrame(ben_rec) if ben_rec
                          else pd.DataFrame(columns=["#","Organismo","Abundancia_%",
                                                     "Función_Agronómica","Referencia"]))
                _excel_safe_df(df_ben).to_excel(writer, index=False, sheet_name="Beneficos")
                ws_ben = writer.sheets["Beneficos"]
                _hdr(ws_ben, 5, fill=PatternFill("solid", fgColor="0F6E56"))
                _datos_filas(ws_ben, 2, len(df_ben) + 1)
                _aplicar_tabla(ws_ben, df_ben, "TablaBeneficos", "TableStyleMedium7")
                _ajustar_cols(ws_ben, {"A": 5, "B": 38, "C": 16, "D": 62, "E": 45})
                _wrap(ws_ben, h=38)

                # ─────────────────────────────────────────────────────
                # H-07  FITOPATÓGENOS
                # ─────────────────────────────────────────────────────
                fitopatogenos = detalle_clas.get("fitopatogeno", [])
                fito_rec = [{
                    "#": i + 1,
                    "Organismo":            f.get("nombre", ""),
                    "Abundancia_%":         round(float(f.get("porcentaje", 0) or 0), 4),
                    "Riesgo_Fitosanitario": f.get("descripcion", ""),
                    "Referencia":           f.get("referencia", ""),
                } for i, f in enumerate(fitopatogenos)]
                df_fito = (pd.DataFrame(fito_rec) if fito_rec
                           else pd.DataFrame(columns=["#","Organismo","Abundancia_%",
                                                      "Riesgo_Fitosanitario","Referencia"]))
                _excel_safe_df(df_fito).to_excel(writer, index=False, sheet_name="Fitopatogenos")
                ws_fito = writer.sheets["Fitopatogenos"]
                _hdr(ws_fito, 5, fill=fill_rojo)
                _datos_filas(ws_fito, 2, len(df_fito) + 1)
                _aplicar_tabla(ws_fito, df_fito, "TablaFitopatogenos", "TableStyleMedium3")
                _ajustar_cols(ws_fito, {"A": 5, "B": 38, "C": 16, "D": 62, "E": 45})
                _wrap(ws_fito, h=38)

                # ─────────────────────────────────────────────────────
                # H-08  NEUTRALES
                # ─────────────────────────────────────────────────────
                neutrales = detalle_clas.get("neutral", [])
                neu_rec = [{
                    "#": i + 1,
                    "Organismo":    n.get("nombre", ""),
                    "Abundancia_%": round(float(n.get("porcentaje", 0) or 0), 4),
                    "Notas":        n.get("descripcion", "") or "Sin clasificación funcional definida",
                } for i, n in enumerate(neutrales)]
                df_neu = (pd.DataFrame(neu_rec) if neu_rec
                          else pd.DataFrame(columns=["#","Organismo","Abundancia_%","Notas"]))
                _excel_safe_df(df_neu).to_excel(writer, index=False, sheet_name="Neutrales")
                ws_neu = writer.sheets["Neutrales"]
                _hdr(ws_neu, 4, fill=PatternFill("solid", fgColor=CGRIS_H))
                _datos_filas(ws_neu, 2, len(df_neu) + 1)
                _aplicar_tabla(ws_neu, df_neu, "TablaNeutrales", "TableStyleMedium15")
                _ajustar_cols(ws_neu, {"A": 5, "B": 38, "C": 16, "D": 50})
                _wrap(ws_neu, h=30)

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
                    _hdr(ws_dif, 6, fill=fill_azul)
                    _datos_filas(ws_dif, 2, len(df_dif) + 1)
                    _aplicar_tabla(ws_dif, df_dif, "TablaDiferencial", "TableStyleMedium2")
                    _ajustar_cols(ws_dif, {"A": 5, "B": 38, "C": 22,
                                           "D": 20, "E": 18, "F": 22})
                    _wrap(ws_dif, h=28)

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

                # ─────────────────────────────────────────────────────
                # H-10  GRÁFICOS
                # ─────────────────────────────────────────────────────
                ws_g = wb.create_sheet("Graficos")
                ws_g.cell(row=1, column=1,
                          value="Gráficos — BioSuelo").font = fnt_titulo
                ws_g.cell(row=1, column=1).fill = fill_titulo

                # Mini tabla clasificación
                ws_g.append(["", ""])
                ws_g.append(["Clasificación", "N° Taxa"])
                for cod, lbl in [("benefico","Benéficos"),("fitopatogeno","Fitopatógenos"),
                                  ("neutral","Neutrales"),("sin_clasificar","Sin catalogar")]:
                    ws_g.append([lbl, totales_clas.get(cod, 0)])
                for cell in ws_g[3]:
                    cell.fill = fill_hdr; cell.font = fnt_hdr; cell.alignment = al_c
                for row in ws_g.iter_rows(min_row=4, max_row=7):
                    for cell in row:
                        cell.font = fnt_normal; cell.border = borde

                _ajustar_cols(ws_g, {"A": 22, "B": 14})
                _pie_chart(
                    ws_g, anchor="D2",
                    data_ref=Reference(ws_g, min_col=2, max_col=2, min_row=3, max_row=7),
                    cats_ref=Reference(ws_g, min_col=1, max_col=1, min_row=4, max_row=7),
                    titulo_celda="D1",
                    titulo_txt="Distribución Funcional de la Comunidad Microbiana",
                )
                ws_g.cell(row=20, column=1,
                          value="Generado por BioSuelo").font = fnt_gris

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
                    ["BioSuelo — Reporte Comparativo de Salud Microbiológica", "", ""],
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
                    ["Taxa Benéficos",    str(totales_clas.get("benefico", 0)), ""],
                    ["Taxa Fitopatógenos",str(totales_clas.get("fitopatogeno", 0)), ""],
                    ["Taxa Neutrales",    str(totales_clas.get("neutral", 0)), ""],
                    ["Taxa Sin Catalogar",str(totales_clas.get("sin_clasificar", 0)), ""],
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
                    elif v.startswith("BioSuelo"):
                        for cell in row:
                            cell.fill = fill_titulo
                            cell.font = Font(bold=True, color=CBLANCO, size=12)
                            cell.border = borde
                    elif v:
                        for cell in row:
                            cell.font = fnt_normal; cell.border = borde; cell.alignment = al_l
                _ajustar_cols(ws_rc, {"A": 34, "B": 25, "C": 65})
                _wrap(ws_rc, h=28)

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
                        "Sin_Catalogar":    tc.get("sin_clasificar", 0),
                    })
                df_cuad = (pd.DataFrame(cuad_rec) if cuad_rec
                           else pd.DataFrame(columns=["Muestra","Cultivo","Variedad",
                               "Localidad","Índice_Salud","Nivel","Riqueza",
                               "Shannon_H'","Simpson_D","Equitatividad_J'",
                               "Benéficos","Fitopatógenos","Neutrales","Sin_Catalogar"]))
                _excel_safe_df(df_cuad).to_excel(writer, index=False, sheet_name="Cuadro_Comparativo")
                ws_cuad = writer.sheets["Cuadro_Comparativo"]
                _hdr(ws_cuad, len(df_cuad.columns))
                _datos_filas(ws_cuad, 2, len(df_cuad) + 1, alin=al_c)
                _aplicar_tabla(ws_cuad, df_cuad, "TablaCuadroComp", "TableStyleMedium9")
                _ajustar_cols(ws_cuad, {
                    "A": 16, "B": 20, "C": 20, "D": 18,
                    "E": 14, "F": 14, "G": 12, "H": 14,
                    "I": 12, "J": 18, "K": 12, "L": 14, "M": 12, "N": 14,
                })
                _wrap(ws_cuad, h=26)

                # Gráfico: Índice de salud por muestra
                if len(df_cuad) > 0:
                    _titulo_celda(ws_cuad, "P2", "Índice de Salud por Muestra", CV_OSC)
                    ch_sal = BarChart()
                    ch_sal.type = "col"; ch_sal.grouping = "clustered"
                    ch_sal.title = None; ch_sal.y_axis.title = "Índice (0-100)"
                    ch_sal.style = 10; ch_sal.width = 18; ch_sal.height = 12
                    ch_sal.y_axis.scaling.max = 100
                    dat_s = Reference(ws_cuad, min_col=5, max_col=5,
                                      min_row=1, max_row=len(df_cuad)+1)
                    cat_s = Reference(ws_cuad, min_col=1, max_col=1,
                                      min_row=2, max_row=len(df_cuad)+1)
                    ch_sal.add_data(dat_s, titles_from_data=True)
                    ch_sal.set_categories(cat_s)
                    ch_sal.series[0].graphicalProperties.solidFill = CV
                    ws_cuad.add_chart(ch_sal, "P3")

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
                _hdr(ws_alfa, 6, fill=fill_azul)
                _datos_filas(ws_alfa, 2, len(df_alfa) + 1, alin=al_c)
                # Fila promedio en negrita
                if alfa_rec:
                    for c in range(1, 7):
                        ws_alfa.cell(row=len(df_alfa) + 1, column=c).font = fnt_bold
                _aplicar_tabla(ws_alfa, df_alfa, "TablaDivAlfa", "TableStyleMedium2")
                _ajustar_cols(ws_alfa, {"A": 18, "B": 12, "C": 14, "D": 22, "E": 12, "F": 18})
                _wrap(ws_alfa, h=24)

                # Gráfico Shannon por muestra — colores por umbral absoluto
                # (<1 rojo, 1-2 naranja, 2-3 amarillo, ≥3 verde)
                from openpyxl.chart.series import DataPoint as XLDataPoint
                n_data = len(alfa_rec) - 1 if alfa_rec else 0  # excluye fila PROMEDIO
                if n_data > 0:
                    _titulo_celda(ws_alfa, "H2", "Shannon H' por Muestra (colores por umbral)", CAZUL)
                    ch_sh = BarChart()
                    ch_sh.type = "col"; ch_sh.grouping = "clustered"
                    ch_sh.title = None; ch_sh.y_axis.title = "Shannon H'"
                    ch_sh.style = 10; ch_sh.width = 20; ch_sh.height = 14
                    sh_dat = Reference(ws_alfa, min_col=3, max_col=3,
                                       min_row=1, max_row=n_data + 1)
                    sh_cat = Reference(ws_alfa, min_col=1, max_col=1,
                                       min_row=2, max_row=n_data + 1)
                    ch_sh.add_data(sh_dat, titles_from_data=True)
                    ch_sh.set_categories(sh_cat)
                    # Color por umbral Shannon en cada barra (<1 rojo, 1-2 naranja, 2-3 amarillo, ≥3 verde)
                    for idx, row_data in enumerate(alfa_rec[:n_data]):
                        sv = float(row_data.get("Shannon_H'", 0) or 0)
                        if sv >= 3.0:   fill_c = "16A34A"
                        elif sv >= 2.0: fill_c = "EAB308"
                        elif sv >= 1.0: fill_c = "F97316"
                        else:           fill_c = "DC2626"
                        dp = XLDataPoint(idx=idx)
                        dp.graphicalProperties.solidFill = fill_c
                        ch_sh.series[0].dPt.append(dp)
                    ws_alfa.add_chart(ch_sh, "H3")

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
                _hdr(ws_top, len(df_top.columns))
                _datos_filas(ws_top, 2, len(df_top) + 1)
                _aplicar_tabla(ws_top, df_top, "TablaTopNGlobal")
                _ajustar_cols(ws_top, {"A": 6, "B": 42, "C": 14, "D": 16, "E": 20})
                _wrap(ws_top)
                if len(df_top) > 0:
                    _chart_bars_h(
                        ws_top, anchor="G3", n_filas=len(df_top),
                        col_datos=4, col_cats=2, color_fill=CV,
                        titulo_celda="G2",
                        titulo_txt=f"Top {top_n} Taxa Global — Abundancia (%) · {tipo}",
                    )

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
                _hdr(ws_tod, len(df_tod.columns))
                _datos_filas(ws_tod, 2, len(df_tod) + 1)
                _aplicar_tabla(ws_tod, df_tod, "TablaTaxonomia", "TableStyleMedium9")
                _ajustar_cols(ws_tod, {"A": 6, "B": 42, "C": 14, "D": 16, "E": 20})
                _wrap(ws_tod)

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
                        "Sin_Catalogar":   tc.get("sin_clasificar", 0),
                        "Total_Taxa":      tot,
                        "%_Benéficos":     round(tc.get("benefico",0)/tot*100, 2),
                        "%_Fitopatógenos": round(tc.get("fitopatogeno",0)/tot*100, 2),
                    })
                df_cls = (pd.DataFrame(cls_rec) if cls_rec
                          else pd.DataFrame(columns=[
                              "Muestra","Benéficos","Fitopatógenos","Neutrales",
                              "Sin_Catalogar","Total_Taxa","%_Benéficos","%_Fitopatógenos"]))
                _excel_safe_df(df_cls).to_excel(writer, index=False, sheet_name="Clas_Por_Muestra")
                ws_cls = writer.sheets["Clas_Por_Muestra"]
                _hdr(ws_cls, len(df_cls.columns),
                     fill=PatternFill("solid", fgColor=CA),
                     font=Font(bold=True, color=CBLANCO, size=11))
                _datos_filas(ws_cls, 2, len(df_cls) + 1, alin=al_c)
                _aplicar_tabla(ws_cls, df_cls, "TablaClsPorMuestra", "TableStyleMedium4")
                _ajustar_cols(ws_cls, {
                    "A": 18, "B": 13, "C": 15, "D": 13,
                    "E": 15, "F": 13, "G": 16, "H": 18,
                })
                _wrap(ws_cls, h=24)

                # ─────────────────────────────────────────────────────
                # H-08  BENÉFICOS (global)
                # ─────────────────────────────────────────────────────
                beneficos = detalle_clas.get("benefico", [])
                ben_rec = [{
                    "#": i + 1,
                    "Organismo":          b.get("nombre", ""),
                    "Abundancia_%":       round(float(b.get("porcentaje", 0) or 0), 4),
                    "Función_Agronómica": b.get("descripcion", ""),
                    "Referencia":         b.get("referencia", ""),
                } for i, b in enumerate(beneficos)]
                df_ben = (pd.DataFrame(ben_rec) if ben_rec
                          else pd.DataFrame(columns=["#","Organismo","Abundancia_%",
                                                     "Función_Agronómica","Referencia"]))
                _excel_safe_df(df_ben).to_excel(writer, index=False, sheet_name="Beneficos")
                ws_ben = writer.sheets["Beneficos"]
                _hdr(ws_ben, 5, fill=PatternFill("solid", fgColor="0F6E56"))
                _datos_filas(ws_ben, 2, len(df_ben) + 1)
                _aplicar_tabla(ws_ben, df_ben, "TablaBeneficos", "TableStyleMedium7")
                _ajustar_cols(ws_ben, {"A": 5, "B": 38, "C": 16, "D": 62, "E": 45})
                _wrap(ws_ben, h=38)

                # ─────────────────────────────────────────────────────
                # H-09  FITOPATÓGENOS (global)
                # ─────────────────────────────────────────────────────
                fitopatogenos = detalle_clas.get("fitopatogeno", [])
                fito_rec = [{
                    "#": i + 1,
                    "Organismo":            f.get("nombre", ""),
                    "Abundancia_%":         round(float(f.get("porcentaje", 0) or 0), 4),
                    "Riesgo_Fitosanitario": f.get("descripcion", ""),
                    "Referencia":           f.get("referencia", ""),
                } for i, f in enumerate(fitopatogenos)]
                df_fito = (pd.DataFrame(fito_rec) if fito_rec
                           else pd.DataFrame(columns=["#","Organismo","Abundancia_%",
                                                      "Riesgo_Fitosanitario","Referencia"]))
                _excel_safe_df(df_fito).to_excel(writer, index=False, sheet_name="Fitopatogenos")
                ws_fito = writer.sheets["Fitopatogenos"]
                _hdr(ws_fito, 5, fill=fill_rojo)
                _datos_filas(ws_fito, 2, len(df_fito) + 1)
                _aplicar_tabla(ws_fito, df_fito, "TablaFitopatogenos", "TableStyleMedium3")
                _ajustar_cols(ws_fito, {"A": 5, "B": 38, "C": 16, "D": 62, "E": 45})
                _wrap(ws_fito, h=38)

                # ─────────────────────────────────────────────────────
                # H-10  NEUTRALES (global)
                # ─────────────────────────────────────────────────────
                neutrales = detalle_clas.get("neutral", [])
                neu_rec = [{
                    "#": i + 1,
                    "Organismo":    n.get("nombre", ""),
                    "Abundancia_%": round(float(n.get("porcentaje", 0) or 0), 4),
                    "Notas":        n.get("descripcion", "") or "Sin clasificación funcional definida",
                } for i, n in enumerate(neutrales)]
                df_neu = (pd.DataFrame(neu_rec) if neu_rec
                          else pd.DataFrame(columns=["#","Organismo","Abundancia_%","Notas"]))
                _excel_safe_df(df_neu).to_excel(writer, index=False, sheet_name="Neutrales")
                ws_neu = writer.sheets["Neutrales"]
                _hdr(ws_neu, 4, fill=PatternFill("solid", fgColor=CGRIS_H))
                _datos_filas(ws_neu, 2, len(df_neu) + 1)
                _aplicar_tabla(ws_neu, df_neu, "TablaNeutrales", "TableStyleMedium15")
                _ajustar_cols(ws_neu, {"A": 5, "B": 38, "C": 16, "D": 50})
                _wrap(ws_neu, h=30)

                # ─────────────────────────────────────────────────────
                # H-11  GRÁFICOS COMPARATIVOS
                # ─────────────────────────────────────────────────────
                ws_g = wb.create_sheet("Graficos")
                ws_g.cell(row=1, column=1,
                          value="Gráficos — BioSuelo").font = fnt_titulo
                ws_g.cell(row=1, column=1).fill = fill_titulo
                ws_g.row_dimensions[1].height = 22

                # Mini tabla clasificación global
                ws_g.append(["", ""])
                ws_g.append(["Clasificación", "N° Taxa"])
                for cod, lbl in [("benefico","Benéficos"),("fitopatogeno","Fitopatógenos"),
                                  ("neutral","Neutrales"),("sin_clasificar","Sin catalogar")]:
                    ws_g.append([lbl, totales_clas.get(cod, 0)])
                for cell in ws_g[3]:
                    cell.fill = fill_hdr; cell.font = fnt_hdr; cell.alignment = al_c
                for row in ws_g.iter_rows(min_row=4, max_row=7):
                    for cell in row:
                        cell.font = fnt_normal; cell.border = borde
                _ajustar_cols(ws_g, {"A": 22, "B": 14})

                # Pastel global
                _pie_chart(
                    ws_g, anchor="D2",
                    data_ref=Reference(ws_g, min_col=2, max_col=2, min_row=3, max_row=7),
                    cats_ref=Reference(ws_g, min_col=1, max_col=1, min_row=4, max_row=7),
                    titulo_celda="D1",
                    titulo_txt="Distribución Funcional Global de la Comunidad Microbiana",
                )

                # Mini tabla Índice de salud por muestra (para gráfico)
                ws_g.cell(row=22, column=1, value="Muestra").font = fnt_hdr
                ws_g.cell(row=22, column=1).fill = fill_hdr
                ws_g.cell(row=22, column=1).alignment = al_c
                ws_g.cell(row=22, column=2, value="Índice de Salud").font = fnt_hdr
                ws_g.cell(row=22, column=2).fill = fill_hdr
                ws_g.cell(row=22, column=2).alignment = al_c
                fila_sal = 23
                for dpm in datos_por_muestra:
                    ws_g.cell(row=fila_sal, column=1,
                              value=str(dpm["muestra"].codigo)).font = fnt_normal
                    ws_g.cell(row=fila_sal, column=2,
                              value=dpm.get("indice_salud", 0)).font = fnt_normal
                    for c in range(1, 3):
                        ws_g.cell(row=fila_sal, column=c).border = borde
                    fila_sal += 1

                n_sal = len(datos_por_muestra)
                if n_sal > 0:
                    _titulo_celda(ws_g, "D21", "Índice de Salud por Muestra", CV_OSC)
                    ch_s2 = BarChart()
                    ch_s2.type = "col"; ch_s2.grouping = "clustered"
                    ch_s2.title = None; ch_s2.y_axis.title = "Índice (0-100)"
                    ch_s2.style = 10; ch_s2.width = 18; ch_s2.height = 12
                    ch_s2.y_axis.scaling.max = 100
                    ds2 = Reference(ws_g, min_col=2, max_col=2,
                                    min_row=22, max_row=22 + n_sal)
                    cs2 = Reference(ws_g, min_col=1, max_col=1,
                                    min_row=23, max_row=22 + n_sal)
                    ch_s2.add_data(ds2, titles_from_data=True)
                    ch_s2.set_categories(cs2)
                    ch_s2.series[0].graphicalProperties.solidFill = CV
                    ws_g.add_chart(ch_s2, "D22")

                ws_g.cell(row=40, column=1,
                          value="Generado por BioSuelo").font = fnt_gris

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
