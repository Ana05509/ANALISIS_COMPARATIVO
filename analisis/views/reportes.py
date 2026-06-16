from typing import Any
import pandas as pd
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse,HttpResponseBase
from django.views.decorators.http import require_POST
 

# Importaciones de Modelos
from analisis.models import MuestraSuelo

# Importaciones de Servicios (Estandarización)
from analisis.services.business.export_service import ExportService
from analisis.services.business.report_generation_service import ReportGenerationService

MARCADORES_VALIDOS = ("16S", "ITS")
FORMATOS_VALIDOS = ("pdf", "excel", "html", "json")


@login_required
def reportes(request):
    """Manejo de visualización del historial de reportes."""
    tipo_raw = request.GET.get("tipo", "16S")
    tipo = tipo_raw if tipo_raw in MARCADORES_VALIDOS else "16S"

    try:
        muestras = MuestraSuelo.objects.filter(
        archivos_moleculares__tipo_analisis=tipo
        ).distinct().order_by("-id")
        
        # Uso correcto del servicio para obtener historial
        historial = ReportGenerationService.obtener_historial_reportes(tipo)
        
    except Exception as e:
        messages.error(request, f"Error al cargar los reportes: {str(e)}")
        muestras = MuestraSuelo.objects.none()
        historial = []

    return render(request, "analisis/reportes.html", {
        "productos": muestras,
        "historial": historial,
        "tipo_actual": tipo,
        "marcadores_disponibles": MARCADORES_VALIDOS,
    })

@login_required
@require_POST
def generar_reporte(request) -> HttpResponseBase:
    tipo = request.POST.get("tipo", "16S")
    variedad_id = request.POST.get("producto_id", None)
    formato = request.POST.get("formato", "excel")
    top_n = int(request.POST.get("top_n", 10))
    nivel = request.POST.get("nivel", "genus")

    if formato not in FORMATOS_VALIDOS:
        return JsonResponse({"ok": False, "error": "Formato no soportado."}, status=400)

    try:
        df_reporte = pd.DataFrame()  # Simplificado, reemplaza con tu lógica real

        if formato == "html":
            resultado = ExportService.generar_html_reporte(
                titulo=f"Reporte {tipo}",
                datos_analisis={},
                df_datos=df_reporte,
                usuario=request.user,
                nombre_archivo=f"reporte_{tipo}"
            )
            # Garantizar que retornamos HttpResponse
            if isinstance(resultado, str):
                return HttpResponse(resultado, content_type="text/html")
            return resultado

        elif formato == "pdf":
            return ExportService.exportar_pdf_response(
                titulo=f"Reporte {tipo}",
                datos_analisis={},
                df_datos=df_reporte,
                usuario=request.user
            )

        elif formato == "json":
            return ExportService.exportar_json(
                df_reporte.to_dict('records'),
                f"reporte_{tipo}.json"
            )

        else:  # excel
            return ReportGenerationService.exportar_excel(tipo, variedad_id, nivel, top_n)

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

@login_required
def detalle_reporte(request, reporte_id):
    """Acceso al detalle de un reporte específico."""
    reporte = ReportGenerationService.obtener_reporte_por_id(reporte_id)
    if reporte is None:
        messages.error(request, "Reporte no encontrado.")
        return redirect("analisis:reportes")

    return render(request, "analisis/reportes.html", {
        "reporte": reporte,
    })