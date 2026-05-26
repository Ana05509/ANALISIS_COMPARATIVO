from analisis.models import CatalogoMicroorganismo, ResultadoTaxonomico

CLASIFICACIONES_VALIDAS = ("benefico", "fitopatogeno", "neutral", "sin_clasificar")
NIVELES_VALIDOS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]


def obtener_catalogo_microorganismos(marcador="", clasificacion="", nivel=""):
    """
    README: "Clasificación Funcional: Benéficos ✅, Fitopatógenos ⚠️, Sin clasificación ⚪"
    """
    qs = CatalogoMicroorganismo.objects.all()

    if clasificacion in CLASIFICACIONES_VALIDAS:
        qs = qs.filter(clasificacion=clasificacion)
    if nivel in NIVELES_VALIDOS:
        qs = qs.filter(nivel=nivel)

    return qs.order_by("nombre")


def buscar_microorganismos(termino="", marcador="", clasificacion=""):
    qs = CatalogoMicroorganismo.objects.all()

    if termino:
        qs = qs.filter(nombre__icontains=termino)
    if clasificacion in CLASIFICACIONES_VALIDAS:
        qs = qs.filter(clasificacion=clasificacion)

    return qs.order_by("nombre")


def obtener_detalle_microorganismo(pk):
    try:
        return CatalogoMicroorganismo.objects.get(pk=pk)
    except CatalogoMicroorganismo.DoesNotExist:
        return None


def obtener_estadisticas_catalogo():
    """README: Clasificación Funcional ✅ ⚠️ ⚪"""
    qs = CatalogoMicroorganismo.objects.all()
    return {
        "total":               qs.count(),
        "total_beneficos":     qs.filter(clasificacion="benefico").count(),
        "total_fitopatogenos": qs.filter(clasificacion="fitopatogeno").count(),
        "total_sin_clas":      qs.filter(clasificacion="sin_clasificar").count(),
        "total_16s": ResultadoTaxonomico.objects.filter(archivo__tipo_analisis="16S").values("genus").distinct().count(),
        "total_its": ResultadoTaxonomico.objects.filter(archivo__tipo_analisis="ITS").values("genus").distinct().count(),
    }