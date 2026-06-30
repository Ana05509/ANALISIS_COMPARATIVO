import pandas as pd
from django.db.models import F, Sum, Avg
from analisis.models import ResultadoTaxonomico, CatalogoMicroorganismo, VariedadClon
from analisis.services.processing.diversity import DiversityService
from analisis.services.processing.abundance import comparar_abundancias
from analisis.constants import MARCADORES_VALIDOS, NIVELES_VALIDOS, MAPA_NIVELES, OPCIONES_TOP_N


def obtener_lookup_catalogo(tipo):
    """Dict {nombre.lower(): clasificacion} para todos los microorganismos del marcador."""
    return {
        obj.nombre.lower(): obj.clasificacion
        for obj in CatalogoMicroorganismo.objects.filter(marcador=tipo)
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

    campo_db = MAPA_NIVELES[nivel]
    qs = _base_queryset(tipo, variedad_id, muestra_id, muestra_ids)

    if not qs.exists():
        return {"resumen": [], "tipo_actual": tipo, "nivel_actual": nivel, "top_actual": top_n}

    # Suma de hits por taxón — clave 'taxonomia' uniforme para todos los templates
    todos_los_datos = list(
        qs.values(taxonomia=F(campo_db))
        .annotate(total_hits=Sum("num_hits"))
        .order_by("-total_hits")
    )

    if not todos_los_datos:
        return {"resumen": [], "tipo_actual": tipo, "nivel_actual": nivel, "top_actual": top_n}

    grand_total = sum(x["total_hits"] for x in todos_los_datos) or 1

    datos_top = todos_los_datos[:top_n]
    datos_resto = todos_los_datos[top_n:]

    catalogo_lookup = obtener_lookup_catalogo(tipo)

    for item in datos_top:
        item["total_porcentaje"] = round(item["total_hits"] / grand_total * 100, 5)
        item["clasificacion"] = catalogo_lookup.get(
            (item["taxonomia"] or "").lower(), "sin_clasificar"
        )

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

    campo_db = MAPA_NIVELES[nivel]
    qs = _base_queryset(tipo, variedad_id)

    if not qs.exists(): return []

    grand_total = qs.aggregate(t=Sum("num_hits"))["t"] or 1

    data = list(
        qs.values(taxonomia=F(campo_db))
        .annotate(total_hits=Sum("num_hits"))
        .order_by("-total_hits")[:n]
    )

    catalogo_lookup = obtener_lookup_catalogo(tipo)

    for item in data:
        item["total_porcentaje"] = round(item["total_hits"] / grand_total * 100, 5)
        item["clasificacion"] = catalogo_lookup.get(
            (item["taxonomia"] or "").lower(), "sin_clasificar"
        )

    return data

def obtener_diversidad(tipo="16S", nivel="genus", variedad_id=None, muestra_id=None, muestra_ids=None):
    """
    Calcula diversidad alfa por muestra individual y devuelve el promedio.
    Evita el error de calcular Shannon/Simpson sobre un perfil promediado.
    """
    if tipo not in MARCADORES_VALIDOS: tipo = "16S"
    campo_db = MAPA_NIVELES.get(nivel, "genus")

    qs = _base_queryset(tipo, variedad_id, muestra_id, muestra_ids)
    if not qs.exists(): return None

    data = list(qs.values(
        taxonomia=F(campo_db),
        muestra_pk=F("archivo__muestra_id"),
        hits=F("porcentaje_hits"),
    ))
    if not data: return None

    df = pd.DataFrame(data)
    diversidades = []
    for _, grupo in df.groupby("muestra_pk"):
        df_m = grupo[["hits"]].rename(columns={"hits": "%_hits"})
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
    elif muestra_id:
        qs_b = qs_b.exclude(archivo__muestra_id=muestra_id)

    if not qs_a.exists() or not qs_b.exists(): return None

    def _preparar_df(qs):
        data = list(qs.values(tax=F(campo_db), p=F("num_hits")))
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
    }