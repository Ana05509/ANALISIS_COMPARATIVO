# services/business/export_service.py
# Módulo de exportación avanzada (PDF, JSON, CSV, HTML) optimizado para consistencia de biodiversidad.

import json
import pandas as pd
from datetime import datetime
from io import BytesIO
from django.http import HttpResponse
from django.utils.text import slugify

import base64

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, PageBreak, HRFlowable,
)
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


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
    style_titulo = ParagraphStyle(
        'ScientificTitle', parent=styles['Heading1'], fontSize=20, leading=24,
        textColor=_C_PRIMARY, spaceAfter=15, alignment=TA_LEFT, fontName='Helvetica-Bold',
    )
    style_h2 = ParagraphStyle(
        'ScientificH2', parent=styles['Heading2'], fontSize=13, leading=17,
        textColor=_C_SECONDARY, spaceBefore=14, spaceAfter=7, fontName='Helvetica-Bold',
    )
    style_h3 = ParagraphStyle(
        'ScientificH3', parent=styles['Heading3'], fontSize=11, leading=14,
        textColor=_C_PRIMARY, spaceBefore=10, spaceAfter=4, fontName='Helvetica-Bold',
    )
    style_body = ParagraphStyle(
        'ScientificBody', parent=styles['Normal'], fontSize=9.5, leading=13,
        textColor=colors.HexColor('#212529'),
    )
    style_body_sm = ParagraphStyle(
        'ScientificBodySm', parent=styles['Normal'], fontSize=8.5, leading=11.5,
        textColor=colors.HexColor('#374151'),
    )
    style_th = ParagraphStyle(
        'TableTh', parent=styles['Normal'], fontSize=9, leading=11,
        textColor=colors.white, fontName='Helvetica-Bold',
    )
    style_center = ParagraphStyle(
        'CenteredBody', parent=styles['Normal'], fontSize=9.5, leading=13,
        textColor=colors.HexColor('#212529'), alignment=TA_CENTER,
    )
    style_italic = ParagraphStyle(
        'ItalicBody', parent=styles['Normal'], fontSize=8.5, leading=12,
        textColor=colors.HexColor('#64748b'), fontName='Helvetica-Oblique',
    )
    return {
        "titulo": style_titulo,
        "h2": style_h2,
        "h3": style_h3,
        "body": style_body,
        "body_sm": style_body_sm,
        "th": style_th,
        "center": style_center,
        "italic": style_italic,
    }


def _pdf_footer(canvas, doc):
    """Footer con número de página para todos los PDF del sistema."""
    canvas.saveState()
    canvas.setFont('Helvetica', 7.5)
    canvas.setFillColor(colors.HexColor('#94a3b8'))
    canvas.drawString(40, 18, "TerraBioLab UTC — Universidad Técnica de Cotopaxi")
    canvas.drawRightString(A4[0] - 40, 18, f"Página {canvas.getPageNumber()}")
    canvas.restoreState()


def _nivel_color_rl(nivel_salud: str):
    hex_color = _NIVEL_COLORES.get(nivel_salud, "#64748b")
    return colors.HexColor(hex_color)


class ExportService:
    """Servicio de exportación avanzada a múltiples formatos con soporte biogeográfico."""

    # ------------------------------------------------------------------
    # Charts matplotlib
    # ------------------------------------------------------------------

    @staticmethod
    def _chart_donut_taxa(top_taxa, width_pt=250, height_pt=200):
        """Genera donut chart de top 10 taxa. Devuelve RLImage o None."""
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
            plt.tight_layout(pad=0.3)

            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=120, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return RLImage(buf, width=width_pt, height=height_pt)
        except Exception:
            return None

    @staticmethod
    def _chart_barras_clas(totales, width_pt=220, height_pt=130):
        """Gráfica de barras horizontales para clasificación funcional."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            cats   = ["Benéfico", "Fitopatógeno", "Neutral", "Sin clas."]
            keys   = ["benefico", "fitopatogeno", "neutral", "sin_clasificar"]
            clrs   = ['#16a34a', '#dc2626', '#64748b', '#94a3b8']
            values = [totales.get(k, 0) for k in keys]

            fig, ax = plt.subplots(figsize=(width_pt / 72, height_pt / 72))
            bars = ax.barh(cats, values, color=clrs, edgecolor='white', linewidth=0.6)
            ax.bar_label(bars, padding=3, fontsize=7, color='#374151')
            ax.set_xlabel("N.° de taxones", fontsize=7)
            ax.tick_params(axis='y', labelsize=7)
            ax.tick_params(axis='x', labelsize=6)
            ax.spines[['top', 'right']].set_visible(False)
            plt.tight_layout(pad=0.3)

            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=120, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return RLImage(buf, width=width_pt, height=height_pt)
        except Exception:
            return None

    @staticmethod
    def _chart_comparativo_shannon(datos_por_muestra, width_pt=460, height_pt=160):
        """Dos subplots: Shannon H' y Índice de Salud por muestra."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            if not datos_por_muestra:
                return None

            codigos  = [d["muestra"].codigo for d in datos_por_muestra]
            shannons = [float(d.get("diversidad", {}).get("shannon", 0) or 0) for d in datos_por_muestra]
            indices  = [d.get("indice_salud", 0) for d in datos_por_muestra]

            def color_indice(v):
                if v >= 80:   return '#14532d'
                if v >= 65:   return '#16a34a'
                if v >= 50:   return '#ca8a04'
                return '#dc2626'

            bar_colors = [color_indice(v) for v in indices]

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(width_pt / 72, height_pt / 72))

            ax1.bar(codigos, shannons, color='#185FA5', edgecolor='white', linewidth=0.6)
            ax1.set_title("Shannon H'", fontsize=8, fontweight='bold')
            ax1.set_ylabel("H'", fontsize=7)
            ax1.tick_params(axis='x', labelsize=6, rotation=30)
            ax1.tick_params(axis='y', labelsize=6)
            ax1.spines[['top', 'right']].set_visible(False)

            ax2.bar(codigos, indices, color=bar_colors, edgecolor='white', linewidth=0.6)
            ax2.set_title("Índice de Salud", fontsize=8, fontweight='bold')
            ax2.set_ylabel("Índice (0-100)", fontsize=7)
            ax2.set_ylim(0, 100)
            ax2.tick_params(axis='x', labelsize=6, rotation=30)
            ax2.tick_params(axis='y', labelsize=6)
            ax2.spines[['top', 'right']].set_visible(False)

            plt.tight_layout(pad=0.5)
            buf = BytesIO()
            fig.savefig(buf, format='png', dpi=120, bbox_inches='tight')
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

        # ----------------------------------------------------------------
        # Página 1 — Portada
        # ----------------------------------------------------------------
        # Header block
        header_data = [[
            Paragraph(
                "<font color='#ffffff'><b>TerraBioLab UTC</b><br/>"
                "<font size='9'>Universidad Técnica de Cotopaxi — Laboratorio de Bioinformática de Suelos</font></font>",
                S["body"],
            )
        ]]
        t_header = Table(header_data, colWidths=[ancho_util])
        t_header.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), _C_PRIMARY),
            ('TOPPADDING', (0, 0), (-1, -1), 14),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
            ('LEFTPADDING', (0, 0), (-1, -1), 16),
            ('RIGHTPADDING', (0, 0), (-1, -1), 16),
            ('ROUNDEDCORNERS', [4, 4, 4, 4]),
        ]))
        contenido.append(t_header)
        contenido.append(Spacer(1, 18))

        contenido.append(Paragraph("REPORTE DE SALUD MICROBIOLÓGICA DEL SUELO", S["titulo"]))
        contenido.append(Paragraph(f"Marcador: <b>{marcador_lbl}</b>", S["body"]))
        contenido.append(Spacer(1, 14))

        # Tabla info muestra (2x4)
        info_rows = [
            ["Código", _safe(muestra, "codigo"), "Cultivo", cultivo_nom],
            ["Variedad/Clon", var_nom, "Tipo de Muestra", _safe(muestra, "tipo_muestra")],
            ["Localidad", _safe(muestra, "localidad"), "Finca/Lote", _safe(muestra, "finca_lote")],
            ["Altitud (msnm)", _safe(muestra, "altitud", "N/A"), "Fecha de Registro", _safe(muestra, "fecha_registro")],
        ]
        col_w = [ancho_util / 4] * 4
        t_info = Table(
            [[Paragraph(f"<b>{r[0]}</b>", S["body_sm"]), Paragraph(r[1], S["body_sm"]),
              Paragraph(f"<b>{r[2]}</b>", S["body_sm"]), Paragraph(r[3], S["body_sm"])]
             for r in info_rows],
            colWidths=col_w,
        )
        t_info.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), _C_LIGHT),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, _C_INNER),
            ('BOX', (0, 0), (-1, -1), 1, _C_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_info)
        contenido.append(Spacer(1, 10))

        gen_rows = [
            [Paragraph("<b>Fecha de generación:</b>", S["body_sm"]), Paragraph(fecha_gen, S["body_sm"]),
             Paragraph("<b>Analista:</b>", S["body_sm"]), Paragraph(analista, S["body_sm"])],
            [Paragraph("<b>Nivel taxonómico:</b>", S["body_sm"]), Paragraph(nivel.capitalize(), S["body_sm"]),
             Paragraph("<b>Top N:</b>", S["body_sm"]), Paragraph(str(top_n), S["body_sm"])],
        ]
        t_gen = Table(gen_rows, colWidths=col_w)
        t_gen.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), _C_LIGHT),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, _C_INNER),
            ('BOX', (0, 0), (-1, -1), 1, _C_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        contenido.append(t_gen)

        contenido.append(PageBreak())

        # ----------------------------------------------------------------
        # Página 2 — Resumen Ejecutivo
        # ----------------------------------------------------------------
        contenido.append(Paragraph("Resumen Ejecutivo", S["h2"]))
        contenido.append(HRFlowable(width=ancho_util, thickness=1, color=_C_SECONDARY))
        contenido.append(Spacer(1, 12))

        # Bloque índice de salud
        nivel_color_hex = _NIVEL_COLORES.get(nivel_salud, "#64748b")
        nivel_color_rl  = colors.HexColor(nivel_color_hex)

        # Barra de progreso visible (fill + empty)
        _barra_util = ancho_util - 20   # margen interno
        _fill_w  = max(_barra_util * (indice_salud / 100), 1.0)
        _empty_w = max(_barra_util - _fill_w, 1.0)
        t_bar = Table([["", ""]], colWidths=[_fill_w, _empty_w])
        t_bar.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), nivel_color_rl),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#e2e8f0')),
            ('LEFTPADDING',   (0, 0), (-1, -1), 0),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
            ('TOPPADDING',    (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('ROWHEIGHT', (0, 0), (-1, -1), 14),
        ]))

        salud_style = ParagraphStyle(
            'SaludNum', parent=S["body"], fontSize=34, fontName='Helvetica-Bold',
            textColor=nivel_color_rl, alignment=TA_CENTER,
        )
        salud_lbl_style = ParagraphStyle(
            'SaludLbl', parent=S["body"], fontSize=10, fontName='Helvetica-Bold',
            textColor=nivel_color_rl,
        )
        salud_sub_style = ParagraphStyle(
            'SaludSub', parent=S["body_sm"], textColor=colors.HexColor('#64748b'),
        )
        barra_data = [[
            Paragraph(str(indice_salud), salud_style),
            Table(
                [[Paragraph(f"<b>{nivel_salud}</b>", salud_lbl_style)],
                 [Paragraph("Índice de Salud del Suelo (0 – 100)", salud_sub_style)],
                 [t_bar]],
                colWidths=[ancho_util * 0.65],
            ),
        ]]
        t_salud = Table(barra_data, colWidths=[ancho_util * 0.18, ancho_util * 0.82])
        t_salud.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('BOX', (0, 0), (-1, -1), 2, nivel_color_rl),
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#f0faf4')),
            ('BACKGROUND', (1, 0), (1, 0), colors.white),
        ]))
        contenido.append(t_salud)
        contenido.append(Spacer(1, 12))

        # Métricas diversidad + clasificación
        shannon_v = diversidad.get("shannon", 0.0) or 0.0
        simpson_v = diversidad.get("simpson", 0.0) or 0.0
        equit_v   = diversidad.get("equitatividad", 0.0) or 0.0
        riqueza_v = diversidad.get("riqueza", len(todos_taxa))

        metr_rows = [
            [Paragraph("<b>Métrica</b>", S["th"]), Paragraph("<b>Valor</b>", S["th"]),
             Paragraph("<b>Métrica</b>", S["th"]), Paragraph("<b>Valor</b>", S["th"])],
            [Paragraph("Taxa Totales", S["body_sm"]), Paragraph(str(riqueza_v), S["body_sm"]),
             Paragraph("Benéficos", S["body_sm"]), Paragraph(str(totales_clas.get("benefico", 0)), S["body_sm"])],
            [Paragraph("Shannon H'", S["body_sm"]), Paragraph(f"{shannon_v:.4f}", S["body_sm"]),
             Paragraph("Fitopatógenos", S["body_sm"]), Paragraph(str(totales_clas.get("fitopatogeno", 0)), S["body_sm"])],
            [Paragraph("Simpson D", S["body_sm"]), Paragraph(f"{simpson_v:.4f}", S["body_sm"]),
             Paragraph("Neutrales", S["body_sm"]), Paragraph(str(totales_clas.get("neutral", 0)), S["body_sm"])],
            [Paragraph("Equitatividad", S["body_sm"]), Paragraph(f"{equit_v:.4f}", S["body_sm"]),
             Paragraph("Sin Catalogar", S["body_sm"]), Paragraph(str(totales_clas.get("sin_clasificar", 0)), S["body_sm"])],
        ]
        col_w2 = [ancho_util * 0.28, ancho_util * 0.22, ancho_util * 0.28, ancho_util * 0.22]
        t_metr = Table(metr_rows, colWidths=col_w2)
        t_metr.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), _C_SECONDARY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _C_LIGHT]),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, _C_INNER),
            ('BOX', (0, 0), (-1, -1), 1, _C_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_metr)
        contenido.append(Spacer(1, 12))

        # Conclusión auto-generada
        cod_muestra = _safe(muestra, "codigo", "la muestra seleccionada")
        conclusion = (
            f"La muestra <b>{cod_muestra}</b> del cultivo <b>{cultivo_nom}</b> presenta un "
            f"Índice de Salud del Suelo de <b>{indice_salud}/100</b> ({nivel_salud}). "
            f"El análisis con marcador <b>{marcador_lbl}</b> a nivel <b>{nivel}</b> detectó "
            f"<b>{riqueza_v}</b> taxa únicos con una diversidad Shannon H'= <b>{shannon_v:.3f}</b>. "
            f"La comunidad microbiana incluye <b>{totales_clas.get('benefico', 0)}</b> taxa benéficos "
            f"y <b>{totales_clas.get('fitopatogeno', 0)}</b> fitopatógenos potenciales."
        )
        contenido.append(Paragraph(conclusion, S["body"]))

        contenido.append(PageBreak())

        # ----------------------------------------------------------------
        # Página 3 — Perfil Taxonómico
        # ----------------------------------------------------------------
        contenido.append(Paragraph("Perfil Taxonómico", S["h2"]))
        contenido.append(HRFlowable(width=ancho_util, thickness=1, color=_C_SECONDARY))
        contenido.append(Spacer(1, 10))

        chart_donut = ExportService._chart_donut_taxa(top_taxa, width_pt=220, height_pt=180)
        chart_clas  = ExportService._chart_barras_clas(totales_clas, width_pt=200, height_pt=150)

        if chart_donut or chart_clas:
            chart_cells = [
                chart_donut if chart_donut else Paragraph("(Sin datos suficientes)", S["body_sm"]),
                chart_clas  if chart_clas  else Paragraph("", S["body_sm"]),
            ]
            t_charts = Table([chart_cells], colWidths=[ancho_util * 0.52, ancho_util * 0.48])
            t_charts.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            contenido.append(t_charts)
            contenido.append(Spacer(1, 10))

        # Tabla top taxa
        def _clas_badge(clas):
            if clas == 'benefico':      return Paragraph("<font color='#16a34a'>&#9679; Benéfico</font>", S["body_sm"])
            if clas == 'fitopatogeno':  return Paragraph("<font color='#dc2626'>&#9679; Fitopatógeno</font>", S["body_sm"])
            if clas == 'neutral':       return Paragraph("<font color='#64748b'>&#9675; Neutral</font>", S["body_sm"])
            return Paragraph("<font color='#94a3b8'>· Sin clas.</font>", S["body_sm"])

        taxa_rows = [[
            Paragraph("<b>#</b>", S["th"]),
            Paragraph("<b>Taxón</b>", S["th"]),
            Paragraph("<b>Hits</b>", S["th"]),
            Paragraph("<b>Abundancia %</b>", S["th"]),
            Paragraph("<b>Clasificación</b>", S["th"]),
        ]]
        for i, r in enumerate(top_taxa, 1):
            taxa_rows.append([
                Paragraph(str(i), S["body_sm"]),
                Paragraph(str(r.get("taxonomia", r.get("nombre", "?"))), S["body_sm"]),
                Paragraph(str(r.get("total_hits", r.get("hits", 0))), S["body_sm"]),
                Paragraph(f"{r.get('total_porcentaje', r.get('porcentaje', 0)):.2f}%", S["body_sm"]),
                _clas_badge(r.get("clasificacion", "sin_clasificar")),
            ])

        col_taxa = [30, ancho_util * 0.38, 60, 80, 100]
        t_taxa = Table(taxa_rows, colWidths=col_taxa, repeatRows=1)
        t_taxa.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), _C_SECONDARY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _C_LIGHT]),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, _C_INNER),
            ('BOX', (0, 0), (-1, -1), 1, _C_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_taxa)

        contenido.append(PageBreak())

        # ----------------------------------------------------------------
        # Página 4 — Diversidad Alfa
        # ----------------------------------------------------------------
        contenido.append(Paragraph("Diversidad Alfa", S["h2"]))
        contenido.append(HRFlowable(width=ancho_util, thickness=1, color=_C_SECONDARY))
        contenido.append(Spacer(1, 10))

        # bar_total: ancho disponible dentro de la celda exterior (colWidth - L/R padding)
        _bar_total = max(ancho_util * 0.30 - 14, 10.0)

        def _interp_bar(valor, max_val, color_hex):
            """Barra de progreso sin padding interior para evitar ancho negativo."""
            pct = min(max(float(valor or 0), 0.0) / max(float(max_val or 1), 1e-9), 1.0)
            fill_w = max(_bar_total * pct, 1.0)
            rest_w = max(_bar_total * (1.0 - pct), 1.0)
            t = Table([["", ""]], colWidths=[fill_w, rest_w])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, 0), colors.HexColor(color_hex)),
                ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#e2e8f0')),
                ('LEFTPADDING',   (0, 0), (-1, -1), 0),
                ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
                ('TOPPADDING',    (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ('ROWHEIGHT', (0, 0), (-1, -1), 9),
            ]))
            return t

        div_rows = [
            [Paragraph("<b>Métrica</b>", S["th"]), Paragraph("<b>Valor</b>", S["th"]),
             Paragraph("<b>Barra</b>", S["th"]), Paragraph("<b>Interpretación</b>", S["th"])],
            [
                Paragraph("Riqueza de especies", S["body_sm"]),
                Paragraph(str(riqueza_v), S["body_sm"]),
                _interp_bar(riqueza_v, max(riqueza_v, 1), '#185FA5'),
                Paragraph(
                    "Alta" if riqueza_v > 100 else ("Moderada" if riqueza_v > 30 else "Baja"),
                    S["body_sm"],
                ),
            ],
            [
                Paragraph("Shannon H'", S["body_sm"]),
                Paragraph(f"{shannon_v:.4f}", S["body_sm"]),
                _interp_bar(shannon_v, 5.0, '#1D9E75'),
                Paragraph(
                    "Alta diversidad" if shannon_v > 3 else ("Moderada" if shannon_v > 1.5 else "Baja diversidad"),
                    S["body_sm"],
                ),
            ],
            [
                Paragraph("Simpson D", S["body_sm"]),
                Paragraph(f"{simpson_v:.4f}", S["body_sm"]),
                _interp_bar(simpson_v, 1.0, '#BA7517'),
                Paragraph(
                    "Buena equidad" if simpson_v > 0.7 else ("Moderada" if simpson_v > 0.4 else "Dominancia marcada"),
                    S["body_sm"],
                ),
            ],
            [
                Paragraph("Equitatividad (J')", S["body_sm"]),
                Paragraph(f"{equit_v:.4f}", S["body_sm"]),
                _interp_bar(equit_v, 1.0, '#6B4E9E'),
                Paragraph(
                    "Comunidad equilibrada" if equit_v > 0.7 else ("Distribución media" if equit_v > 0.4 else "Dominancia fuerte"),
                    S["body_sm"],
                ),
            ],
        ]
        col_div = [ancho_util * 0.28, 60, ancho_util * 0.30, ancho_util * 0.28]
        t_div = Table(div_rows, colWidths=col_div, repeatRows=1)
        t_div.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), _C_SECONDARY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _C_LIGHT]),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, _C_INNER),
            ('BOX', (0, 0), (-1, -1), 1, _C_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_div)
        contenido.append(Spacer(1, 12))

        if shannon_v > 3:
            div_concl = "La comunidad microbiana presenta alta diversidad alfa, lo que indica un ecosistema de suelo equilibrado y resiliente."
        elif shannon_v > 1.5:
            div_concl = "Se observa diversidad alfa moderada. La comunidad microbiana es funcional aunque puede beneficiarse de prácticas de mejora del suelo."
        else:
            div_concl = "La diversidad alfa es baja, sugiriendo posible dominancia de pocos taxa o condiciones de estrés edáfico."
        contenido.append(Paragraph(div_concl, S["body"]))

        contenido.append(PageBreak())

        # ----------------------------------------------------------------
        # Página 5 — Perfil Funcional
        # ----------------------------------------------------------------
        contenido.append(Paragraph("Perfil Funcional de la Comunidad Microbiana", S["h2"]))
        contenido.append(HRFlowable(width=ancho_util, thickness=1, color=_C_SECONDARY))
        contenido.append(Spacer(1, 10))

        # Resumen de 4 números grandes
        summ_data = [[
            Paragraph(f"<font color='#16a34a'><b>{totales_clas.get('benefico', 0)}</b><br/><font size='8'>Benéficos</font></font>", S["center"]),
            Paragraph(f"<font color='#dc2626'><b>{totales_clas.get('fitopatogeno', 0)}</b><br/><font size='8'>Fitopatógenos</font></font>", S["center"]),
            Paragraph(f"<font color='#64748b'><b>{totales_clas.get('neutral', 0)}</b><br/><font size='8'>Neutrales</font></font>", S["center"]),
            Paragraph(f"<font color='#94a3b8'><b>{totales_clas.get('sin_clasificar', 0)}</b><br/><font size='8'>Sin Catalogar</font></font>", S["center"]),
        ]]
        t_summ = Table(summ_data, colWidths=[ancho_util / 4] * 4)
        t_summ.setStyle(TableStyle([
            ('INNERGRID', (0, 0), (-1, -1), 0.5, _C_INNER),
            ('BOX', (0, 0), (-1, -1), 1, _C_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_summ)
        contenido.append(Spacer(1, 12))

        # Tabla organismos benéficos (hasta 20)
        beneficos = detalle_clas.get("benefico", [])[:20]
        if beneficos:
            contenido.append(Paragraph("Organismos Benéficos", S["h3"]))
            ben_rows = [[
                Paragraph("<b>Taxón</b>", S["th"]),
                Paragraph("<b>Abundancia %</b>", S["th"]),
                Paragraph("<b>Rol Agronómico</b>", S["th"]),
                Paragraph("<b>Referencia</b>", S["th"]),
            ]]
            for item in beneficos:
                ben_rows.append([
                    Paragraph(str(item.get("nombre", "")), S["body_sm"]),
                    Paragraph(f"{item.get('porcentaje', 0):.2f}%", S["body_sm"]),
                    Paragraph(str(item.get("descripcion", ""))[:120], S["body_sm"]),
                    Paragraph(str(item.get("referencia", ""))[:80], S["body_sm"]),
                ])
            col_ben = [ancho_util * 0.28, 70, ancho_util * 0.35, ancho_util * 0.22]
            t_ben = Table(ben_rows, colWidths=col_ben, repeatRows=1)
            t_ben.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), _C_BEN),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0fdf4')]),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, _C_INNER),
                ('BOX', (0, 0), (-1, -1), 1, _C_BORDER),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            contenido.append(t_ben)
            contenido.append(Spacer(1, 10))

        # Tabla fitopatógenos (hasta 15)
        fitopatogenos = detalle_clas.get("fitopatogeno", [])[:15]
        if fitopatogenos:
            contenido.append(Paragraph("Fitopatógenos Potenciales", S["h3"]))
            fito_rows = [[
                Paragraph("<b>Taxón</b>", S["th"]),
                Paragraph("<b>Abundancia %</b>", S["th"]),
                Paragraph("<b>Riesgo</b>", S["th"]),
                Paragraph("<b>Referencia</b>", S["th"]),
            ]]
            for item in fitopatogenos:
                fito_rows.append([
                    Paragraph(str(item.get("nombre", "")), S["body_sm"]),
                    Paragraph(f"{item.get('porcentaje', 0):.2f}%", S["body_sm"]),
                    Paragraph(str(item.get("descripcion", ""))[:120], S["body_sm"]),
                    Paragraph(str(item.get("referencia", ""))[:80], S["body_sm"]),
                ])
            col_fito = [ancho_util * 0.28, 70, ancho_util * 0.35, ancho_util * 0.22]
            t_fito = Table(fito_rows, colWidths=col_fito, repeatRows=1)
            t_fito.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), _C_FITO),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fff1f2')]),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, _C_INNER),
                ('BOX', (0, 0), (-1, -1), 1, _C_BORDER),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            contenido.append(t_fito)
            contenido.append(Spacer(1, 10))

        # Neutrales (lista hasta 30)
        neutrales = detalle_clas.get("neutral", [])[:30]
        if neutrales:
            contenido.append(Paragraph("Organismos Neutrales", S["h3"]))
            noms = ", ".join(str(n.get("nombre", "?")) for n in neutrales)
            contenido.append(Paragraph(noms, S["body_sm"]))

        contenido.append(PageBreak())

        # ----------------------------------------------------------------
        # Página 6 — Trazabilidad
        # ----------------------------------------------------------------
        contenido.append(Paragraph("Trazabilidad y Nota Metodológica", S["h2"]))
        contenido.append(HRFlowable(width=ancho_util, thickness=1, color=_C_SECONDARY))
        contenido.append(Spacer(1, 10))

        obs = _safe(muestra, "observaciones", "")
        if obs and obs != "N/A":
            contenido.append(Paragraph("<b>Observaciones de la muestra:</b>", S["body"]))
            contenido.append(Paragraph(obs, S["body_sm"]))
            contenido.append(Spacer(1, 8))

        marcador_txt = "16S rRNA" if tipo == "16S" else "ITS (Internal Transcribed Spacer)"
        nota_meto = (
            f"El presente análisis utiliza el marcador molecular <b>{marcador_txt}</b> a nivel taxonómico de "
            f"<b>{nivel}</b>. Se detectaron <b>{len(todos_taxa)}</b> taxa únicos mediante el pipeline bioinformático "
            f"de TerraBioLab UTC. La diversidad alfa fue calculada usando los índices de Shannon-Wiener (H') y "
            f"Simpson (D). El Índice de Salud del Suelo integra la proporción funcional de la comunidad (70%) y "
            f"la diversidad normalizada Shannon/3.5 (30%). La cobertura del catálogo funcional corresponde a "
            f"<b>{totales_clas.get('benefico', 0) + totales_clas.get('fitopatogeno', 0) + totales_clas.get('neutral', 0)}</b> "
            f"taxa catalogados de un total de <b>{len(todos_taxa)}</b> detectados. "
            f"Plataforma: TerraBioLab UTC — {fecha_gen}."
        )
        contenido.append(Paragraph(nota_meto, S["body"]))
        contenido.append(Spacer(1, 14))

        contenido.append(Paragraph(
            "<i>Este documento es un reporte técnico automatizado generado por TerraBioLab UTC. "
            "Los resultados deben ser interpretados por un profesional calificado en microbiología de suelos. "
            "Universidad Técnica de Cotopaxi — Laboratorio de Bioinformática de Suelos.</i>",
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
        indice_salud      = datos.get("indice_salud", 0)
        nivel_salud       = datos.get("nivel_salud", "MODERADO")
        tipo              = datos.get("tipo", "16S")
        nivel             = datos.get("nivel", "genus")
        top_n             = datos.get("top_n", 25)
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

        # ----------------------------------------------------------------
        # Página 1 — Portada comparativa
        # ----------------------------------------------------------------
        header_data = [[
            Paragraph(
                "<font color='#ffffff'><b>TerraBioLab UTC</b><br/>"
                "<font size='9'>Universidad Técnica de Cotopaxi — Laboratorio de Bioinformática de Suelos</font></font>",
                S["body"],
            )
        ]]
        t_header = Table(header_data, colWidths=[ancho_util])
        t_header.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), _C_PRIMARY),
            ('TOPPADDING', (0, 0), (-1, -1), 14),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
            ('LEFTPADDING', (0, 0), (-1, -1), 16),
        ]))
        contenido.append(t_header)
        contenido.append(Spacer(1, 18))

        contenido.append(Paragraph("ANÁLISIS COMPARATIVO DE PERFILES MICROBIOLÓGICOS", S["titulo"]))
        contenido.append(Paragraph(f"Marcador: <b>{marcador_lbl}</b> — {len(muestras)} muestras", S["body"]))
        contenido.append(Spacer(1, 12))

        # Tabla de muestras incluidas
        muestras_hdr = [[
            Paragraph("<b>Código</b>", S["th"]),
            Paragraph("<b>Cultivo</b>", S["th"]),
            Paragraph("<b>Variedad</b>", S["th"]),
            Paragraph("<b>Localidad</b>", S["th"]),
            Paragraph("<b>Finca</b>", S["th"]),
            Paragraph("<b>Altitud</b>", S["th"]),
        ]]
        for m in muestras:
            cult = m.cultivo.nombre if getattr(m, 'cultivo', None) else "N/A"
            var  = m.variedad_clon.nombre if getattr(m, 'variedad_clon', None) else "N/A"
            muestras_hdr.append([
                Paragraph(str(m.codigo), S["body_sm"]),
                Paragraph(cult, S["body_sm"]),
                Paragraph(var, S["body_sm"]),
                Paragraph(str(getattr(m, 'localidad', 'N/A') or 'N/A'), S["body_sm"]),
                Paragraph(str(getattr(m, 'finca_lote', 'N/A') or 'N/A'), S["body_sm"]),
                Paragraph(str(getattr(m, 'altitud', 'N/A') or 'N/A'), S["body_sm"]),
            ])
        col_m = [80, 80, 80, ancho_util * 0.22, ancho_util * 0.18, 55]
        t_muestras = Table(muestras_hdr, colWidths=col_m, repeatRows=1)
        t_muestras.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), _C_SECONDARY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _C_LIGHT]),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, _C_INNER),
            ('BOX', (0, 0), (-1, -1), 1, _C_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_muestras)
        contenido.append(Spacer(1, 10))

        gen_rows = [[
            Paragraph("<b>Fecha:</b>", S["body_sm"]), Paragraph(fecha_gen, S["body_sm"]),
            Paragraph("<b>Analista:</b>", S["body_sm"]), Paragraph(analista, S["body_sm"]),
            Paragraph("<b>Nivel:</b>", S["body_sm"]), Paragraph(nivel.capitalize(), S["body_sm"]),
        ]]
        col_gen = [60, 100, 60, 100, 50, 80]
        t_gen = Table(gen_rows, colWidths=col_gen)
        t_gen.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), _C_LIGHT),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, _C_INNER),
            ('BOX', (0, 0), (-1, -1), 1, _C_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ]))
        contenido.append(t_gen)

        contenido.append(PageBreak())

        # ----------------------------------------------------------------
        # Página 2 — Cuadro comparativo
        # ----------------------------------------------------------------
        contenido.append(Paragraph("Cuadro Comparativo de Salud del Suelo", S["h2"]))
        contenido.append(HRFlowable(width=ancho_util, thickness=1, color=_C_SECONDARY))
        contenido.append(Spacer(1, 10))

        # Ordenar por indice_salud desc
        sorted_dpm = sorted(datos_por_muestra, key=lambda x: x.get("indice_salud", 0), reverse=True)

        comp_hdr = [[
            Paragraph("<b>Muestra</b>", S["th"]),
            Paragraph("<b>Índice Salud</b>", S["th"]),
            Paragraph("<b>Nivel</b>", S["th"]),
            Paragraph("<b>Taxa</b>", S["th"]),
            Paragraph("<b>Shannon</b>", S["th"]),
            Paragraph("<b>Benéficos</b>", S["th"]),
            Paragraph("<b>Fitopatógenos</b>", S["th"]),
        ]]
        for d in sorted_dpm:
            m = d["muestra"]
            tc = d.get("totales_clas", {})
            shan = float(d.get("diversidad", {}).get("shannon", 0) or 0)
            n_taxa = len(d.get("top_taxa", []))
            col_nivel = colors.HexColor(_NIVEL_COLORES.get(d.get("nivel_salud", "MODERADO"), "#64748b"))
            comp_hdr.append([
                Paragraph(str(m.codigo), S["body_sm"]),
                Paragraph(str(d.get("indice_salud", 0)), S["body_sm"]),
                Paragraph(str(d.get("nivel_salud", "N/A")), S["body_sm"]),
                Paragraph(str(n_taxa), S["body_sm"]),
                Paragraph(f"{shan:.3f}", S["body_sm"]),
                Paragraph(str(tc.get("benefico", 0)), S["body_sm"]),
                Paragraph(str(tc.get("fitopatogeno", 0)), S["body_sm"]),
            ])
        col_comp = [80, 70, 75, 50, 65, 65, 70]
        t_comp = Table(comp_hdr, colWidths=col_comp, repeatRows=1)
        t_comp.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), _C_SECONDARY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _C_LIGHT]),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, _C_INNER),
            ('BOX', (0, 0), (-1, -1), 1, _C_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_comp)
        contenido.append(Spacer(1, 14))

        # Gráfica comparativa Shannon + Salud
        chart_comp = ExportService._chart_comparativo_shannon(sorted_dpm, width_pt=ancho_util, height_pt=160)
        if chart_comp:
            contenido.append(chart_comp)

        contenido.append(PageBreak())

        # ----------------------------------------------------------------
        # Página 3 — Composición global (Top N)
        # ----------------------------------------------------------------
        contenido.append(Paragraph("Composición Global por Muestra", S["h2"]))
        contenido.append(HRFlowable(width=ancho_util, thickness=1, color=_C_SECONDARY))
        contenido.append(Spacer(1, 10))

        # Tabla top taxa global
        g_rows = [[
            Paragraph("<b>#</b>", S["th"]),
            Paragraph("<b>Taxón</b>", S["th"]),
            Paragraph("<b>Total Hits</b>", S["th"]),
            Paragraph("<b>Abundancia %</b>", S["th"]),
            Paragraph("<b>Clasificación</b>", S["th"]),
        ]]
        for i, r in enumerate(top_taxa, 1):
            clas = r.get("clasificacion", "sin_clasificar")
            if clas == "benefico":     clas_txt = "Benéfico"
            elif clas == "fitopatogeno": clas_txt = "Fitopatógeno"
            elif clas == "neutral":    clas_txt = "Neutral"
            else:                      clas_txt = "Sin clas."
            g_rows.append([
                Paragraph(str(i), S["body_sm"]),
                Paragraph(str(r.get("taxonomia", "?")), S["body_sm"]),
                Paragraph(str(r.get("total_hits", 0)), S["body_sm"]),
                Paragraph(f"{r.get('total_porcentaje', 0):.2f}%", S["body_sm"]),
                Paragraph(clas_txt, S["body_sm"]),
            ])
        col_g = [30, ancho_util * 0.42, 70, 80, 90]
        t_g = Table(g_rows, colWidths=col_g, repeatRows=1)
        t_g.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), _C_SECONDARY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _C_LIGHT]),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, _C_INNER),
            ('BOX', (0, 0), (-1, -1), 1, _C_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_g)
        contenido.append(Spacer(1, 10))

        # Donut global
        chart_donut_g = ExportService._chart_donut_taxa(top_taxa, width_pt=220, height_pt=180)
        if chart_donut_g:
            contenido.append(chart_donut_g)

        contenido.append(PageBreak())

        # ----------------------------------------------------------------
        # Página 4 — Perfil funcional comparativo
        # ----------------------------------------------------------------
        contenido.append(Paragraph("Perfil Funcional Comparativo", S["h2"]))
        contenido.append(HRFlowable(width=ancho_util, thickness=1, color=_C_SECONDARY))
        contenido.append(Spacer(1, 10))

        # Resumen global de clasificación
        summ_g = [[
            Paragraph(f"<font color='#16a34a'><b>{totales_clas.get('benefico', 0)}</b><br/><font size='8'>Benéficos</font></font>", S["center"]),
            Paragraph(f"<font color='#dc2626'><b>{totales_clas.get('fitopatogeno', 0)}</b><br/><font size='8'>Fitopatógenos</font></font>", S["center"]),
            Paragraph(f"<font color='#64748b'><b>{totales_clas.get('neutral', 0)}</b><br/><font size='8'>Neutrales</font></font>", S["center"]),
            Paragraph(f"<font color='#94a3b8'><b>{totales_clas.get('sin_clasificar', 0)}</b><br/><font size='8'>Sin Catalogar</font></font>", S["center"]),
        ]]
        t_summ_g = Table(summ_g, colWidths=[ancho_util / 4] * 4)
        t_summ_g.setStyle(TableStyle([
            ('INNERGRID', (0, 0), (-1, -1), 0.5, _C_INNER),
            ('BOX', (0, 0), (-1, -1), 1, _C_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_summ_g)
        contenido.append(Spacer(1, 10))

        # Gráfica barras global
        chart_clas_g = ExportService._chart_barras_clas(totales_clas, width_pt=220, height_pt=130)
        if chart_clas_g:
            contenido.append(chart_clas_g)
        contenido.append(Spacer(1, 10))

        # Tabla por muestra: Muestra | Benéficos | Fitopatógenos | Neutrales | Sin catalogar
        por_m_hdr = [[
            Paragraph("<b>Muestra</b>", S["th"]),
            Paragraph("<b>Benéficos</b>", S["th"]),
            Paragraph("<b>Fitopatógenos</b>", S["th"]),
            Paragraph("<b>Neutrales</b>", S["th"]),
            Paragraph("<b>Sin catalogar</b>", S["th"]),
        ]]
        for d in datos_por_muestra:
            tc = d.get("totales_clas", {})
            por_m_hdr.append([
                Paragraph(str(d["muestra"].codigo), S["body_sm"]),
                Paragraph(str(tc.get("benefico", 0)), S["body_sm"]),
                Paragraph(str(tc.get("fitopatogeno", 0)), S["body_sm"]),
                Paragraph(str(tc.get("neutral", 0)), S["body_sm"]),
                Paragraph(str(tc.get("sin_clasificar", 0)), S["body_sm"]),
            ])
        col_pm = [ancho_util * 0.30, 80, 90, 80, 80]
        t_pm = Table(por_m_hdr, colWidths=col_pm, repeatRows=1)
        t_pm.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), _C_SECONDARY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _C_LIGHT]),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, _C_INNER),
            ('BOX', (0, 0), (-1, -1), 1, _C_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_pm)

        contenido.append(PageBreak())

        # ----------------------------------------------------------------
        # Página 5 — Trazabilidad
        # ----------------------------------------------------------------
        contenido.append(Paragraph("Trazabilidad y Nota Metodológica", S["h2"]))
        contenido.append(HRFlowable(width=ancho_util, thickness=1, color=_C_SECONDARY))
        contenido.append(Spacer(1, 10))

        # Tabla metadata de muestras
        meta_hdr = [[
            Paragraph("<b>Código</b>", S["th"]),
            Paragraph("<b>Cultivo</b>", S["th"]),
            Paragraph("<b>Variedad</b>", S["th"]),
            Paragraph("<b>Localidad</b>", S["th"]),
            Paragraph("<b>Finca/Lote</b>", S["th"]),
            Paragraph("<b>Altitud</b>", S["th"]),
            Paragraph("<b>Fecha</b>", S["th"]),
        ]]
        for m in muestras:
            cult = m.cultivo.nombre if getattr(m, 'cultivo', None) else "N/A"
            var  = m.variedad_clon.nombre if getattr(m, 'variedad_clon', None) else "N/A"
            meta_hdr.append([
                Paragraph(str(m.codigo), S["body_sm"]),
                Paragraph(cult, S["body_sm"]),
                Paragraph(var, S["body_sm"]),
                Paragraph(str(getattr(m, 'localidad', 'N/A') or 'N/A'), S["body_sm"]),
                Paragraph(str(getattr(m, 'finca_lote', 'N/A') or 'N/A'), S["body_sm"]),
                Paragraph(str(getattr(m, 'altitud', 'N/A') or 'N/A'), S["body_sm"]),
                Paragraph(str(getattr(m, 'fecha_registro', 'N/A') or 'N/A'), S["body_sm"]),
            ])
        col_meta = [65, 65, 65, ancho_util * 0.18, ancho_util * 0.15, 45, 60]
        t_meta = Table(meta_hdr, colWidths=col_meta, repeatRows=1)
        t_meta.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), _C_SECONDARY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _C_LIGHT]),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, _C_INNER),
            ('BOX', (0, 0), (-1, -1), 1, _C_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        contenido.append(t_meta)
        contenido.append(Spacer(1, 12))

        marcador_txt = "16S rRNA" if tipo == "16S" else "ITS (Internal Transcribed Spacer)"
        shannon_g = float(diversidad.get("shannon", 0) or 0)
        riqueza_g = diversidad.get("riqueza", len(top_taxa))
        nota_meto = (
            f"Análisis comparativo de <b>{len(muestras)}</b> muestras con marcador <b>{marcador_txt}</b> "
            f"a nivel <b>{nivel}</b>. Se detectaron en total <b>{riqueza_g}</b> taxa únicos. "
            f"Shannon H' global: <b>{shannon_g:.3f}</b>. "
            f"El Índice de Salud del Suelo integra la proporción funcional (70%) y diversidad Shannon/3.5 (30%). "
            f"Plataforma: TerraBioLab UTC — {fecha_gen}."
        )
        contenido.append(Paragraph(nota_meto, S["body"]))
        contenido.append(Spacer(1, 14))
        contenido.append(Paragraph(
            "<i>Reporte técnico automatizado — TerraBioLab UTC. "
            "Interpretación a cargo de profesionales en microbiología de suelos.</i>",
            S["italic"],
        ))

        doc.build(contenido, onFirstPage=_pdf_footer, onLaterPages=_pdf_footer)
        buffer.seek(0)
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # Excel multi-hoja
    # ------------------------------------------------------------------

    @staticmethod
    def generar_excel_multisheet(datos) -> HttpResponse:
        """
        Genera Excel con múltiples hojas temáticas.
        datos keys: muestra, muestras, top_taxa, todos_taxa, diversidad,
                    detalle_clas, totales_clas, indice_salud, nivel_salud,
                    tipo, nivel, top_n, usuario
        """
        muestra      = datos.get("muestra")
        muestras     = datos.get("muestras", [])
        top_taxa     = datos.get("top_taxa", [])
        todos_taxa   = datos.get("todos_taxa", [])
        diversidad   = datos.get("diversidad", {})
        detalle_clas = datos.get("detalle_clas", {})
        totales_clas = datos.get("totales_clas", {})
        indice_salud = datos.get("indice_salud", 0)
        nivel_salud  = datos.get("nivel_salud", "N/A")
        tipo         = datos.get("tipo", "16S")
        nivel        = datos.get("nivel", "genus")
        top_n        = datos.get("top_n", 25)
        usuario      = datos.get("usuario")

        buffer = BytesIO()

        def _safe(obj, attr, default="N/A"):
            val = getattr(obj, attr, None) if obj else None
            return str(val) if val not in (None, "") else default

        cultivo_nom = (muestra.cultivo.nombre if muestra and getattr(muestra, 'cultivo', None) else "N/A")
        var_nom     = (muestra.variedad_clon.nombre if muestra and getattr(muestra, 'variedad_clon', None) else "N/A")

        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:

            # ------ Hoja 1: Resumen ------
            resumen_rows = [
                ["TerraBioLab UTC — Reporte de Salud Microbiológica", ""],
                ["Fecha de generación", datetime.now().strftime("%d/%m/%Y %H:%M")],
                ["Analista", str(usuario) if usuario else "Sistema"],
                ["", ""],
                ["--- MUESTRA ---", ""],
                ["Código", _safe(muestra, "codigo")],
                ["Cultivo", cultivo_nom],
                ["Variedad/Clon", var_nom],
                ["Tipo de muestra", _safe(muestra, "tipo_muestra")],
                ["Localidad", _safe(muestra, "localidad")],
                ["Finca/Lote", _safe(muestra, "finca_lote")],
                ["Altitud (msnm)", _safe(muestra, "altitud")],
                ["Fecha de registro", _safe(muestra, "fecha_registro")],
                ["", ""],
                ["--- PARÁMETROS ANALÍTICOS ---", ""],
                ["Marcador molecular", tipo],
                ["Nivel taxonómico", nivel],
                ["Top N", str(top_n)],
                ["", ""],
                ["--- ÍNDICE DE SALUD ---", ""],
                ["Índice de Salud del Suelo (0-100)", str(indice_salud)],
                ["Nivel cualitativo", nivel_salud],
                ["", ""],
                ["--- DIVERSIDAD ALFA ---", ""],
                ["Riqueza de taxa", str(diversidad.get("riqueza", len(todos_taxa)))],
                ["Shannon H'", f"{float(diversidad.get('shannon', 0) or 0):.4f}"],
                ["Simpson D", f"{float(diversidad.get('simpson', 0) or 0):.4f}"],
                ["Equitatividad J'", f"{float(diversidad.get('equitatividad', 0) or 0):.4f}"],
                ["", ""],
                ["--- CLASIFICACIÓN FUNCIONAL ---", ""],
                ["Taxa Benéficos", str(totales_clas.get("benefico", 0))],
                ["Taxa Fitopatógenos", str(totales_clas.get("fitopatogeno", 0))],
                ["Taxa Neutrales", str(totales_clas.get("neutral", 0))],
                ["Taxa Sin Catalogar", str(totales_clas.get("sin_clasificar", 0))],
            ]
            if len(muestras) > 1:
                resumen_rows.append(["", ""])
                resumen_rows.append(["--- MUESTRAS INCLUIDAS ---", ""])
                for m in muestras:
                    resumen_rows.append([str(m.codigo), str(getattr(m, 'localidad', '') or '')])

            df_resumen = pd.DataFrame(resumen_rows, columns=["Campo", "Valor"])
            df_resumen.to_excel(writer, index=False, sheet_name="Resumen")

            # ------ Hoja 2: Top_N ------
            top_records = []
            for r in top_taxa:
                top_records.append({
                    "Taxonomia": r.get("taxonomia", r.get("nombre", "?")),
                    "Total_Hits": r.get("total_hits", r.get("hits", 0)),
                    "Abundancia_Pct": r.get("total_porcentaje", r.get("porcentaje", 0)),
                    "Clasificacion": r.get("clasificacion", "sin_clasificar"),
                })
            df_top = pd.DataFrame(top_records) if top_records else pd.DataFrame(
                columns=["Taxonomia", "Total_Hits", "Abundancia_Pct", "Clasificacion"]
            )
            df_top.to_excel(writer, index=False, sheet_name="Top_N")

            # ------ Hoja 3: Taxonomia_Completa ------
            todos_records = []
            for r in todos_taxa:
                todos_records.append({
                    "Taxonomia": r.get("taxonomia", r.get("nombre", "?")),
                    "Total_Hits": r.get("total_hits", r.get("hits", 0)),
                    "Abundancia_Pct": r.get("total_porcentaje", r.get("porcentaje", 0)),
                    "Clasificacion": r.get("clasificacion", "sin_clasificar"),
                })
            df_todos = pd.DataFrame(todos_records) if todos_records else pd.DataFrame(
                columns=["Taxonomia", "Total_Hits", "Abundancia_Pct", "Clasificacion"]
            )
            df_todos.to_excel(writer, index=False, sheet_name="Taxonomia_Completa")

            # ------ Hoja 4: Beneficos ------
            beneficos = detalle_clas.get("benefico", [])
            df_ben = pd.DataFrame([{
                "Nombre": b.get("nombre", ""),
                "Abundancia_Pct": b.get("porcentaje", 0),
                "Descripcion": b.get("descripcion", ""),
                "Referencia": b.get("referencia", ""),
            } for b in beneficos]) if beneficos else pd.DataFrame(
                columns=["Nombre", "Abundancia_Pct", "Descripcion", "Referencia"]
            )
            df_ben.to_excel(writer, index=False, sheet_name="Beneficos")

            # ------ Hoja 5: Fitopatogenos ------
            fitopatogenos = detalle_clas.get("fitopatogeno", [])
            df_fito = pd.DataFrame([{
                "Nombre": f.get("nombre", ""),
                "Abundancia_Pct": f.get("porcentaje", 0),
                "Descripcion": f.get("descripcion", ""),
                "Referencia": f.get("referencia", ""),
            } for f in fitopatogenos]) if fitopatogenos else pd.DataFrame(
                columns=["Nombre", "Abundancia_Pct", "Descripcion", "Referencia"]
            )
            df_fito.to_excel(writer, index=False, sheet_name="Fitopatogenos")

            # ------ Hoja 6: Diversidad ------
            div_records = [
                {"Metrica": "Riqueza de taxa", "Valor": str(diversidad.get("riqueza", len(todos_taxa)))},
                {"Metrica": "Shannon H'", "Valor": f"{float(diversidad.get('shannon', 0) or 0):.4f}"},
                {"Metrica": "Simpson D", "Valor": f"{float(diversidad.get('simpson', 0) or 0):.4f}"},
                {"Metrica": "Equitatividad J'", "Valor": f"{float(diversidad.get('equitatividad', 0) or 0):.4f}"},
            ]
            df_div = pd.DataFrame(div_records)
            df_div.to_excel(writer, index=False, sheet_name="Diversidad")

        buffer.seek(0)
        fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre = f"reporte_{tipo}_{nivel}_multisheet_{fecha}.xlsx"
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
