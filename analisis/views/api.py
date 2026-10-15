"""
API REST v1 — BioMicro UTC
Endpoints JSON de solo lectura. Autenticación por sesión Django.
Las vistas HTML existentes no se ven afectadas.

Base URL: /api/v1/
"""
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required
from django.db.models import F, Sum, Count

from analisis.models import (
    MuestraSuelo, ResultadoTaxonomico,
    CatalogoMicroorganismo, ArchivoMolecular,
)
from analisis.services.business.analysis_service import obtener_lookup_catalogo


def _error(msg, status=400):
    return JsonResponse({"ok": False, "error": msg}, status=status)


def _ok(data, status=200):
    return JsonResponse({"ok": True, "data": data}, status=status)


# ─────────────────────────────────────────────────────────────
# /api/v1/muestras/
# ─────────────────────────────────────────────────────────────
@login_required
@require_GET
def api_muestras(request):
    """
    Lista todas las muestras de suelo registradas.

    Parámetros opcionales (GET):
      - cultivo_id: filtrar por cultivo
      - q: búsqueda por código de muestra
    """
    qs = MuestraSuelo.objects.select_related("cultivo", "variedad_clon").order_by("-fecha_registro")

    cultivo_id = request.GET.get("cultivo_id")
    q          = request.GET.get("q", "").strip()

    if cultivo_id:
        if not cultivo_id.isdigit():
            return _error("cultivo_id debe ser numérico.")
        qs = qs.filter(cultivo_id=cultivo_id)
    if q:
        qs = qs.filter(codigo__icontains=q)

    data = [
        {
            "id":          m.id,
            "codigo":      m.codigo,
            "cultivo":     m.cultivo.nombre if m.cultivo else None,
            "variedad":    m.variedad_clon.nombre if m.variedad_clon else None,
            "localidad":   m.localidad,
            "tipo_muestra": m.tipo_muestra,
            "altitud":     m.altitud,
            "fecha":       m.fecha_registro.isoformat() if m.fecha_registro else None,
        }
        for m in qs
    ]
    return _ok(data)


# ─────────────────────────────────────────────────────────────
# /api/v1/muestras/<id>/
# ─────────────────────────────────────────────────────────────
@login_required
@require_GET
def api_muestra_detalle(request, pk):
    """
    Detalle de una muestra con resumen de clasificación funcional.

    Parámetros opcionales (GET):
      - tipo: 16S (default) | ITS
      - top_n: 5 | 10 | 25 | 50 (default 10)
    """
    try:
        muestra = MuestraSuelo.objects.select_related("cultivo", "variedad_clon").get(pk=pk)
    except MuestraSuelo.DoesNotExist:
        return _error("Muestra no encontrada.", 404)

    tipo  = request.GET.get("tipo", "16S")
    if tipo not in ("16S", "ITS"):
        tipo = "16S"
    try:
        top_n = int(request.GET.get("top_n", 10))
        if top_n not in (5, 10, 25, 50):
            top_n = 10
    except (ValueError, TypeError):
        top_n = 10

    qs = ResultadoTaxonomico.objects.filter(
        archivo__muestra=muestra,
        archivo__tipo_analisis=tipo,
    )

    catalogo = obtener_lookup_catalogo(tipo)

    todos_los_taxa = list(
        qs.values(taxonomia=F("genus"))
        .annotate(total_hits=Sum("num_hits"))
        .order_by("-total_hits")
    )
    # El total (100%) debe ser sobre TODA la muestra, no solo el Top N que se
    # va a mostrar — si se sumara después de recortar, los porcentajes del
    # Top N siempre sumarían 100% entre sí, aunque en realidad representen
    # menos que el total real de la muestra.
    grand_total = sum(t["total_hits"] for t in todos_los_taxa) or 1
    taxa = todos_los_taxa[:top_n]
    for t in taxa:
        t["porcentaje"]    = round(t["total_hits"] / grand_total * 100, 2)
        t["clasificacion"] = catalogo.get((t["taxonomia"] or "").lower(), "sin_clasificar")

    return _ok({
        "muestra": {
            "id":       muestra.id,
            "codigo":   muestra.codigo,
            "cultivo":  muestra.cultivo.nombre if muestra.cultivo else None,
            "localidad": muestra.localidad,
        },
        "tipo":        tipo,
        "top_n":       top_n,
        "total_taxa":  qs.values("genus").distinct().count(),
        "taxonomia":   taxa,
    })


# ─────────────────────────────────────────────────────────────
# /api/v1/catalogo/
# ─────────────────────────────────────────────────────────────
@login_required
@require_GET
def api_catalogo(request):
    """
    Lista las entradas del Catálogo de Microorganismos.

    Parámetros opcionales (GET):
      - marcador: 16S | ITS
      - clasificacion: benefico | fitopatogeno | neutral | sin_clasificar
      - q: búsqueda por nombre
      - page: número de página (default 1, 50 por página)
    """
    qs = CatalogoMicroorganismo.objects.order_by("nombre")

    marcador      = request.GET.get("marcador")
    clasificacion = request.GET.get("clasificacion")
    q             = request.GET.get("q", "").strip()

    if marcador in ("16S", "ITS"):
        qs = qs.filter(marcador=marcador)
    if clasificacion in ("benefico", "fitopatogeno", "neutral", "sin_clasificar"):
        qs = qs.filter(clasificacion=clasificacion)
    if q:
        qs = qs.filter(nombre__icontains=q)

    # Paginación simple
    page_size = 50
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    offset = (page - 1) * page_size
    total  = qs.count()

    data = [
        {
            "id":            obj.id,
            "nombre":        obj.nombre,
            "nivel":         obj.nivel,
            "marcador":      obj.marcador,
            "clasificacion": obj.clasificacion,
            "descripcion":   obj.descripcion or None,
            "referencia":    obj.referencia  or None,
        }
        for obj in qs[offset: offset + page_size]
    ]

    return _ok({
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     (total + page_size - 1) // page_size,
        "resultados": data,
    })


# ─────────────────────────────────────────────────────────────
# /api/v1/catalogo/<nombre>/
# ─────────────────────────────────────────────────────────────
@login_required
@require_GET
def api_catalogo_entrada(request, nombre):
    """
    Devuelve la clasificación de un taxón específico del catálogo.

    Parámetros opcionales (GET):
      - marcador: 16S (default) | ITS
    """
    marcador = request.GET.get("marcador", "16S")
    if marcador not in ("16S", "ITS"):
        marcador = "16S"

    obj = CatalogoMicroorganismo.objects.filter(
        nombre__iexact=nombre,
        marcador=marcador,
    ).first()

    if not obj:
        return _error(f"No se encontró '{nombre}' en el catálogo para marcador {marcador}.", 404)

    return _ok({
        "id":            obj.id,
        "nombre":        obj.nombre,
        "nivel":         obj.nivel,
        "marcador":      obj.marcador,
        "clasificacion": obj.clasificacion,
        "descripcion":   obj.descripcion or None,
        "referencia":    obj.referencia  or None,
    })


# ─────────────────────────────────────────────────────────────
# /api/v1/estadisticas/
# ─────────────────────────────────────────────────────────────
@login_required
@require_GET
def api_estadisticas(request):
    """
    Estadísticas globales del sistema para tableros externos.
    """
    archivos_con = ResultadoTaxonomico.objects.values("archivo_id").distinct()
    sin_procesar = ArchivoMolecular.objects.exclude(id__in=archivos_con).count()

    conteos_cat = {
        row["clasificacion"]: row["total"]
        for row in CatalogoMicroorganismo.objects.values("clasificacion")
                                                  .annotate(total=Count("id"))
    }

    return _ok({
        "muestras":          MuestraSuelo.objects.count(),
        "archivos_total":    ArchivoMolecular.objects.count(),
        "archivos_sin_procesar": sin_procesar,
        "resultados_taxonomicos": ResultadoTaxonomico.objects.count(),
        "catalogo": {
            "total":          CatalogoMicroorganismo.objects.count(),
            "beneficos":      conteos_cat.get("benefico", 0),
            "fitopatogenos":  conteos_cat.get("fitopatogeno", 0),
            "neutrales":      conteos_cat.get("neutral", 0),
            "sin_clasificar": conteos_cat.get("sin_clasificar", 0),
        },
    })
