import json
import pandas as pd
from django.db.models import F, Sum
from analisis.models import MuestraSuelo, ResultadoTaxonomico, VariedadClon
from analisis.constants import MARCADORES_VALIDOS, NIVELES_VALIDOS, MAPA_NIVELES, OPCIONES_TOP_N, get_taxonomia_annotation, clasificar_taxon
from analisis.services.business.analysis_service import obtener_lookup_catalogo


def comparar_productos(analisis_filtrado, nivel="genus", taxa_top=None, tipo="16S"):
    """
    Convierte el queryset en tabla dinámica pivoteada por muestra.
    Agrupa dinámicamente todo el residuo biológico fuera del Top N en la fila 'Otros'.
    """
    if not analisis_filtrado.exists():
        return []

    campo_db = MAPA_NIVELES.get(nivel, "genus")
    mapa_clasificacion = obtener_lookup_catalogo(tipo, nivel=nivel)

    data = []
    muestras_vistas = set()

    for a in analisis_filtrado:
        if nivel == "species":
            g = (a.genus or "").strip()
            s = (a.species or "").strip()
            if s.lower().startswith(g.lower()) and g:
                nombre_tax = s or "Unclassified"
            else:
                nombre_tax = f"{g} {s}".strip() or "Unclassified"
        else:
            nombre_tax = getattr(a, campo_db, "") or "Unclassified"
        codigo_muestra = a.archivo.muestra.codigo
        porcentaje = float(a.porcentaje_hits or 0)
        muestras_vistas.add(codigo_muestra)

        # Si definimos un Top N y el microorganismo actual no pertenece a él, pasa a 'Otros'
        if taxa_top is not None and nombre_tax not in taxa_top:
            data.append({
                "muestra": codigo_muestra,
                "taxonomia": "Otros microorganismos (< abundancia)",
                "%_hits": porcentaje,
                "clasificacion": "neutral"
            })
        else:
            data.append({
                "muestra": codigo_muestra,
                "taxonomia": nombre_tax,
                "%_hits": porcentaje,
                "clasificacion": clasificar_taxon(nombre_tax, mapa_clasificacion, nivel),
            })

    df = pd.DataFrame(data)
    if df.empty:
        return []

    # Agrupamos por si se sumaron múltiples registros en 'Otros' para una misma muestra
    df_agrupado = df.groupby(["taxonomia", "muestra", "clasificacion"], as_index=False)["%_hits"].sum()

    # Generación de la Tabla Dinámica (Pivot Table)
    tabla_df = df_agrupado.pivot_table(
        index=["taxonomia", "clasificacion"], 
        columns="muestra",
        values="%_hits", 
        fill_value=0
    ).reset_index()

    # Calcular columna total global temporal para ordenar las filas por dominancia analítica
    columnas_muestras = [c for c in tabla_df.columns if c not in ["taxonomia", "clasificacion"]]
    tabla_df["__total_sort"] = tabla_df[columnas_muestras].sum(axis=1)
    
    # Garantizar que 'Otros' quede fijo siempre al fondo de la tabla de resultados
    tabla_df["__is_otros"] = tabla_df["taxonomia"].apply(lambda x: 1 if "Otros microorganismos" in x else 0)
    
    tabla_df = tabla_df.sort_values(by=["__is_otros", "__total_sort"], ascending=[True, False]).drop(
        columns=["__total_sort", "__is_otros"]
    )

    # json.loads(to_json()) convierte numpy.float64 → Python float antes de devolver
    return json.loads(tabla_df.to_json(orient="records"))


def _calcular_diferencial(sets_por_muestra):
    """Calcula con lógica de conjuntos: Dominantes, Compartidos y Exclusivos."""
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
    # Dominantes: Microorganismos que aparecen en más del 50% de las muestras evaluadas
    dominantes  = sorted(t for t in union_total if sum(1 for s in todos if t in s) > n / 2)

    return dominantes, compartidos, exclusivos


def ejecutar_comparacion_clean(cleaned_data):
    """
    Servicio principal de comparación multidimensional.
    Procesa las muestras seleccionadas sin segmentar conjuntos de datos inválidos.
    """
    tipo         = cleaned_data.get("tipo", "16S")
    nivel        = cleaned_data.get("nivel", "genus")
    top_n        = int(cleaned_data.get("top_n") or 10)
    muestras_sel = cleaned_data.get("productos", [])

    if tipo not in MARCADORES_VALIDOS: tipo = "16S"
    if nivel not in NIVELES_VALIDOS:   nivel = "genus"
    if top_n not in OPCIONES_TOP_N:    top_n = 10

    campo_db = MAPA_NIVELES.get(nivel, "genus")
    ids = [m.id for m in muestras_sel] if muestras_sel else []
    
    muestras_base = MuestraSuelo.objects.filter(
        archivos_moleculares__tipo_analisis=tipo
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

    # Top N por suma de num_hits usando binomio completo para species
    taxonomia_expr = get_taxonomia_annotation(nivel)
    taxa_top = list(
        analisis.values(tax=taxonomia_expr)
        .annotate(total=Sum("num_hits"))
        .order_by("-total")
        .values_list("tax", flat=True)[:top_n]
    )

    # Enviamos la totalidad de los datos pero parametrizando el 'taxa_top' para consolidar la fila 'Otros'
    tabla = comparar_productos(analisis, nivel, taxa_top=taxa_top, tipo=tipo)

    sets = {
        mid: set(
            analisis.filter(archivo__muestra_id=mid)
            .annotate(_tax=taxonomia_expr)
            .values_list("_tax", flat=True)
        )
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
    """
    Calcula el Core Microbioma (intersección) restringiendo las muestras
    estrictamente al contexto de su propio cultivo agrícola.
    """
    if not variedad_id:
        return []
        
    try:
        cultivo_id = VariedadClon.objects.get(id=variedad_id).cultivo_id
    except VariedadClon.DoesNotExist:
        return []

    # Filtramos para que solo compare muestras del mismo cultivo biológico
    qs = ResultadoTaxonomico.objects.filter(
        archivo__tipo_analisis=tipo,
        archivo__muestra__cultivo_id=cultivo_id
    )

    ids = list(qs.values_list("archivo__muestra_id", flat=True).distinct())
    if len(ids) < 2:
        return []

    sets = {mid: set(qs.filter(archivo__muestra_id=mid).values_list("genus", flat=True).distinct()) for mid in ids}
    return sorted(set.intersection(*sets.values()))


def obtener_microorganismos_exclusivos(tipo="16S", variedad_id=None):
    """
    Calcula taxones exclusivos restando los del grupo de control
    dentro del mismo nicho ecológico de cultivo vegetal.
    """
    if not variedad_id:
        return []

    try:
        cultivo_id = VariedadClon.objects.get(id=variedad_id).cultivo_id
    except VariedadClon.DoesNotExist:
        return []

    qs_contexto = ResultadoTaxonomico.objects.filter(
        archivo__tipo_analisis=tipo,
        archivo__muestra__cultivo_id=cultivo_id
    )
    
    taxa_var   = set(qs_contexto.filter(archivo__muestra__variedad_clon_id=variedad_id).values_list("genus", flat=True).distinct())
    taxa_otros = set(qs_contexto.exclude(archivo__muestra__variedad_clon_id=variedad_id).values_list("genus", flat=True).distinct())
    
    return sorted(taxa_var - taxa_otros)