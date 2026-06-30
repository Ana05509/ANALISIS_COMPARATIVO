from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count

from ..models import MuestraSuelo, ArchivoMolecular
from analisis.constants import MARCADORES_VALIDOS

@login_required
def historial(request):
    """Historial de muestras procesadas en los laboratorios."""
    tipo_raw = request.GET.get("tipo", "16S")
    tipo = tipo_raw if tipo_raw in MARCADORES_VALIDOS else "16S"
    busqueda = request.GET.get("q", "").strip()

    try:
        muestras = MuestraSuelo.objects.filter(
            archivos_moleculares__tipo_analisis=tipo
        ).distinct().order_by("-id")

        if busqueda:
            muestras = muestras.filter(codigo__icontains=busqueda)

        muestras = muestras.annotate(
            total_analisis=Count("archivos_moleculares__resultados_taxonomicos", distinct=True)
        )

        analisis = ArchivoMolecular.objects.filter(
            tipo_analisis=tipo
        ).select_related("muestra__variedad_clon").order_by("-id")

    except Exception as e:
        messages.error(request, f"Error al consultar la bitácora histórica: {str(e)}")
        muestras = MuestraSuelo.objects.none()
        analisis = ArchivoMolecular.objects.none()

    return render(request, "analisis/historial.html", {
        "muestras":               muestras,
        "analisis":               analisis,
        "tipo_actual":            tipo,
        "busqueda":               busqueda,
        "marcadores_disponibles": MARCADORES_VALIDOS,
    })