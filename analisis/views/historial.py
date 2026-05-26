from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count

from ..models import MuestraSuelo, ArchivoMolecular

MARCADORES_VALIDOS = ("16S", "ITS")


@login_required
def historial(request):
    """
    Historial de muestras procesadas por marcador molecular.
    README: "Gestión de Muestras Agrícolas", "Segmentación Detallada"
    """
    tipo_raw = request.GET.get("tipo", "16S")
    tipo = tipo_raw if tipo_raw in MARCADORES_VALIDOS else "16S"
    busqueda = request.GET.get("q", "").strip()

    try:
        muestras = MuestraSuelo.objects.filter(
            archivomolecular__tipo_analisis=tipo
        ).distinct().order_by("-id")

        if busqueda:
            muestras = muestras.filter(codigo__icontains=busqueda)

        muestras = muestras.annotate(
            total_analisis=Count("archivomolecular__resultadotaxonomico", distinct=True)
        )

        analisis = ArchivoMolecular.objects.filter(
            tipo_analisis=tipo
        ).select_related("muestra__variedad_clon").order_by("-id")

    except Exception as e:
        messages.error(request, f"Error al cargar el historial: {str(e)}")
        muestras = MuestraSuelo.objects.none()
        analisis = ArchivoMolecular.objects.none()

    return render(request, "analisis/historial.html", {
        "productos":              muestras,
        "analisis":               analisis,
        "tipo_actual":            tipo,
        "marcadores_disponibles": MARCADORES_VALIDOS,
        "busqueda":               busqueda,
        "total_productos":        muestras.count(),
    })