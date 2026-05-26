import pandas as pd
from django.db.models import F, Sum
from analisis.models import MuestraSuelo, ResultadoTaxonomico, CatalogoMicroorganismo

NIVELES_VALIDOS    = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
MARCADORES_VALIDOS = ("16S", "ITS")
MAPA_NIVELES = {
    "kingdom": "kingdom", "phylum": "phylum", "class": "tax_class",
    "order": "order", "family": "family", "genus": "genus", "species": "species"
}


def _get_clasificacion(nombre, nivel):
    """Cruza con CatalogoMicroorganismo para obtener clasificacion funcional."""
    ref = CatalogoMicroorganismo.objects.filter(
        nombre__iexact=nombre, nivel__iexact=nivel
    ).first()
    return ref.clasificacion if ref else "sin_clasificar"


def comparar_productos(analisis_filtrado, nivel="genus"):
    """
    Convierte el queryset en tabla dinámica pivoteada por muestra.
    README: "Análisis Comparativo → tablas dinámicas"
    """
    if not analisis_filtrado.exists():
        return []

    campo_db = MAPA_NIVELES.get(nivel, "genus")

    data = []
    for a in analisis_filtrado:
        nombre_tax = getattr(a, campo_db, "") or "Unclassified"
        data.append({
            "muestra":       a.archivo.muestra.codigo,
            "taxonomia":     nombre_tax,
            "%_hits":        float(a.porcentaje_hits or 0),
            "clasificacion": _get_clasificacion(nombre_tax, nivel),
        })

    df = pd.DataFrame(data)

    clasificacion_map = (
        df.groupby("taxonomia")["clasificacion"]
        .agg(lambda x: x.mode()[0])
        .to_dict()
    )

    tabla_df = df.pivot_table(
        index="taxonomia", columns="muestra",
        values="%_hits", fill_value=0,
    ).reset_index()

    columnas_num = [c for c in tabla_df.columns if c != "taxonomia"]
    tabla_df["total"] = tabla_df[columnas_num].sum(axis=1)
    tabla_df = tabla_df.sort_values("total", ascending=False).drop(columns=["total"])
    tabla_df["clasificacion"] = tabla_df["taxonomia"].map(clasificacion_map).fillna("sin_clasificar")

    return tabla_df.to_dict(orient="records")


def _calcular_diferencial(sets_por_muestra):
    """Calcula Dominantes, Compartidos y Exclusivos."""
    if not sets_por_muestra:
        return [], [], []

    todos = list(sets_por_muestra.values())
    n = len(todos)

    compartidos = sorted(set.intersection(*todos)) if n > 1 else []
    exclusivos  = []
    for mid, taxa in sets_por_muestra.items():
        otros_list = [s for p, s in sets_por_muestra.items() if p != mid]
        otros = set.union(*otros_list) if otros_list else set()
        exclusivos += sorted(taxa - otros)

    union_total = set.union(*todos) if todos else set()
    dominantes  = sorted(t for t in union_total if sum(1 for s in todos if t in s) > n / 2)

    return dominantes, compartidos, exclusivos


def ejecutar_comparacion_clean(cleaned_data):
    """
    Servicio principal de comparación entre muestras/variedades.
    README: "Análisis Diferencial: Dominantes, Compartidos y Exclusivos"
    """
    tipo       = cleaned_data.get("tipo", "16S")
    nivel      = cleaned_data.get("nivel", "genus")
    top_n      = int(cleaned_data.get("top_n") or 10)
    muestras_sel = cleaned_data.get("productos", [])

    if tipo not in MARCADORES_VALIDOS: tipo = "16S"
    if nivel not in NIVELES_VALIDOS:   nivel = "genus"
    
    # Validate top_n
    opciones_top_n = [5, 10, 25, 50]
    if top_n not in opciones_top_n:
        top_n = 10

    campo_db   = MAPA_NIVELES.get(nivel, "genus")
    ids        = [m.id for m in muestras_sel] if muestras_sel else []
    muestras_base = MuestraSuelo.objects.filter(
        archivomolecular__tipo_analisis=tipo
    ).distinct().order_by("-id")

    vacio = {
        "tabla": [], "dominantes": [], "compartidos": [], "exclusivos": [],
        "productos": muestras_base, "tipo_actual": tipo,
        "nivel_actual": nivel, "top_actual": top_n,
    }

    if not ids:
        return vacio

    analisis = ResultadoTaxonomico.objects.filter(
        archivo__tipo_analisis=tipo,
        archivo__muestra_id__in=ids,
    ).select_related("archivo__muestra")

    if not analisis.exists():
        return vacio

    # Top N por abundancia total
    df_hits = pd.DataFrame(list(
        analisis.values(tax=F(campo_db)).annotate(total=Sum("porcentaje_hits"))
    ))
    taxa_top = (
        df_hits.groupby("tax")["total"].sum()
        .sort_values(ascending=False)
        .head(top_n).index.tolist()
    )

    analisis_final = analisis.filter(**{f"{campo_db}__in": taxa_top})
    tabla = comparar_productos(analisis_final, nivel)

    sets = {
        mid: set(analisis.filter(archivo__muestra_id=mid).values_list(campo_db, flat=True))
        for mid in ids
    }
    dominantes, compartidos, exclusivos = _calcular_diferencial(sets)

    return {
        "tabla": tabla, "dominantes": dominantes,
        "compartidos": compartidos, "exclusivos": exclusivos,
        "productos": muestras_base, "tipo_actual": tipo,
        "nivel_actual": nivel, "top_actual": top_n,
    }


def obtener_microorganismos_compartidos(tipo="16S", variedad_id=None):
    """README: Compartidos (Core). Importado por views/analisis.py."""
    qs = ResultadoTaxonomico.objects.filter(archivo__tipo_analisis=tipo)
    if variedad_id:
        qs = qs.filter(archivo__muestra__variedad_clon_id=variedad_id)

    ids = list(qs.values_list("archivo__muestra_id", flat=True).distinct())
    if len(ids) < 2:
        return []

    sets = {mid: set(qs.filter(archivo__muestra_id=mid).values_list("genus", flat=True)) for mid in ids}
    return sorted(set.intersection(*sets.values()))


def obtener_microorganismos_exclusivos(tipo="16S", variedad_id=None):
    """README: Exclusivos. Importado por views/analisis.py."""
    if not variedad_id:
        return []

    qs = ResultadoTaxonomico.objects.filter(archivo__tipo_analisis=tipo)
    taxa_var   = set(qs.filter(archivo__muestra__variedad_clon_id=variedad_id).values_list("genus", flat=True))
    taxa_otros = set(qs.exclude(archivo__muestra__variedad_clon_id=variedad_id).values_list("genus", flat=True))
    return sorted(taxa_var - taxa_otros)