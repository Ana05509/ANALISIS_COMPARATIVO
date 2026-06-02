# services/business/export_service.py
# Módulo de exportación avanzada (PDF, JSON, CSV, HTML) optimizado para consistencia de biodiversidad.

import json
import pandas as pd
from datetime import datetime
from io import BytesIO
from django.http import HttpResponse
from django.utils.text import slugify

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


class ExportService:
    """Servicio de exportación avanzada a múltiples formatos con soporte biogeográfico."""

    @staticmethod
    def exportar_json(datos, nombre_archivo=None):
        """
        Exporta estructuras de datos o DataFrames a formato JSON unificado.
        """
        if isinstance(datos, pd.DataFrame):
            json_str = datos.to_json(orient='records', indent=2)
        elif isinstance(datos, dict):
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
        """
        Exporta DataFrames biológicos a CSV, manteniendo consistencia analítica.
        """
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
                             usuario=None, formato_pagina="A4", muestra_obj=None):
        """
        Genera un reporte PDF formal de calidad científica utilizando ReportLab Platypus.
        Soporta dinámicamente el renderizado del bloque geográfico obligatorio de la muestra.
        """
        pagesize = A4 if formato_pagina == "A4" else letter
        buffer = BytesIO()
        
        doc = SimpleDocTemplate(
            buffer,
            pagesize=pagesize,
            rightMargin=36, leftMargin=36,
            topMargin=40, bottomMargin=40
        )
        
        styles = getSampleStyleSheet()
        
        COLOR_PRIMARY = colors.HexColor('#1b4332')
        COLOR_SECONDARY = colors.HexColor('#2d6a4f')
        COLOR_LIGHT = colors.HexColor('#f8f9fa')
        
        style_titulo = ParagraphStyle(
            'ScientificTitle', parent=styles['Heading1'], fontSize=20, leading=24,
            textColor=COLOR_PRIMARY, spaceAfter=15, alignment=TA_LEFT, fontName='Helvetica-Bold'
        )
        style_heading = ParagraphStyle(
            'ScientificHeading', parent=styles['Heading2'], fontSize=12, leading=16,
            textColor=COLOR_SECONDARY, spaceBefore=12, spaceAfter=6, fontName='Helvetica-Bold'
        )
        style_body = ParagraphStyle(
            'ScientificBody', parent=styles['Normal'], fontSize=9.5, leading=13, textColor=colors.HexColor('#212529')
        )
        style_th = ParagraphStyle(
            'TableTh', parent=styles['Normal'], fontSize=9, leading=11, textColor=colors.white, fontName='Helvetica-Bold'
        )

        contenido = []
        
        contenido.append(Paragraph(titulo, style_titulo))
        contenido.append(Paragraph(f"<b>Fecha de Generación:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", style_body))
        contenido.append(Paragraph(f"<b>Investigador/Analista:</b> {usuario or 'Sistema Central'}", style_body))
        contenido.append(Spacer(1, 10))
        
        # Validación explícita de nulidad para evitar reportOptionalMemberAccess en PDF
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
                [Paragraph("<b>🌍 Localidad:</b>", style_body), Paragraph(str(getattr(muestra_obj, 'localidad', 'N/A')), style_body),
                 Paragraph("<b>🏡 Finca / Lote:</b>", style_body), Paragraph(str(getattr(muestra_obj, 'finca_lote', 'N/A')), style_body)],
                [Paragraph("<b>⛰️ Altitud:</b>", style_body), Paragraph(f"{getattr(muestra_obj, 'altitud', 0)} msnm", style_body),
                 Paragraph("<b>Observaciones:</b>", style_body), Paragraph(str(obs_text), style_body)]
            ]
            t_meta = Table(meta_tabla, colWidths=[100, 160, 100, 160])
            t_meta.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), COLOR_LIGHT),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e9ecef')),
                ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#dee2e6')),
                ('TOPPADDING', (0,0), (-1,-1), 5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 5),
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

        contenido.append(Spacer(1, 15))
        contenido.append(Paragraph(
            "<font color='#64748b'><i>Nota: Este documento constituye un reporte técnico automatizado emitido por el "
            "Pipeline Bioinformático de Análisis de Suelos. Los resultados están sujetos al umbral del Top N seleccionado "
            "y las taxonomías remanentes han sido consolidadas de forma proporcional.</i></font>",
            style_body
        ))

        doc.build(contenido)
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def exportar_pdf_response(titulo, datos_analisis, df_datos=None, 
                              usuario=None, nombre_archivo=None, muestra_obj=None):
        """
        Envuelve el binario del PDF en una respuesta de descarga HTTP protegida para Django.
        """
        pdf_bytes = ExportService.generar_pdf_completo(
            titulo, datos_analisis, df_datos, usuario, muestra_obj=muestra_obj
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
        """
        Genera un reporte interpretativo interactivo en HTML limpio estructurado.
        """
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

        # Construcción condicional segura del bloque HTML para evitar reportOptionalMemberAccess
        if muestra_obj is not None:
            cultivo_nom = muestra_obj.cultivo.nombre if hasattr(muestra_obj, 'cultivo') and muestra_obj.cultivo else "N/A"
            var_nom = muestra_obj.variedad_clon.nombre if hasattr(muestra_obj, 'variedad_clon') and muestra_obj.variedad_clon else "N/A"
            
            html += f"""
                    <div class="meta-item"><strong>🌍 Localidad:</strong> {getattr(muestra_obj, 'localidad', 'N/A')}</div>
                    <div class="meta-item"><strong>🏡 Finca / Lote:</strong> {getattr(muestra_obj, 'finca_lote', 'N/A')}</div>
                    <div class="meta-item"><strong>⛰️ Altitud:</strong> {getattr(muestra_obj, 'altitud', 0)} msnm</div>
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
        """
        Empaqueta los archivos generados en un archivo comprimido ZIP para descarga masiva.
        """
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