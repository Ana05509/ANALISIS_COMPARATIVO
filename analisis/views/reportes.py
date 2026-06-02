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
FORMATOS_VALIDOS   = ("pdf", "excel", "html", "json")


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
        "historial":              historial,
        "tipo_actual":            tipo,
        "marcadores_disponibles": MARCADORES_VALIDOS,
    })


@login_required
@require_POST
def generar_reporte(request) -> HttpResponse:
    """
    Vista para la generación y exportación de reportes.
    SOLUCIÓN PYLANCE: Se define el tipo de retorno explícito -> HttpResponse
    y se envuelven todas las salidas en objetos de respuesta nativos de Django.
    """
    tipo        = request.POST.get("tipo", "16S")
    variedad_id = request.POST.get("producto_id", None)
    formato     = request.POST.get("formato", "excel")
    top_n       = int(request.POST.get("top_n", 10))
    nivel       = request.POST.get("nivel", "genus")

    if formato not in FORMATOS_VALIDOS:
        return JsonResponse({"ok": False, "error": "Formato de archivo no soportado."}, status=400)

    try:
        raw_qs = ResultadoTaxonomico.objects.filter(archivo__tipo_analisis=tipo)
        if variedad_id:
            raw_qs = raw_qs.filter(archivo__muestra__variedad_clon_id=variedad_id)
            
        datos_analisis = list(raw_qs.values(nivel, "num_hits", "porcentaje_hits"))
        
        if not datos_analisis:
            return JsonResponse({"ok": False, "error": "No existen registros moleculares con los filtros seleccionados."}, status=404)
            
        df_reporte = pd.DataFrame(datos_analisis).groupby(nivel, as_index=False).sum()
        df_reporte = df_reporte.sort_values(by="num_hits", ascending=False).head(top_n)

        export_service = ExportService()

        if formato == "html":
            html_puro = export_service.exportar_html(df_reporte.to_html(classes="table table-striped"), f"reporte_{tipo}_{nivel}.html")
            # Forzamos conversión a string por si el servicio devuelve un objeto inesperado
            return HttpResponse(str(html_puro), content_type="text/html")
        
        elif formato == "pdf":
            response = export_service.exportar_pdf(
                datos_analisis=datos_analisis,
                df_datos=df_reporte,
                usuario=request.user,
                nombre_archivo=f"reporte_{tipo}_{nivel}"
            )
            # Nos aseguramos de que sea un objeto de respuesta válido, si no, lo envolvemos
            if isinstance(response, HttpResponse):
                return response
            return HttpResponse(bytes(response), content_type="application/pdf")
        
        elif formato == "json":
            json_response = export_service.exportar_json(
                df_reporte.to_dict('records'),
                nombre_archivo=f"reporte_{tipo}_{nivel}.json"
            )
            # Si el servicio devuelve un String JSON en lugar de un JsonResponse, lo envolvemos correctamente
            if isinstance(json_response, HttpResponse):
                return json_response
            return HttpResponse(str(json_response), content_type="application/json")
        
        else:  # Formato Excel u otros procesados por report_service
            resultado = generar_reporte_analisis(
                tipo=tipo, producto_id=variedad_id, formato=formato,
                top_n=top_n, nivel=nivel, usuario=request.user,
            )
            return JsonResponse({"ok": True, "url_reporte": resultado.get("url")})
            
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

    # RETORNO DE SEGURIDAD EXPLICITO: Evita que Pylance asuma un posible retorno 'None' al final del bloque try
    return JsonResponse({"ok": False, "error": "Flujo de exportación no resuelto."}, status=500)


@login_required
def detalle_reporte(request, reporte_id):
    """README: Técnico Agrícola accede al reporte final sin modificarlo."""
    reporte = obtener_reporte_por_id(reporte_id)
    if reporte is None:
        messages.error(request, "Reporte no encontrado.")
        return redirect("analisis:reportes")

    return render(request, "analisis/reportes.html", {
        "reporte": reporte,
    })