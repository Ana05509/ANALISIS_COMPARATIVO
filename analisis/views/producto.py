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

    catalogo = {
        obj.nombre.lower(): obj.clasificacion
        for obj in CatalogoMicroorganismo.objects.filter(nivel='genus', marcador=tipo_actual)
    }

    for reg in analisis_top:
        reg.clasificacion = catalogo.get((reg.genus or "").lower(), "sin_clasificar")

    total_beneficos         = sum(1 for r in analisis_top if r.clasificacion == "benefico")
    total_fitopatogenos     = sum(1 for r in analisis_top if r.clasificacion == "fitopatogeno")
    total_neutral           = sum(1 for r in analisis_top if r.clasificacion == "neutral")
    total_sin_clasificacion = sum(1 for r in analisis_top if r.clasificacion == "sin_clasificar")

    base = len(analisis_top) or 1
    pct_beneficos         = round(total_beneficos         / base * 100, 1)
    pct_fitopatogenos     = round(total_fitopatogenos     / base * 100, 1)
    pct_neutral           = round(total_neutral           / base * 100, 1)
    pct_sin_clasificacion = round(total_sin_clasificacion / base * 100, 1)

    return render(request, "analisis/detalle_producto.html", {
        "producto":                muestra,
        "analisis":                analisis_top,
        "tipo_actual":             tipo_actual,
        "total_analisis":          total_analisis,
        "display_limit":           DISPLAY_LIMIT,
        "total_beneficos":         total_beneficos,
        "total_fitopatogenos":     total_fitopatogenos,
        "total_neutral":           total_neutral,
        "total_sin_clasificacion": total_sin_clasificacion,
        "pct_beneficos":           pct_beneficos,
        "pct_fitopatogenos":       pct_fitopatogenos,
        "pct_neutral":             pct_neutral,
        "pct_sin_clasificacion":   pct_sin_clasificacion,
    })
