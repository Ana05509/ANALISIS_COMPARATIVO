from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from ..models import MuestraSuelo, ResultadoTaxonomico, CatalogoMicroorganismo


@login_required
def ver_producto(request, id):
    """
    Detalle de una muestra con sus resultados taxonómicos.
    README: "Segmentación Detallada: CCN51, Clon 100, Clon 1..."
    """
    muestra = get_object_or_404(MuestraSuelo, id=id)

    analisis = ResultadoTaxonomico.objects.filter(
        archivo__muestra=muestra
    ).select_related("archivo").order_by("-id")

    # Clasificación funcional cruzando con CatalogoMicroorganismo por genus
    nombres_genus = analisis.values_list("genus", flat=True).distinct()

    total_beneficos = CatalogoMicroorganismo.objects.filter(
        nombre__in=nombres_genus,
        clasificacion="benefico"
    ).count()

    total_fitopatogenos = CatalogoMicroorganismo.objects.filter(
        nombre__in=nombres_genus,
        clasificacion="fitopatogeno"
    ).count()

    total_sin_clasificacion = CatalogoMicroorganismo.objects.filter(
        nombre__in=nombres_genus,
        clasificacion="sin_clasificar"
    ).count()

    return render(request, "analisis/detalle_producto.html", {
        "producto":                muestra,
        "analisis":                analisis,
        "total_analisis":          analisis.count(),
        "total_beneficos":         total_beneficos,
        "total_fitopatogenos":     total_fitopatogenos,
        "total_sin_clasificacion": total_sin_clasificacion,
    })