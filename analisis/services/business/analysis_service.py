import pandas as pd
from django.db.models import F, Sum
from analisis.models import ResultadoTaxonomico, CatalogoMicroorganismo, VariedadClon, MuestraSuelo
from analisis.services.processing.diversity import DiversityService
from analisis.services.processing.abundance import comparar_abundancias
from analisis.constants import MARCADORES_VALIDOS, NIVELES_VALIDOS, MAPA_NIVELES, OPCIONES_TOP_N, get_taxonomia_annotation, clasificar_taxon, NIVEL_ALIASES, normalizar_nombre_catalogo


def _filtrar_catalogo_por_nivel(qs, nivel: str):
    """
    Aplica el filtro de nivel al queryset de CatalogoMicroorganismo aceptando
    tanto nombres en inglés ('species') como en español ('especie', 'género', etc.).
    Si ningún alias devuelve resultados hace fallback al queryset sin filtro.
    """
    from django.db.models import Q
    aliases = NIVEL_ALIASES.get(nivel, [nivel])
    q = Q()
    for alias in aliases:
        q |= Q(nivel__iexact=alias)
    qs_nivel = qs.filter(q)
    return qs_nivel if qs_nivel.exists() else qs


def obtener_lookup_catalogo(tipo, nivel=None):
    """
    Dict {nombre_normalizado: clasificacion}.
    Normaliza nombres del catálogo (elimina accesiones GenBank, _ → espacio) para
    que coincidan con los nombres limpios que produce el pipeline de importación.
    Filtra por marcador y nivel (acepta español e inglés); fallback a solo marcador.
    """
    qs = CatalogoMicroorganismo.objects.filter(marcador=tipo)
    if nivel:
        qs = _filtrar_catalogo_por_nivel(qs, nivel)
    return {
        normalizar_nombre_catalogo(obj.nombre): obj.clasificacion
        for obj in qs
    }


def _base_queryset(tipo, variedad_id=None, muestra_id=None, muestra_ids=None):
    qs = ResultadoTaxonomico.objects.filter(
        archivo__tipo_analisis=tipo
    ).select_related("archivo__muestra__variedad_clon")
    if variedad_id:
        qs = qs.filter(archivo__muestra__variedad_clon_id=variedad_id)
    if muestra_ids:
        qs = qs.filter(archivo__muestra_id__in=muestra_ids)
    elif muestra_id:
        qs = qs.filter(archivo__muestra_id=muestra_id)
    return qs

def obtener_analisis_avanzado(tipo="16S", top_n=10, nivel="genus", variedad_id=None, muestra_id=None, muestra_ids=None):
    """
    Perfil taxonómico agregado para visualización.
    Usa la suma de num_hits para calcular abundancia relativa real entre muestras agrupadas.
    El Top N se aplica solo para la tabla resumen; los datos completos están en BD.
    """
    if tipo not in MARCADORES_VALIDOS: tipo = "16S"
    if nivel not in NIVELES_VALIDOS:   nivel = "genus"
    if top_n not in OPCIONES_TOP_N:    top_n = 10

    qs = _base_queryset(tipo, variedad_id, muestra_id, muestra_ids)

    if not qs.exists():
        return {"resumen": [], "tipo_actual": tipo, "nivel_actual": nivel, "top_actual": top_n}

    # Para species usa binomio completo (genus + species) para que coincida con el catálogo
    taxonomia_expr = get_taxonomia_annotation(nivel)
    todos_los_datos = list(
        qs.values(taxonomia=taxonomia_expr)
        .annotate(total_hits=Sum("num_hits"))
        .order_by("-total_hits")
    )

    if not todos_los_datos:
        return {"resumen": [], "tipo_actual": tipo, "nivel_actual": nivel, "top_actual": top_n}

    grand_total = sum(x["total_hits"] for x in todos_los_datos) or 1

    datos_top = todos_los_datos[:top_n]
    datos_resto = todos_los_datos[top_n:]

    catalogo_lookup = obtener_lookup_catalogo(tipo, nivel=nivel)

    for item in datos_top:
        item["total_porcentaje"] = round(item["total_hits"] / grand_total * 100, 5)
        item["clasificacion"] = clasificar_taxon(item["taxonomia"] or "", catalogo_lookup, nivel)

    if datos_resto:
        hits_resto = sum(x["total_hits"] for x in datos_resto)
        datos_top.append({
            "taxonomia":        "Otros microorganismos (< abundancia)",
            "total_hits":       hits_resto,
            "total_porcentaje": round(hits_resto / grand_total * 100, 5),
            "clasificacion":    "neutral",
        })

    return {
        "resumen":      datos_top,
        "tipo_actual":  tipo,
        "nivel_actual": nivel,
        "top_actual":   top_n,
    }

def obtener_top_n(tipo="16S", n=10, nivel="genus", variedad_id=None):
    if tipo not in MARCADORES_VALIDOS: tipo = "16S"
    if nivel not in NIVELES_VALIDOS:   nivel = "genus"
    if n not in OPCIONES_TOP_N:        n = 10

    qs = _base_queryset(tipo, variedad_id)

    if not qs.exists(): return []

    grand_total = qs.aggregate(t=Sum("num_hits"))["t"] or 1

    taxonomia_expr = get_taxonomia_annotation(nivel)
    data = list(
        qs.values(taxonomia=taxonomia_expr)
        .annotate(total_hits=Sum("num_hits"))
        .order_by("-total_hits")[:n]
    )

    catalogo_lookup = obtener_lookup_catalogo(tipo, nivel=nivel)

    for item in data:
        item["total_porcentaje"] = round(item["total_hits"] / grand_total * 100, 5)
        item["clasificacion"] = clasificar_taxon(item["taxonomia"] or "", catalogo_lookup, nivel)

    return data

def obtener_diversidad(tipo="16S", nivel="genus", variedad_id=None, muestra_id=None, muestra_ids=None):
    """
    Calcula diversidad alfa por muestra individual y devuelve el promedio.
    Agrega Sum(num_hits) por taxon×muestra al nivel elegido antes de calcular
    los índices, evitando que múltiples especies del mismo genus aparezcan
    como taxa distintos al operar con nivel superior a species.
    """
    if tipo not in MARCADORES_VALIDOS: tipo = "16S"

    qs = _base_queryset(tipo, variedad_id, muestra_id, muestra_ids)
    if not qs.exists(): return None

    taxonomia_expr = get_taxonomia_annotation(nivel)
    # Agrega hits por (taxonomia, muestra) — un registro por taxón al nivel elegido
    data = list(
        qs.values(taxonomia=taxonomia_expr, muestra_pk=F("archivo__muestra_id"))
        .annotate(hits=Sum("num_hits"))
    )
    if not data: return None

    df = pd.DataFrame(data)
    diversidades = []
    for _, grupo in df.groupby("muestra_pk"):
        total = grupo["hits"].sum() or 1
        df_m = pd.DataFrame({"%_hits": grupo["hits"] / total * 100})
        df_m = df_m[df_m["%_hits"] > 0]
        if not df_m.empty:
            diversidades.append(DiversityService.calcular_diversidad_alfa(df_m))

    if not diversidades: return None
    n = len(diversidades)
    return {
        "riqueza":       round(sum(d["riqueza"] for d in diversidades) / n, 0),
        "shannon":       round(sum(d["shannon"] for d in diversidades) / n, 4),
        "simpson":       round(sum(d["simpson"] for d in diversidades) / n, 4),
        "equitatividad": round(sum(d["equitatividad"] for d in diversidades) / n, 4),
        "n_muestras":    n,
    }

def obtener_diversidad_beta_inter(tipo="16S", nivel="genus", muestra_ids=None):
    """
    Beta diversidad inter-muestra: disimilitud promedio entre todos los pares.
    Devuelve Bray-Curtis promedio, Jaccard promedio, taxa del core (presentes en
    TODAS las muestras) y taxa únicos (presentes en solo 1 muestra).
    Requiere ≥ 2 muestras con datos.
    """
    from scipy.spatial.distance import braycurtis
    from itertools import combinations
    import numpy as np

    if not muestra_ids or len(muestra_ids) < 2:
        return None

    taxonomia_expr = get_taxonomia_annotation(nivel)
    abundancias: dict = {}
    for mid in muestra_ids:
        data = list(
            ResultadoTaxonomico.objects
            .filter(archivo__tipo_analisis=tipo, archivo__muestra_id=mid)
            .values(t=taxonomia_expr)
            .annotate(h=Sum("num_hits"))
        )
        vec = {row["t"]: row["h"] for row in data if row["t"]}
        if vec:
            abundancias[mid] = vec

    if len(abundancias) < 2:
        return None

    all_taxa = sorted({t for v in abundancias.values() for t in v})
    ids_ok = list(abundancias.keys())

    matrix = np.array(
        [[abundancias[mid].get(t, 0) for t in all_taxa] for mid in ids_ok],
        dtype=float,
    )
    row_sums = matrix.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1
    matrix /= row_sums

    presencia = (matrix > 0).astype(float)

    bc_vals, jac_vals = [], []
    for i, j in combinations(range(len(ids_ok)), 2):
        bc_vals.append(float(braycurtis(matrix[i], matrix[j])))
        inter = float(np.sum(presencia[i] * presencia[j]))
        union = float(np.sum(np.clip(presencia[i] + presencia[j], 0, 1)))
        jac_vals.append(inter / union if union > 0 else 0.0)

    bc_prom  = round(float(np.mean(bc_vals)),  4) if bc_vals  else 0.0
    jac_prom = round(float(np.mean(jac_vals)), 4) if jac_vals else 0.0

    n_muestras_por_taxon = presencia.sum(axis=0)
    n_core   = int(np.sum(n_muestras_por_taxon == len(ids_ok)))
    n_unicos = int(np.sum(n_muestras_por_taxon == 1))

    if bc_prom >= 0.6:
        interp = "Alta disimilitud — las muestras tienen composiciones muy diferentes entre sí."
    elif bc_prom >= 0.3:
        interp = "Disimilitud moderada — las muestras comparten parte de su microbioma."
    else:
        interp = "Baja disimilitud — las muestras tienen comunidades microbianas similares."

    return {
        "bc_promedio":    bc_prom,
        "jaccard_promedio": jac_prom,
        "n_pares":        len(bc_vals),
        "n_taxa_total":   len(all_taxa),
        "n_core":         n_core,
        "n_unicos":       n_unicos,
        "n_muestras":     len(ids_ok),
        "interpretacion": interp,
    }


def obtener_diversidad_gamma(tipo="16S", nivel="genus", muestra_ids=None):
    """
    Diversidad gamma: combina todas las muestras en una metacomunidad y
    calcula Shannon, Simpson y riqueza total.
    """
    if not muestra_ids:
        return None
    qs = _base_queryset(tipo, muestra_ids=muestra_ids)
    if not qs.exists():
        return None

    taxonomia_expr = get_taxonomia_annotation(nivel)
    pooled = list(
        qs.values(tax=taxonomia_expr)
        .annotate(total=Sum("num_hits"))
        .order_by("-total")
    )
    if not pooled:
        return None

    grand_total = sum(p["total"] for p in pooled) or 1
    df_gamma = pd.DataFrame({"%_hits": [p["total"] / grand_total * 100 for p in pooled]})
    resultado = DiversityService.calcular_diversidad_gamma(df_gamma)
    resultado["n_muestras"] = len(muestra_ids)
    return resultado


def obtener_permanova(tipo="16S", nivel="genus", muestra_ids=None, n_perm=499):
    """
    PERMANOVA: prueba si la composición microbiana difiere significativamente
    entre cultivos. Si todas las muestras son del mismo cultivo, intenta
    agrupar por variedad/clon.
    """
    from scipy.spatial.distance import braycurtis
    import numpy as np
    from analisis.models import MuestraSuelo

    if not muestra_ids or len(muestra_ids) < 2:
        return None

    muestras = list(
        MuestraSuelo.objects.filter(id__in=muestra_ids)
        .select_related("cultivo", "variedad_clon")
    )
    if not muestras:
        return None

    # Grupos por cultivo
    mapa_cultivo  = {m.id: (m.cultivo.nombre  if m.cultivo       else "Sin cultivo")  for m in muestras}
    mapa_variedad = {m.id: (m.variedad_clon.nombre if m.variedad_clon else "Sin variedad") for m in muestras}

    if len(set(mapa_cultivo.values())) >= 2:
        mapa_grupo      = mapa_cultivo
        nivel_agrupacion = "cultivo"
    else:
        mapa_grupo      = mapa_variedad
        nivel_agrupacion = "variedad/clon"

    # Vector de abundancias por muestra
    taxonomia_expr = get_taxonomia_annotation(nivel)
    abundancias: dict = {}
    for mid in muestra_ids:
        qs = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo,
            archivo__muestra_id=mid,
        )
        if not qs.exists():
            continue
        data = list(qs.values(t=taxonomia_expr).annotate(h=Sum("num_hits")))
        abundancias[mid] = {row["t"]: row["h"] for row in data if row["t"]}

    if len(abundancias) < 2:
        return None

    all_taxa = sorted({t for v in abundancias.values() for t in v})
    if not all_taxa:
        return None

    ids_ok = list(abundancias.keys())
    matrix = np.array(
        [[abundancias[mid].get(t, 0) for t in all_taxa] for mid in ids_ok],
        dtype=float,
    )
    row_sums = matrix.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1
    matrix /= row_sums

    n = len(ids_ok)
    dist_mat = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = braycurtis(matrix[i], matrix[j])
            dist_mat[i, j] = dist_mat[j, i] = d

    grupos   = [mapa_grupo[mid] for mid in ids_ok]
    resultado = DiversityService.calcular_permanova(dist_mat, grupos, n_permutaciones=n_perm)
    if resultado:
        resultado["nivel_agrupacion"]    = nivel_agrupacion
        resultado["muestras_con_datos"]  = n
    return resultado


def obtener_analisis_diferencial(tipo="16S", nivel="genus", variedad_id=None, muestra_id=None):
    """
    Compara un conjunto A (la muestra o variedad seleccionada) contra un
    conjunto B: TODAS las demás muestras del mismo cultivo, agrupadas en un
    solo perfil agregado (no una segunda muestra individual). Sirve para ver
    si la muestra elegida es "típica" del cultivo o si se aparta de lo que
    normalmente se encuentra en él (taxa exclusivos, similitud de Jaccard).
    """
    if tipo not in MARCADORES_VALIDOS: tipo = "16S"

    etiqueta_a = None
    if variedad_id:
        try:
            variedad_origen = VariedadClon.objects.get(id=variedad_id)
            cultivo_id = variedad_origen.cultivo_id
            cultivo_nombre = variedad_origen.cultivo.nombre
            etiqueta_a = f"Variedad {variedad_origen.nombre}"
        except VariedadClon.DoesNotExist:
            return None
    elif muestra_id:
        try:
            qs_m = ResultadoTaxonomico.objects.filter(archivo__muestra_id=muestra_id).first()
            if not qs_m: return None
            muestra_origen = qs_m.archivo.muestra
            cultivo_id = muestra_origen.cultivo_id
            cultivo_nombre = muestra_origen.cultivo.nombre
            etiqueta_a = muestra_origen.codigo
        except Exception:
            return None
    else:
        return None

    qs_a = _base_queryset(tipo, variedad_id, muestra_id)
    qs_b = ResultadoTaxonomico.objects.filter(archivo__tipo_analisis=tipo, archivo__muestra__cultivo_id=cultivo_id)
    if variedad_id:
        qs_b = qs_b.exclude(archivo__muestra__variedad_clon_id=variedad_id)
    elif muestra_id:
        qs_b = qs_b.exclude(archivo__muestra_id=muestra_id)

    if not qs_a.exists() or not qs_b.exists(): return None

    n_muestras_b = qs_b.values("archivo__muestra_id").distinct().count()

    taxonomia_expr = get_taxonomia_annotation(nivel)

    def _preparar_df(qs):
        data = list(qs.values(tax=taxonomia_expr, p=F("num_hits")))
        df = pd.DataFrame(data)
        if df.empty: return pd.DataFrame(columns=[nivel, "%_hits"])
        agg = df.groupby("tax", as_index=False).agg({"p": "sum"})
        total = agg["p"].sum() or 1
        agg["%_hits"] = agg["p"] / total * 100
        return agg.rename(columns={"tax": nivel}).drop(columns=["p"])

    df_a = _preparar_df(qs_a)
    df_b = _preparar_df(qs_b)

    if df_a.empty or df_b.empty: return None

    return {
        "diferencial": comparar_abundancias(df_a, df_b, nivel=nivel),
        "beta": DiversityService.calcular_diversidad_beta(df_a, df_b, nivel=nivel), # CORRECCIÓN
        # Metadatos solo descriptivos (para la interfaz) — no participan en
        # ningún cálculo anterior ni lo modifican.
        "etiqueta_a": etiqueta_a,
        "cultivo_nombre": cultivo_nombre,
        "n_muestras_b": n_muestras_b,
    }