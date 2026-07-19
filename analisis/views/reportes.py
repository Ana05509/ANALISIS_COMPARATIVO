from collections import defaultdict
from datetime import datetime
import json

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import F, Sum
from django.http import JsonResponse, HttpResponse, HttpResponseBase
from django.views.decorators.http import require_POST

from analisis.models import MuestraSuelo, ResultadoTaxonomico, CatalogoMicroorganismo
from analisis.services.business.analysis_service import obtener_analisis_avanzado, obtener_diversidad, _filtrar_catalogo_por_nivel
from analisis.services.business.export_service import ExportService
from analisis.constants import MARCADORES_VALIDOS, OPCIONES_TOP_N, NIVELES_VALIDOS, MAPA_NIVELES, get_taxonomia_annotation, clasificar_taxon, buscar_en_catalogo, NIVELES_ES, MARCADORES_ES, NIVELES_CHOICES, MARCADORES_CHOICES, normalizar_nombre_catalogo

FORMATOS_VALIDOS = ("pdf", "excel")


# ── Helpers de cálculo ────────────────────────────────────────────────────────

def calcular_indice_salud(n_ben, n_fito, n_neu, n_sc, shannon=0):
    """Índice de Salud del Suelo (0-100). Devuelve (indice, nivel)."""
    total_func = n_ben + n_fito
    ratio      = n_ben / total_func if total_func > 0 else 0.5
    shan_norm  = min(float(shannon or 0) / 3.5, 1.0)
    indice     = max(0, min(100, round((ratio * 0.70 + shan_norm * 0.30) * 100)))
    if   indice >= 80: nivel = "ÓPTIMO"
    elif indice >= 65: nivel = "FAVORABLE"
    elif indice >= 50: nivel = "MODERADO"
    elif indice >= 30: nivel = "EN RIESGO"
    else:              nivel = "CRÍTICO"
    return indice, nivel


def _obtener_clasificacion_detalle(qs, nivel, campo_db, tipo="16S"):
    """
    Devuelve (detalle_dict, totales_dict) con info funcional de cada taxón.
    detalle_dict[cat] = [{nombre, porcentaje, descripcion, referencia}, ...]
    """
    CATS = ("benefico", "fitopatogeno", "neutral", "sin_clasificar")
    taxa_qs    = list(qs.values(taxon=get_taxonomia_annotation(nivel)).annotate(hits=Sum("num_hits")).order_by("-hits"))
    grand_total = sum(r["hits"] for r in taxa_qs) or 1

    catalogo = {
        normalizar_nombre_catalogo(obj.nombre): obj
        for obj in _filtrar_catalogo_por_nivel(
            CatalogoMicroorganismo.objects.filter(marcador=tipo), nivel
        )
    }

    detalle = {c: [] for c in CATS}
    totales = {c: 0  for c in CATS}
    for row in taxa_qs:
        nombre = row["taxon"] or "Desconocido"
        cat_obj = buscar_en_catalogo(nombre, catalogo, nivel)
        clas    = (cat_obj.clasificacion if cat_obj and cat_obj.clasificacion in CATS else "sin_clasificar")

        pct_raw = row["hits"] / grand_total * 100
        # Usar 4 decimales para que abundancias muy bajas no aparezcan como 0.00
        pct = round(pct_raw, 4) if pct_raw < 0.01 else round(pct_raw, 2)
        detalle[clas].append({
            "nombre":      nombre,
            "porcentaje":  pct,
            "descripcion": cat_obj.descripcion or "" if cat_obj else "",
            "referencia":  cat_obj.referencia  or "" if cat_obj else "",
        })
        totales[clas] += 1
    return detalle, totales


def _construir_datos_reporte(tipo, nivel, top_n, muestra_ids=None):
    """
    Construye el dict completo de datos para PDF / Excel.
    Retorna None si no hay datos.
    """
    campo_db = MAPA_NIVELES.get(nivel, "genus")
    qs = ResultadoTaxonomico.objects.filter(archivo__tipo_analisis=tipo)
    if muestra_ids:
        qs = qs.filter(archivo__muestra_id__in=muestra_ids)
    if not qs.exists():
        return None

    grand_total = qs.aggregate(total=Sum("num_hits"))["total"] or 1
    todos_raw   = list(qs.values(taxonomia=get_taxonomia_annotation(nivel)).annotate(total_hits=Sum("num_hits")).order_by("-total_hits"))

    catalogo_map = {
        normalizar_nombre_catalogo(obj["nombre"]): obj["clasificacion"]
        for obj in _filtrar_catalogo_por_nivel(
            CatalogoMicroorganismo.objects.filter(marcador=tipo), nivel
        ).values("nombre", "clasificacion")
    }
    for r in todos_raw:
        pct_raw = r["total_hits"] / grand_total * 100
        r["total_porcentaje"] = round(pct_raw, 4) if pct_raw < 0.01 else round(pct_raw, 2)
        r["clasificacion"]    = clasificar_taxon(str(r["taxonomia"] or ""), catalogo_map, nivel)

    diversidad  = obtener_diversidad(tipo=tipo, nivel=nivel, muestra_ids=muestra_ids) or {}
    detalle_clas, totales_clas = _obtener_clasificacion_detalle(qs, nivel, campo_db, tipo)
    shannon_val  = diversidad.get("shannon", 0) or 0
    indice, nivel_salud = calcular_indice_salud(
        totales_clas["benefico"], totales_clas["fitopatogeno"],
        totales_clas["neutral"],  totales_clas["sin_clasificar"],
        shannon=shannon_val,
    )

    # Agregación kingdom → phylum → <nivel actual>, para el gráfico Sunburst
    # del reporte Excel (Fase 1.2). No reemplaza ninguna consulta existente.
    jerarquia_taxonomica = list(
        qs.values("kingdom", "phylum", campo_db)
          .annotate(hits=Sum("num_hits"))
          .order_by("-hits")[:150]
    )

    return {
        "top_taxa":     todos_raw[:top_n],
        "todos_taxa":   todos_raw,
        "diversidad":   diversidad,
        "detalle_clas": detalle_clas,
        "totales_clas": totales_clas,
        "indice_salud": indice,
        "nivel_salud":  nivel_salud,
        "jerarquia_taxonomica": jerarquia_taxonomica,
        "nivel_campo_jerarquia": campo_db,
        "tipo": tipo, "nivel": nivel, "top_n": top_n,
    }


def _construir_datos_por_muestra(tipo, nivel, top_n, muestras_list):
    """Para reportes comparativos: datos por cada muestra seleccionada."""
    campo_db  = MAPA_NIVELES.get(nivel, "genus")
    EXCLUIR = {"others", "unclassified", "unknown", "others sp", "nan", ""}
    resultado = []
    for muestra in muestras_list:
        qs_m = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo, archivo__muestra_id=muestra.id
        )
        if not qs_m.exists():
            continue
        grand_total = qs_m.aggregate(total=Sum("num_hits"))["total"] or 1
        # Todos los taxa de esta muestra (para diversidad beta)
        all_raw = list(qs_m.values(taxonomia=get_taxonomia_annotation(nivel)).annotate(total_hits=Sum("num_hits")).order_by("-total_hits"))
        for r in all_raw:
            pct_raw = r["total_hits"] / grand_total * 100
            r["total_porcentaje"] = round(pct_raw, 4) if pct_raw < 0.01 else round(pct_raw, 2)
        top_raw = all_raw[:top_n]
        todos_taxa_nombres = {
            str(r["taxonomia"]) for r in all_raw
            if r.get("taxonomia") and str(r["taxonomia"]).lower() not in EXCLUIR
        }
        div_m = obtener_diversidad(tipo=tipo, nivel=nivel, muestra_ids=[muestra.id]) or {}
        detalle_m, totales_m = _obtener_clasificacion_detalle(qs_m, nivel, campo_db, tipo)
        indice_m, nivel_m = calcular_indice_salud(
            totales_m["benefico"], totales_m["fitopatogeno"],
            totales_m["neutral"],  totales_m["sin_clasificar"],
            shannon=div_m.get("shannon", 0) or 0,
        )
        resultado.append({
            "muestra":            muestra,
            "top_taxa":           top_raw,
            "todos_taxa":         all_raw,
            "todos_taxa_nombres": todos_taxa_nombres,
            "diversidad":         div_m,
            "detalle_clas":       detalle_m,
            "totales_clas":       totales_m,
            "indice_salud":       indice_m,
            "nivel_salud":        nivel_m,
        })
    return resultado


def _clasificacion_por_muestra(tipo, nivel, muestra_ids=None):
    """
    Devuelve lista de dicts {muestra, benefico, fitopatogeno, neutral, sin_clasificar,
    nombres_benefico, ...} filtrada por muestra_ids (o global si es None).
    """
    campo_db = MAPA_NIVELES.get(nivel, "genus")
    qs = ResultadoTaxonomico.objects.filter(archivo__tipo_analisis=tipo)
    if muestra_ids:
        qs = qs.filter(archivo__muestra_id__in=muestra_ids)

    data = list(qs.values(muestra=F("archivo__muestra__codigo"), taxon=get_taxonomia_annotation(nivel)).annotate(hits=Sum("num_hits")))
    if not data:
        return []

    catalog = {
        normalizar_nombre_catalogo(obj.nombre): obj.clasificacion
        for obj in _filtrar_catalogo_por_nivel(
            CatalogoMicroorganismo.objects.filter(marcador=tipo), nivel
        )
    }
    CATS    = ("benefico", "fitopatogeno", "neutral", "sin_clasificar")
    acc     = defaultdict(lambda: {c: [] for c in CATS})

    for row in data:
        m      = row["muestra"] or "Sin código"
        nombre = row["taxon"]   or "Desconocido"
        clas   = clasificar_taxon(nombre, catalog, nivel)
        if nombre not in acc[m][clas]:
            acc[m][clas].append(nombre)

    return [
        {"muestra": m, **{c: len(listas[c]) for c in CATS}, **{f"nombres_{c}": sorted(listas[c]) for c in CATS}}
        for m, listas in sorted(acc.items())
    ]


# ── Vistas ────────────────────────────────────────────────────────────────────

@login_required
def reportes(request):
    tipo  = request.GET.get("tipo",  "16S")  if request.GET.get("tipo",  "16S")  in MARCADORES_VALIDOS else "16S"
    nivel = request.GET.get("nivel", "genus") if request.GET.get("nivel", "genus") in NIVELES_VALIDOS    else "genus"
    try:
        top_n = int(request.GET.get("top_n", 25))
        top_n = top_n if top_n in OPCIONES_TOP_N else 25
    except (ValueError, TypeError):
        top_n = 25

    muestra_ids = [int(x) for x in request.GET.getlist("muestra_id") if x.isdigit()]

    # Contexto base (defaults vacíos si falla algo)
    ctx = {
        "tipo_actual":             tipo,
        "nivel_actual":            nivel,
        "top_n_actual":            top_n,
        "opciones_top_n":          OPCIONES_TOP_N,
        "marcadores_choices":      MARCADORES_CHOICES,
        "niveles_choices":         NIVELES_CHOICES,
        "nivel_actual_label":      NIVELES_ES.get(nivel, nivel.capitalize()),
        "muestra_ids_seleccionados": muestra_ids,
        "productos": MuestraSuelo.objects.filter(
            archivos_moleculares__tipo_analisis=tipo
        ).distinct().order_by("codigo"),
        "resumen":                 [],
        "diversidad":              {},
        "datos_clasificacion":     [],
        "datos_clasificacion_json": "[]",
        "totales_clasificacion":   {"benefico": 0, "fitopatogeno": 0, "neutral": 0, "sin_clasificar": 0},
        "indice_salud":            None,
        "nivel_salud":             None,
        "alfa_por_muestra":        {},
    }

    # Solo cargar datos si el usuario seleccionó al menos una muestra
    if muestra_ids:
        try:
            # ① Tabla Top N
            resultado      = obtener_analisis_avanzado(tipo=tipo, top_n=top_n, nivel=nivel, muestra_ids=muestra_ids)
            ctx["resumen"] = resultado.get("resumen", [])
            ctx["resumen_json"] = json.dumps([
                {
                    "nombre":        str(r.get("taxonomia") or "Desconocido"),
                    "porcentaje":    float(r.get("total_porcentaje") or 0),
                    "hits":          int(r.get("total_hits") or 0),
                    "clasificacion": str(r.get("clasificacion") or "sin_clasificar"),
                }
                for r in ctx["resumen"]
            ])

            # ② Diversidad Alfa (promedio del set; incluye simpson y equitatividad)
            ctx["diversidad"] = obtener_diversidad(tipo=tipo, nivel=nivel, muestra_ids=muestra_ids) or {}

            # ③ Gráfica de tendencia clasificación por muestra
            datos_clas                      = _clasificacion_por_muestra(tipo, nivel, muestra_ids=muestra_ids)
            ctx["datos_clasificacion"]      = datos_clas
            ctx["datos_clasificacion_json"] = json.dumps(datos_clas)

            # ④ Índice de salud + totales funcionales
            datos_rpt = _construir_datos_reporte(tipo, nivel, top_n, muestra_ids)
            if datos_rpt:
                ctx["indice_salud"]          = datos_rpt["indice_salud"]
                ctx["nivel_salud"]           = datos_rpt["nivel_salud"]
                ctx["totales_clasificacion"] = datos_rpt["totales_clas"]

            # ⑤ Alpha diversidad individual por muestra (para gráfico Shannon multi-muestra)
            if len(muestra_ids) > 1:
                muestras_set = MuestraSuelo.objects.filter(
                    id__in=muestra_ids
                ).only("id", "codigo").order_by("codigo")
                alfa_pm = {}
                for m in muestras_set:
                    div_m = obtener_diversidad(tipo=tipo, nivel=nivel, muestra_ids=[m.id]) or {}
                    if div_m:
                        alfa_pm[m.codigo] = {
                            "riqueza":       int(div_m.get("riqueza", 0)),
                            "shannon":       round(float(div_m.get("shannon", 0)), 4),
                            "simpson":       round(float(div_m.get("simpson", 0)), 4),
                            "equitatividad": round(float(div_m.get("equitatividad", 0)), 4),
                        }
                ctx["alfa_por_muestra"] = alfa_pm

        except Exception as exc:
            import traceback; traceback.print_exc()
            messages.error(request, f"Error al cargar el reporte: {exc}")

    return render(request, "analisis/reportes.html", ctx)


@login_required
@require_POST
def generar_reporte(request) -> HttpResponseBase:
    tipo  = request.POST.get("tipo",  "16S")
    nivel = request.POST.get("nivel", "genus")
    if tipo  not in MARCADORES_VALIDOS: tipo  = "16S"
    if nivel not in NIVELES_VALIDOS:    nivel = "genus"

    formato = request.POST.get("formato", "excel")
    if formato not in FORMATOS_VALIDOS:
        return JsonResponse({"ok": False, "error": "Formato no soportado."}, status=400)

    try:
        top_n = int(request.POST.get("top_n", 25))
        top_n = top_n if top_n in OPCIONES_TOP_N else 25
    except (ValueError, TypeError):
        top_n = 25

    muestra_ids = [int(x) for x in request.POST.getlist("muestra_id") if x.isdigit()]
    ids_param   = muestra_ids if muestra_ids else None

    try:
        datos_rpt = _construir_datos_reporte(tipo, nivel, top_n, ids_param)
        if not datos_rpt:
            return JsonResponse({"ok": False, "error": "No hay datos para el reporte seleccionado."}, status=404)

        # Muestras correspondientes
        muestras_qs = MuestraSuelo.objects.select_related("cultivo", "variedad_clon").filter(
            archivos_moleculares__tipo_analisis=tipo
        ).distinct()
        if muestra_ids:
            muestras_qs = muestras_qs.filter(id__in=muestra_ids)
        muestras_list = list(muestras_qs.order_by("codigo"))

        fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
        datos = {
            **datos_rpt,
            "muestras": muestras_list,
            "muestra":  muestras_list[0] if len(muestras_list) == 1 else None,
            "usuario":  request.user,
        }

        if formato == "excel":
            # Datos adicionales que el PDF no necesita pero el Excel sí
            if len(muestras_list) > 1:
                datos["datos_por_muestra"] = _construir_datos_por_muestra(
                    tipo, nivel, top_n, muestras_list
                )
            elif muestras_list:
                # Análisis diferencial solo para muestra individual
                try:
                    from analisis.services.business.analysis_service import obtener_analisis_diferencial
                    diff = obtener_analisis_diferencial(
                        tipo=tipo, nivel=nivel, muestra_id=muestras_list[0].id
                    )
                    if diff:
                        datos["analisis_diferencial"] = diff
                except Exception:
                    pass
            return ExportService.generar_excel_multisheet(datos)

        # PDF — individual si 0-1 muestras, comparativo si 2+
        if len(muestras_list) > 1:
            datos["datos_por_muestra"] = _construir_datos_por_muestra(tipo, nivel, top_n, muestras_list)
            pdf_bytes = ExportService.generar_pdf_comparativo(datos)
            nombre    = f"reporte_comparativo_{tipo}_{nivel}_{fecha}.pdf"
        else:
            pdf_bytes = ExportService.generar_pdf_individual(datos)
            codigo    = muestras_list[0].codigo if muestras_list else "global"
            nombre    = f"reporte_{tipo}_{nivel}_{codigo}_{fecha}.pdf"

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return response

    except Exception as exc:
        import traceback; traceback.print_exc()
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)


@login_required
def detalle_reporte(request, reporte_id):
    """Placeholder — redirige al listado hasta que se implemente la vista de detalle."""
    messages.info(request, "Vista de detalle pendiente de implementación.")
    return redirect("analisis:reportes")
