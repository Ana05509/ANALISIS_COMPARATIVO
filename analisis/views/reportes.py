from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
import pandas as pd

from ..models import MuestraSuelo, ResultadoTaxonomico
from ..services.business.report_service import (
    generar_reporte_analisis,
    obtener_historial_reportes,
    obtener_reporte_por_id,
)
from ..services.business.export_service import ExportService
from django.db.models import F, Sum

MARCADORES_VALIDOS = ("16S", "ITS")
FORMATOS_VALIDOS   = ("pdf", "excel", "html", "json")  # Phase 2: added html, json


@login_required
def reportes(request):
    """README: "Salida de Resultados: reportes interpretativos para usuarios finales" """
    tipo_raw = request.GET.get("tipo", "16S")
    tipo = tipo_raw if tipo_raw in MARCADORES_VALIDOS else "16S"

    try:
        muestras  = MuestraSuelo.objects.filter(
            archivomolecular__tipo_analisis=tipo
        ).distinct().order_by("-id")
        historial = obtener_historial_reportes(tipo=tipo)
    except Exception as e:
        messages.error(request, f"Error al cargar los reportes: {str(e)}")
        muestras  = MuestraSuelo.objects.none()
        historial = []

    return render(request, "analisis/reportes.html", {
        "productos":              muestras,
        "historial_reportes":     historial,
        "tipo_actual":            tipo,
        "marcadores_disponibles": MARCADORES_VALIDOS,
        "formatos_disponibles":   FORMATOS_VALIDOS,
        "total_reportes":         len(historial),
    })


@login_required
@require_POST
def generar_reporte(request):
    """README: Rol Técnico Agrícola y Analista pueden exportar reportes."""
    tipo        = request.POST.get("tipo", "16S")
    variedad_id = request.POST.get("producto_id") or None
    formato     = request.POST.get("formato", "pdf")
    top_n       = int(request.POST.get("top_n", 10))
    nivel       = request.POST.get("nivel", "genus")

    if tipo not in MARCADORES_VALIDOS:
        return JsonResponse({"ok": False, "error": "Marcador inválido."}, status=400)
    if formato not in FORMATOS_VALIDOS:
        return JsonResponse({"ok": False, "error": "Formato inválido."}, status=400)

    try:
        # Obtener datos para el reporte
        qs = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo
        )
        if variedad_id:
            qs = qs.filter(archivo__muestra__variedad_clon_id=variedad_id)
        
        # Crear DataFrame
        data = list(
            qs.values(nombre_tax=F("genus"))
            .annotate(total_hits=Sum("num_hits"), total_porcentaje=Sum("porcentaje_hits"))
            .order_by("-total_porcentaje")[:top_n]
        )
        
        df_reporte = pd.DataFrame(data) if data else pd.DataFrame()
        
        # ========== PHASE 2: EXPORTACIÓN AVANZADA ==========
        
        export_service = ExportService()
        
        if formato == "pdf":
            # PDF con datos y estadísticas
            datos_analisis = {
                "Marcador": tipo,
                "Nivel Taxonómico": nivel,
                "Top N": top_n,
                "Total Taxa": len(df_reporte),
            }
            
            response = export_service.exportar_pdf_response(
                titulo=f"Reporte de Análisis - {tipo}",
                datos_analisis=datos_analisis,
                df_datos=df_reporte,
                usuario=request.user,
                nombre_archivo=f"reporte_{tipo}_{nivel}.pdf"
            )
            return response
        
        elif formato == "html":
            # HTML interactivo
            datos_analisis = {
                "Metadatos": {
                    "Marcador": tipo,
                    "Nivel": nivel,
                    "Registros": len(df_reporte),
                }
            }
            
            response = export_service.generar_html_reporte(
                titulo=f"Reporte HTML - {tipo}",
                datos_analisis=datos_analisis,
                df_datos=df_reporte,
                usuario=request.user,
                nombre_archivo=f"reporte_{tipo}_{nivel}"
            )
            return response
        
        elif formato == "json":
            # JSON estructurado
            json_response = export_service.exportar_json(
                df_reporte.to_dict('records'),
                nombre_archivo=f"reporte_{tipo}_{nivel}.json"
            )
            return json_response
        
        else:  # Excel (formato original)
            resultado = generar_reporte_analisis(
                tipo=tipo, producto_id=variedad_id, formato=formato,
                top_n=top_n, nivel=nivel, usuario=request.user,
            )
            return JsonResponse({"ok": True, "url_reporte": resultado.get("url")})
    
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@login_required
def detalle_reporte(request, reporte_id):
    """README: Técnico Agrícola accede al reporte final sin modificarlo."""
    reporte = obtener_reporte_por_id(reporte_id)
    if reporte is None:
        messages.error(request, "Reporte no encontrado.")
        return redirect("analisis:reportes")

    return render(request, "analisis/reportes.html", {
        "reporte":                reporte,
        "tipo_actual":            reporte.get("tipo", "16S"),
        "marcadores_disponibles": MARCADORES_VALIDOS,
    })