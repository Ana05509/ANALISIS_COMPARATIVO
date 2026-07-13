from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q

from ..models import MuestraSuelo
from analisis.constants import MARCADORES_VALIDOS

POR_PAGINA = 20

@login_required
def historial(request):
    tipo_raw = request.GET.get("tipo", "16S")
    tipo     = tipo_raw if tipo_raw in MARCADORES_VALIDOS else "16S"
    busqueda = request.GET.get("q", "").strip()
    localidad_f = request.GET.get("localidad", "").strip()

    try:
        qs = (
            MuestraSuelo.objects
            .filter(archivos_moleculares__tipo_analisis=tipo)
            .distinct()
            .select_related("cultivo", "variedad_clon")
            .order_by("-fecha_registro")
        )

        if busqueda:
            qs = qs.filter(
                Q(codigo__icontains=busqueda)
                | Q(localidad__icontains=busqueda)
                | Q(finca_lote__icontains=busqueda)
                | Q(cultivo__nombre__icontains=busqueda)
            )

        if localidad_f:
            qs = qs.filter(localidad__icontains=localidad_f)

        qs = qs.annotate(
            total_resultados=Count(
                "archivos_moleculares__resultados_taxonomicos", distinct=True
            ),
            total_archivos=Count("archivos_moleculares", distinct=True),
        )

        localidades = (
            MuestraSuelo.objects
            .filter(archivos_moleculares__tipo_analisis=tipo)
            .values_list("localidad", flat=True)
            .distinct()
            .order_by("localidad")
        )

        paginator = Paginator(qs, POR_PAGINA)
        page_obj  = paginator.get_page(request.GET.get("page", 1))
        total     = paginator.count

    except Exception as e:
        messages.error(request, f"Error al consultar la bitácora histórica: {str(e)}")
        page_obj  = None
        localidades = []
        total = 0

    return render(request, "analisis/historial.html", {
        "page_obj":               page_obj,
        "tipo_actual":            tipo,
        "busqueda":               busqueda,
        "localidad_f":            localidad_f,
        "localidades":            localidades,
        "marcadores_disponibles": MARCADORES_VALIDOS,
        "total_muestras":         total,
    })
