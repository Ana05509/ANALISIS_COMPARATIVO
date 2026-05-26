import pandas as pd
from django.db.models import F, Sum
from analisis.models import ResultadoTaxonomico, CatalogoMicroorganismo
from analisis.services.processing.diversity import calcular_diversidad_alfa, calcular_diversidad_beta
from analisis.services.processing.abundance import comparar_abundancias

MAPA_NIVELES = {
    "kingdom": "kingdom", "phylum": "phylum", "class": "tax_class",
    "order": "order", "family": "family", "genus": "genus", "species": "species"
}
NIVELES_VALIDOS    = list(MAPA_NIVELES.keys())
MARCADORES_VALIDOS = ("16S", "ITS")
OPCIONES_TOP_N     = [5, 10, 25, 50]


def _base_queryset(tipo, variedad_id=None, muestra_id=None):
    qs = ResultadoTaxonomico.objects.filter(
        archivo__tipo_analisis=tipo
    ).select_related("archivo__muestra__variedad_clon")
    if variedad_id:
        qs = qs.filter(archivo__muestra__variedad_clon_id=variedad_id)
    if muestra_id:
        qs = qs.filter(archivo__muestra_id=muestra_id)
    return qs


def obtener_analisis_avanzado(tipo="16S", top_n=10, nivel="genus",
                               variedad_id=None, muestra_id=None):
    """
    README: "Rankings de Abundancia", "Agrupamiento Multinivel", "Clasificación Funcional"
    """
    if tipo not in MARCADORES_VALIDOS: tipo = "16S"
    if nivel not in NIVELES_VALIDOS:   nivel = "genus"
    if top_n not in OPCIONES_TOP_N:    top_n = 10

    campo_db = MAPA_NIVELES[nivel]
    qs = _base_queryset(tipo, variedad_id, muestra_id)

    if not qs.exists():
        return {"resumen": [], "tipo_actual": tipo, "nivel_actual": nivel, "top_actual": top_n}

    data = list(
        qs.values(nombre_tax=F(campo_db))
        .annotate(total_hits=Sum("num_hits"), total_porcentaje=Sum("porcentaje_hits"))
        .order_by("-total_porcentaje")[:top_n]
    )

    for item in data:
        ref = CatalogoMicroorganismo.objects.filter(
            nombre__iexact=item["nombre_tax"], nivel__iexact=nivel
        ).first()
        item["clasificacion"]    = ref.clasificacion if ref else "sin_clasificar"
        item["total_porcentaje"] = round(item["total_porcentaje"], 5)

    return {
        "resumen":      data,
        "tipo_actual":  tipo,
        "nivel_actual": nivel,
        "top_actual":   top_n,
    }


def obtener_top_n(tipo="16S", n=10, nivel="genus", variedad_id=None):
    """
    README: "Cálculo de Top N: filtra y ordena por abundancia relativa"
    """
    if tipo not in MARCADORES_VALIDOS: tipo = "16S"
    if nivel not in NIVELES_VALIDOS:   nivel = "genus"
    if n not in OPCIONES_TOP_N:        n = 10

    campo_db = MAPA_NIVELES[nivel]
    qs = _base_queryset(tipo, variedad_id)

    if not qs.exists():
        return []

    data = list(
        qs.values(nombre_tax=F(campo_db))
        .annotate(total_hits=Sum("num_hits"), total_porcentaje=Sum("porcentaje_hits"))
        .order_by("-total_porcentaje")[:n]
    )

    for item in data:
        ref = CatalogoMicroorganismo.objects.filter(
            nombre__iexact=item["nombre_tax"], nivel__iexact=nivel
        ).first()
        item["clasificacion"]    = ref.clasificacion if ref else "sin_clasificar"
        item["total_porcentaje"] = round(item["total_porcentaje"], 5)

    return data


def obtener_diversidad(tipo="16S", nivel="genus", variedad_id=None):
    """
    README: "Análisis Comparativo: biodiversidad microbiana en cultivos específicos"
    """
    if tipo not in MARCADORES_VALIDOS: tipo = "16S"
    campo_db = MAPA_NIVELES.get(nivel, "genus")

    qs = _base_queryset(tipo, variedad_id)
    if not qs.exists():
        return None

    df = pd.DataFrame(list(qs.values(taxonomia=F(campo_db), hits=F("porcentaje_hits"))))
    df_agrupado = (
        df.groupby("taxonomia", as_index=False)
        .agg({"hits": "sum"})
        .rename(columns={"hits": "%_hits"})
    )
    return calcular_diversidad_alfa(df_agrupado)


def obtener_analisis_diferencial(tipo="16S", nivel="genus",
                                  variedad_id=None, muestra_id=None):
    """
    README: "Análisis Diferencial: comparativa entre muestras de una misma especie"
    """
    if tipo not in MARCADORES_VALIDOS: tipo = "16S"
    campo_db = MAPA_NIVELES.get(nivel, "genus")

    qs_a = _base_queryset(tipo, variedad_id, muestra_id)
    qs_b = ResultadoTaxonomico.objects.filter(
        archivo__tipo_analisis=tipo
    ).exclude(archivo__muestra__variedad_clon_id=variedad_id)

    if not qs_a.exists() or not qs_b.exists():
        return None

    def _preparar_df(qs):
        data = list(qs.values(tax=F(campo_db), p=F("porcentaje_hits")))
        df = pd.DataFrame(data)
        return (
            df.groupby("tax", as_index=False)
            .agg({"p": "sum"})
            .rename(columns={"tax": nivel, "p": "%_hits"})
        )

    df_a = _preparar_df(qs_a)
    df_b = _preparar_df(qs_b)

    return {
        "diferencial": comparar_abundancias(df_a, df_b, nivel=nivel).to_dict(orient="records"),
        "beta":        calcular_diversidad_beta(df_a, df_b, nivel=nivel),
    }