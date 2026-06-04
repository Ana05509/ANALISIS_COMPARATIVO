import pandas as pd
from django.db.models import F, Sum, Avg
from analisis.models import ResultadoTaxonomico, CatalogoMicroorganismo, VariedadClon
from analisis.services.processing.diversity import DiversityService # CORRECCIÓN IMPORT
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

def obtener_analisis_avanzado(tipo="16S", top_n=10, nivel="genus", variedad_id=None, muestra_id=None):
    """Calcula el perfil taxonómico unificando el residuo bajo la firma de 'Otros'."""
    if tipo not in MARCADORES_VALIDOS: tipo = "16S"
    if nivel not in NIVELES_VALIDOS:   nivel = "genus"
    if top_n not in OPCIONES_TOP_N:    top_n = 10

    campo_db = MAPA_NIVELES[nivel]
    qs = _base_queryset(tipo, variedad_id, muestra_id)

    if not qs.exists():
        return {"resumen": [], "tipo_actual": tipo, "nivel_actual": nivel, "top_actual": top_n}

    todos_los_datos = list(
        qs.values(nombre_tax=F(campo_db))
        .annotate(
            total_hits=Sum("num_hits"), 
            total_porcentaje=Avg("porcentaje_hits")
        )
        .order_by("-total_porcentaje")
    )

    if not todos_los_datos:
        return {"resumen": [], "tipo_actual": tipo, "nivel_actual": nivel, "top_actual": top_n}

    datos_top = todos_los_datos[:top_n]
    datos_resto = todos_los_datos[top_n:]

    for item in datos_top:
        ref = CatalogoMicroorganismo.objects.filter(
            nombre__iexact=item["nombre_tax"], nivel__iexact=nivel
        ).first()
        item["clasificacion"] = ref.clasificacion if ref else "sin_clasificar"
        item["total_porcentaje"] = round(item["total_porcentaje"], 5)

    if datos_resto:
        suma_hits_resto = sum(x["total_hits"] for x in datos_resto)
        suma_porc_resto = sum(x["total_porcentaje"] for x in datos_resto)
        
        datos_top.append({
            "nombre_tax": "Otros microorganismos (< abundancia)",
            "total_hits": suma_hits_resto,
            "total_porcentaje": round(suma_porc_resto, 5),
            "clasificacion": "neutral"
        })

    return {
        "resumen":     datos_top,
        "tipo_actual":  tipo,
        "nivel_actual": nivel,
        "top_actual":   top_n,
    }

def obtener_top_n(tipo="16S", n=10, nivel="genus", variedad_id=None):
    if tipo not in MARCADORES_VALIDOS: tipo = "16S"
    if nivel not in NIVELES_VALIDOS:   nivel = "genus"
    if n not in OPCIONES_TOP_N:        n = 10

    campo_db = MAPA_NIVELES[nivel]
    qs = _base_queryset(tipo, variedad_id)

    if not qs.exists(): return []

    data = list(
        qs.values(nombre_tax=F(campo_db))
        .annotate(total_hits=Sum("num_hits"), total_porcentaje=Avg("porcentaje_hits"))
        .order_by("-total_porcentaje")[:n]
    )

    for item in data:
        ref = CatalogoMicroorganismo.objects.filter(nombre__iexact=item["nombre_tax"], nivel__iexact=nivel).first()
        item["clasificacion"] = ref.clasificacion if ref else "sin_clasificar"
        item["total_porcentaje"] = round(item["total_porcentaje"], 5)

    return data

def obtener_diversidad(tipo="16S", nivel="genus", variedad_id=None):
    if tipo not in MARCADORES_VALIDOS: tipo = "16S"
    campo_db = MAPA_NIVELES.get(nivel, "genus")

    qs = _base_queryset(tipo, variedad_id)
    if not qs.exists(): return None

    df = pd.DataFrame(list(qs.values(taxonomia=F(campo_db), hits=F("porcentaje_hits"))))
    df_agrupado = (
        df.groupby("taxonomia", as_index=False)
        .agg({"hits": "mean"})
        .rename(columns={"hits": "%_hits"})
    )
    return DiversityService.calcular_diversidad_alfa(df_agrupado) # CORRECCIÓN

def obtener_analisis_diferencial(tipo="16S", nivel="genus", variedad_id=None, muestra_id=None):
    if tipo not in MARCADORES_VALIDOS: tipo = "16S"
    campo_db = MAPA_NIVELES.get(nivel, "genus")

    if variedad_id:
        try:
            variedad_origen = VariedadClon.objects.get(id=variedad_id)
            cultivo_id = variedad_origen.cultivo_id
        except VariedadClon.DoesNotExist:
            return None
    elif muestra_id:
        try:
            qs_m = ResultadoTaxonomico.objects.filter(archivo__muestra_id=muestra_id).first()
            if not qs_m: return None
            cultivo_id = qs_m.archivo.muestra.cultivo_id
        except Exception:
            return None
    else:
        return None

    qs_a = _base_queryset(tipo, variedad_id, muestra_id)
    qs_b = ResultadoTaxonomico.objects.filter(archivo__tipo_analisis=tipo, archivo__muestra__cultivo_id=cultivo_id)
    if variedad_id:
        qs_b = qs_b.exclude(archivo__muestra__variedad_clon_id=variedad_id)

    if not qs_a.exists() or not qs_b.exists(): return None

    def _preparar_df(qs):
        data = list(qs.values(tax=F(campo_db), p=F("porcentaje_hits")))
        df = pd.DataFrame(data)
        if df.empty: return pd.DataFrame(columns=[nivel, "%_hits"])
        return df.groupby("tax", as_index=False).agg({"p": "mean"}).rename(columns={"tax": nivel, "p": "%_hits"})

    df_a = _preparar_df(qs_a)
    df_b = _preparar_df(qs_b)

    if df_a.empty or df_b.empty: return None

    return {
        "diferencial": comparar_abundancias(df_a, df_b, nivel=nivel).to_dict(orient="records"),
        "beta": DiversityService.calcular_diversidad_beta(df_a, df_b, nivel=nivel), # CORRECCIÓN
    }