import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Sum
from django.shortcuts import render

from ..models import MuestraSuelo, ResultadoTaxonomico
from ..services.business.analysis_service import obtener_diversidad, obtener_lookup_catalogo
from analisis.constants import MARCADORES_VALIDOS, clasificar_taxon

@login_required
def dashboard(request):
    tipo_raw = request.GET.get("tipo", "16S")
    tipo = tipo_raw if tipo_raw in MARCADORES_VALIDOS else "16S"

    contexto_estadisticas = {}

    try:
        # Consultas base
        analisis = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo
        ).select_related("archivo__muestra__variedad_clon").order_by("-id")

        muestras = MuestraSuelo.objects.filter(
            archivos_moleculares__tipo_analisis=tipo
        ).select_related("cultivo", "variedad_clon").distinct().order_by("-id")

        total_analisis = analisis.count()
        total_muestras = muestras.count()

        muestras_por_variedad = list(
            muestras.exclude(cultivo__isnull=True)
            .values(
                cid=F("cultivo_id"),
                nombre_variedad=F("cultivo__nombre"),
                imagen_cultivo=F("cultivo__imagen"),
                imagen_url_cultivo=F("cultivo__imagen_url"),
            )
            .annotate(total=Count("id"))
            .order_by("-total")
        )

        # Desglose de variedades/clones por cultivo (para el modal que se abre
        # al hacer clic en una tarjeta de "Muestras por Cultivo"). El alias no
        # puede llamarse "cultivo_id" en .values(): Django lo rechaza por
        # colisionar con el nombre real del campo FK en el modelo.
        variedades_por_cultivo: dict = {}
        filas_variedades = (
            muestras.exclude(variedad_clon__isnull=True)
            .values(cid=F("cultivo_id"), nombre=F("variedad_clon__nombre"))
            .annotate(total=Count("id"))
            .order_by("cid", "-total")
        )
        for fila in filas_variedades:
            variedades_por_cultivo.setdefault(str(fila["cid"]), []).append(
                {"nombre": fila["nombre"], "total": fila["total"]}
            )

        # Clasificación funcional — mismo lookup canónico (normalizado y
        # filtrado por nivel) que usan Comparar/Avanzado/Reportes, en vez de
        # un match directo por nombre crudo que podía clasificar distinto un
        # mismo género según la página.
        conteos_funcionales = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo
        ).values("genus").annotate(total_hits=Sum("num_hits"))

        catalogo_lookup = obtener_lookup_catalogo(tipo, nivel="genus")

        total_beneficos = 0
        total_fitopatogenos = 0
        total_sin_clasificacion = 0

        for c in conteos_funcionales:
            genus = c["genus"] or ""
            hits = c["total_hits"] or 0
            clasif = clasificar_taxon(genus, catalogo_lookup, "genus")
            if clasif == "benefico":
                total_beneficos += hits
            elif clasif == "fitopatogeno":
                total_fitopatogenos += hits
            else:
                total_sin_clasificacion += hits


        # Diversidad alfa — por muestra individual, sobre todos los taxa
        contexto_estadisticas = obtener_diversidad(tipo=tipo) or {}

    except Exception as e:
        import traceback
        traceback.print_exc()
        messages.error(request, f"Error crítico: {str(e)}")
        return render(request, "analisis/dashboard.html", {"error_critico": True})

    return render(request, "analisis/dashboard.html", {
        "analisis": analisis,
        "productos": muestras,
        "total_analisis": total_analisis,
        "total_productos": total_muestras,
        "total_beneficos": total_beneficos,
        "total_fitopatogenos": total_fitopatogenos,
        "total_sin_clasificacion": total_sin_clasificacion,
        "productos_por_variedad": muestras_por_variedad,
        "variedades_por_cultivo_json": json.dumps(variedades_por_cultivo, default=str),
        "tipo_actual": tipo,
        "marcadores_disponibles": MARCADORES_VALIDOS,
        "estadisticas": contexto_estadisticas,
        "es_estudiante": request.user.rol == 'estudiante',
    })