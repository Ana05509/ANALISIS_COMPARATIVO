from io import BytesIO
from datetime import datetime

import pandas as pd
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import F, Sum
from django.http import JsonResponse, HttpResponse, HttpResponseBase
from django.views.decorators.http import require_POST

from analisis.models import MuestraSuelo, ResultadoTaxonomico, CatalogoMicroorganismo
from analisis.services.business.analysis_service import obtener_analisis_avanzado, obtener_diversidad
from analisis.services.business.export_service import ExportService
from analisis.services.business.report_generation_service import ReportGenerationService

MARCADORES_VALIDOS = ("16S", "ITS")
FORMATOS_VALIDOS   = ("pdf", "excel", "html", "json")
OPCIONES_TOP_N     = [5, 10, 25, 50]
NIVELES_VALIDOS    = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
MAPA_NIVELES = {
    "kingdom": "kingdom", "phylum": "phylum", "class": "tax_class",
    "order": "order",     "family": "family",  "genus": "genus",
    "species": "species",
}


@login_required
def reportes(request):
    tipo_raw = request.GET.get("tipo", "16S")
    tipo = tipo_raw if tipo_raw in MARCADORES_VALIDOS else "16S"

    nivel_raw = request.GET.get("nivel", "genus")
    nivel = nivel_raw if nivel_raw in NIVELES_VALIDOS else "genus"

    try:
        top_n = int(request.GET.get("top_n", 25))
        if top_n not in OPCIONES_TOP_N:
            top_n = 25
    except (ValueError, TypeError):
        top_n = 25

    variedad_id = request.GET.get("producto_id") or None

    resumen   = []
    diversidad = {}
    muestras  = MuestraSuelo.objects.none()
    historial = []

    try:
        muestras  = MuestraSuelo.objects.filter(
            archivos_moleculares__tipo_analisis=tipo
        ).distinct().order_by("-id")
        historial = ReportGenerationService.obtener_historial_reportes(tipo)

        resultado  = obtener_analisis_avanzado(tipo=tipo, top_n=top_n, nivel=nivel, variedad_id=variedad_id)
        resumen    = resultado.get("resumen", [])
        diversidad = obtener_diversidad(tipo=tipo, nivel=nivel, variedad_id=variedad_id) or {}
    except Exception as e:
        messages.error(request, f"Error al cargar los reportes: {str(e)}")

    return render(request, "analisis/reportes.html", {
        "productos":              muestras,
        "historial":              historial,
        "tipo_actual":            tipo,
        "nivel_actual":           nivel,
        "marcadores_disponibles": MARCADORES_VALIDOS,
        "niveles_disponibles":    NIVELES_VALIDOS,
        "top_n_actual":           top_n,
        "opciones_top_n":         OPCIONES_TOP_N,
        "resumen":                resumen,
        "diversidad":             diversidad,
        "variedad_id_actual":     variedad_id,
    })


@login_required
@require_POST
def generar_reporte(request) -> HttpResponseBase:
    tipo = request.POST.get("tipo", "16S")
    if tipo not in MARCADORES_VALIDOS:
        tipo = "16S"

    nivel = request.POST.get("nivel", "genus")
    if nivel not in NIVELES_VALIDOS:
        nivel = "genus"
    campo_db = MAPA_NIVELES[nivel]

    formato = request.POST.get("formato", "excel")
    if formato not in FORMATOS_VALIDOS:
        return JsonResponse({"ok": False, "error": "Formato no soportado."}, status=400)

    variedad_id = request.POST.get("producto_id") or None

    try:
        top_n = int(request.POST.get("top_n", 25))
        if top_n not in OPCIONES_TOP_N:
            top_n = 25
    except (ValueError, TypeError):
        top_n = 25

    try:
        qs = ResultadoTaxonomico.objects.filter(archivo__tipo_analisis=tipo)
        if variedad_id:
            qs = qs.filter(archivo__muestra__variedad_clon_id=variedad_id)

        if not qs.exists():
            return JsonResponse({"ok": False, "error": "No hay datos para el reporte."}, status=404)

        if formato == "excel":
            return _generar_excel_completo(qs, tipo, nivel, campo_db)

        # PDF / HTML / JSON — usa top_n para visualización
        # grand_total desde TODOS los taxa antes del slice
        grand_total = qs.aggregate(total=Sum("num_hits"))["total"] or 1

        data = list(
            qs.values(taxonomia=F(campo_db))
            .annotate(total_hits=Sum("num_hits"))
            .order_by("-total_hits")[:top_n]
        )
        if not data:
            return JsonResponse({"ok": False, "error": "No hay datos para el reporte."}, status=404)

        for r in data:
            r["porcentaje"] = round(r["total_hits"] / grand_total * 100, 5)

        df_reporte = pd.DataFrame(data)
        titulo = f"Reporte {tipo} — {nivel.capitalize()} Top {top_n}"

        if formato == "pdf":
            return ExportService.exportar_pdf_response(
                titulo=titulo,
                datos_analisis={},
                df_datos=df_reporte,
                usuario=request.user,
                nombre_archivo=f"reporte_{tipo}_{nivel}_top{top_n}.pdf",
            )

        if formato == "html":
            resultado = ExportService.generar_html_reporte(
                titulo=titulo,
                datos_analisis={},
                df_datos=df_reporte,
                usuario=request.user,
                nombre_archivo=f"reporte_{tipo}_{nivel}.html",
            )
            if isinstance(resultado, str):
                return HttpResponse(resultado, content_type="text/html")
            return resultado

        # json
        return ExportService.exportar_json(
            df_reporte.to_dict("records"),
            f"reporte_{tipo}.json",
        )

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


def _generar_excel_completo(qs, tipo, nivel, campo_db) -> HttpResponse:
    """
    Genera Excel con TODOS los taxa (sin truncar).
    Porcentajes recalculados desde grand_total real.
    """
    grand_total = qs.aggregate(total=Sum("num_hits"))["total"] or 1

    data_all = list(
        qs.values(taxonomia=F(campo_db))
        .annotate(total_hits=Sum("num_hits"))
        .order_by("-total_hits")
    )
    for r in data_all:
        r["porcentaje"] = round(r["total_hits"] / grand_total * 100, 5)

    nombres = [r["taxonomia"] for r in data_all if r["taxonomia"]]
    catalogo_map = {
        obj["nombre"].lower(): obj["clasificacion"]
        for obj in CatalogoMicroorganismo.objects.filter(
            nombre__in=nombres, nivel=nivel
        ).values("nombre", "clasificacion")
    }
    for r in data_all:
        r["clasificacion"] = catalogo_map.get(str(r["taxonomia"]).lower(), "sin_clasificar")

    df_excel = pd.DataFrame(data_all)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_excel.to_excel(writer, index=False, sheet_name=f"Analisis_{tipo}")
    buffer.seek(0)

    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre = f"reporte_{tipo}_{nivel}_completo_{fecha}.xlsx"
    response = HttpResponse(
        buffer.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return response


@login_required
def detalle_reporte(request, reporte_id):
    reporte = ReportGenerationService.obtener_reporte_por_id(reporte_id)
    if reporte is None:
        messages.error(request, "Reporte no encontrado.")
        return redirect("analisis:reportes")
    return render(request, "analisis/reportes.html", {"reporte": reporte})
