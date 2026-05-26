# services/business/export_service.py
# Módulo de exportación avanzada (PDF, JSON, CSV)
# README: "Salida de Resultados: reportes interpretativos y exportación"

import json
import pandas as pd
from datetime import datetime
from io import BytesIO
from django.http import HttpResponse
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


class ExportService:
    """Servicio de exportación avanzada a múltiples formatos."""

    @staticmethod
    def exportar_json(datos, nombre_archivo=None):
        """
        Exporta datos a JSON.
        
        Args:
            datos: Dict o DataFrame a exportar
            nombre_archivo: Nombre del archivo (opcional)
        
        Returns:
            JSON string o HttpResponse
        """
        if isinstance(datos, pd.DataFrame):
            json_str = datos.to_json(orient='records', indent=2)
        elif isinstance(datos, dict):
            json_str = json.dumps(datos, indent=2, default=str)
        else:
            return None

        if nombre_archivo is None:
            return json_str

        response = HttpResponse(json_str, content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
        return response

    @staticmethod
    def exportar_csv_avanzado(df, nombre_archivo=None, incluir_estadisticas=False):
        """
        Exporta DataFrame a CSV con opciones avanzadas.
        
        Args:
            df: DataFrame a exportar
            nombre_archivo: Nombre del archivo
            incluir_estadisticas: Si True, incluye estadísticas en el CSV
        
        Returns:
            CSV response
        """
        if df.empty:
            return None

        buffer = BytesIO()
        
        # Escribir CSV
        df.to_csv(buffer, index=False, encoding='utf-8')
        
        if incluir_estadisticas:
            # Agregar línea de separación y estadísticas
            stats_df = pd.DataFrame({
                col: [f"Media: {df[col].mean():.2f}" if df[col].dtype in ['float64', 'int64'] else "N/A"]
                for col in df.columns
            })
            stats_df.to_csv(buffer, index=False, encoding='utf-8', mode='a')
        
        buffer.seek(0)
        
        if nombre_archivo is None:
            return buffer.getvalue()

        response = HttpResponse(buffer, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
        return response

    @staticmethod
    def generar_pdf_completo(titulo, datos_analisis, df_datos=None, 
                              usuario=None, formato_pagina="A4"):
        """
        Genera un reporte PDF completo con análisis.
        
        Args:
            titulo: Título del reporte
            datos_analisis: Dict con datos a incluir
            df_datos: DataFrame opcional con tabla de datos
            usuario: Usuario que genera el reporte
            formato_pagina: "A4" o "letter"
        
        Returns:
            PDF bytes
        """
        pagesize = A4 if formato_pagina == "A4" else letter
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=pagesize,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=1*inch,
            bottomMargin=0.75*inch
        )
        
        # Estilos
        styles = getSampleStyleSheet()
        style_titulo = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#0066cc'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        style_heading = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#0066cc'),
            spaceAfter=10,
            spaceBefore=10,
        )
        
        # Contenido
        contenido = []
        
        # Título
        contenido.append(Paragraph(titulo, style_titulo))
        contenido.append(Spacer(1, 0.3*inch))
        
        # Metadata
        metadata = [
            f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            f"Usuario: {usuario or 'Sistema'}",
        ]
        for meta in metadata:
            contenido.append(Paragraph(meta, styles['Normal']))
        contenido.append(Spacer(1, 0.2*inch))
        
        # Análisis
        for seccion, valores in datos_analisis.items():
            contenido.append(Paragraph(seccion, style_heading))
            
            if isinstance(valores, dict):
                for clave, valor in valores.items():
                    texto = f"<b>{clave}:</b> {valor}"
                    contenido.append(Paragraph(texto, styles['Normal']))
            elif isinstance(valores, list):
                for item in valores:
                    contenido.append(Paragraph(f"• {item}", styles['Normal']))
            else:
                contenido.append(Paragraph(str(valores), styles['Normal']))
            
            contenido.append(Spacer(1, 0.1*inch))
        
        # Tabla de datos
        if df_datos is not None and not df_datos.empty:
            contenido.append(Spacer(1, 0.2*inch))
            contenido.append(Paragraph("Datos Detallados", style_heading))
            
            # Limitar a primeras 20 filas para no saturar
            df_mostrar = df_datos.head(20)
            
            # Convertir a tabla
            data = [list(df_mostrar.columns)] + df_mostrar.values.tolist()
            
            tabla = Table(data, colWidths=[2*inch / len(df_mostrar.columns)] * len(df_mostrar.columns))
            tabla.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0066cc')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
            ]))
            
            contenido.append(tabla)
        
        # Notas finales
        contenido.append(Spacer(1, 0.3*inch))
        contenido.append(Paragraph(
            "Este reporte fue generado automáticamente por el Sistema Web de Análisis Comparativo de Perfiles Microbianos.",
            styles['Normal']
        ))
        
        # Build PDF
        doc.build(contenido)
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def exportar_pdf_response(titulo, datos_analisis, df_datos=None, 
                               usuario=None, nombre_archivo=None):
        """
        Exporta PDF como HttpResponse.
        """
        pdf_bytes = ExportService.generar_pdf_completo(
            titulo, datos_analisis, df_datos, usuario
        )
        
        if nombre_archivo is None:
            fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
            nombre_archivo = f"reporte_{fecha}.pdf"
        
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
        return response

    @staticmethod
    def agregar_graficos_pdf(pdf_ruta, graficos_imagenes):
        """
        Agrega gráficos a un PDF existente.
        
        Args:
            pdf_ruta: Ruta del PDF existente
            graficos_imagenes: Lista de rutas de imágenes
        
        Returns:
            PDF modificado (bytes)
        """
        # Esta función es compleja y requeriría pypdf2 o similar
        # Por ahora retornamos un placeholder
        return None

    @staticmethod
    def generar_html_reporte(titulo, datos_analisis, df_datos=None, 
                              usuario=None, nombre_archivo=None):
        """
        Genera un reporte en HTML.
        
        Args:
            titulo: Título del reporte
            datos_analisis: Dict con datos
            df_datos: DataFrame opcional
            usuario: Usuario que genera
            nombre_archivo: Nombre del archivo
        
        Returns:
            HTML string o HttpResponse
        """
        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{titulo}</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    max-width: 900px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                h1 {{
                    color: #0066cc;
                    text-align: center;
                    border-bottom: 3px solid #0066cc;
                    padding-bottom: 10px;
                }}
                h2 {{
                    color: #0066cc;
                    margin-top: 20px;
                    border-left: 4px solid #0066cc;
                    padding-left: 10px;
                }}
                .metadata {{
                    background-color: #f9f9f9;
                    padding: 10px;
                    border-radius: 4px;
                    margin-bottom: 20px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 10px;
                }}
                th {{
                    background-color: #0066cc;
                    color: white;
                    padding: 10px;
                    text-align: left;
                }}
                td {{
                    border: 1px solid #ddd;
                    padding: 8px;
                }}
                tr:nth-child(even) {{
                    background-color: #f9f9f9;
                }}
                .footer {{
                    margin-top: 30px;
                    text-align: center;
                    color: #666;
                    font-size: 12px;
                    border-top: 1px solid #ddd;
                    padding-top: 10px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>{titulo}</h1>
                
                <div class="metadata">
                    <p><strong>Fecha:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
                    <p><strong>Usuario:</strong> {usuario or 'Sistema'}</p>
                </div>
        """
        
        # Análisis
        for seccion, valores in datos_analisis.items():
            html += f"<h2>{seccion}</h2>"
            
            if isinstance(valores, dict):
                html += "<table>"
                for clave, valor in valores.items():
                    html += f"<tr><td><strong>{clave}</strong></td><td>{valor}</td></tr>"
                html += "</table>"
            elif isinstance(valores, list):
                html += "<ul>"
                for item in valores:
                    html += f"<li>{item}</li>"
                html += "</ul>"
            else:
                html += f"<p>{valores}</p>"
        
        # Tabla de datos
        if df_datos is not None and not df_datos.empty:
            html += "<h2>Datos Detallados</h2>"
            html += df_datos.head(50).to_html(index=False, classes='data-table')
        
        html += f"""
                <div class="footer">
                    <p>Reporte generado por el Sistema Web de Análisis Comparativo de Perfiles Microbianos</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        if nombre_archivo is None:
            return html

        response = HttpResponse(html, content_type='text/html')
        response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}.html"'
        return response

    @staticmethod
    def exportar_zip_completo(datos_dict, nombre_base=None):
        """
        Exporta múltiples formatos en un ZIP.
        
        Args:
            datos_dict: Dict con diferentes datos
            nombre_base: Nombre base para los archivos
        
        Returns:
            ZIP bytes
        """
        import zipfile
        
        if nombre_base is None:
            nombre_base = f"reporte_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
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
