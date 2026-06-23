from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required

from ..models import MuestraSuelo, ResultadoTaxonomico, CatalogoMicroorganismo

DISPLAY_LIMIT = 50  # filas mostradas en la tabla; todos los taxa siguen en BD


@login_required
def ver_producto(request, id):
    muestra = get_object_or_404(MuestraSuelo, id=id)

    archivo = muestra.archivos_moleculares.order_by("-id").first()
    tipo_actual = archivo.tipo_analisis if archivo else "16S"

    qs = ResultadoTaxonomico.objects.filter(archivo__muestra=muestra)

    total_analisis = qs.count()

    analisis_top = list(qs.order_by("-num_hits")[:DISPLAY_LIMIT])

    nombres_genus = [r.genus for r in analisis_top if r.genus]

    catalogo = {
        obj.nombre.lower(): obj.clasificacion
        for obj in CatalogoMicroorganismo.objects.filter(nombre__in=nombres_genus)
    }

    for reg in analisis_top:
        reg.clasificacion = catalogo.get((reg.genus or "").lower(), "sin_clasificar")

    total_beneficos         = sum(1 for r in analisis_top if r.clasificacion == "benefico")
    total_fitopatogenos     = sum(1 for r in analisis_top if r.clasificacion == "fitopatogeno")
    total_sin_clasificacion = sum(1 for r in analisis_top if r.clasificacion == "sin_clasificar")

    return render(request, "analisis/detalle_producto.html", {
        "producto":                muestra,
        "analisis":                analisis_top,
        "tipo_actual":             tipo_actual,
        "total_analisis":          total_analisis,
        "display_limit":           DISPLAY_LIMIT,
        "total_beneficos":         total_beneficos,
        "total_fitopatogenos":     total_fitopatogenos,
        "total_sin_clasificacion": total_sin_clasificacion,
    })
