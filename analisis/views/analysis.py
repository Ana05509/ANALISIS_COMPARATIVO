from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import F, Sum
import json
import pandas as pd

from ..services.business.analysis_service import (
    obtener_analisis_avanzado,
    obtener_analisis_diferencial,
    obtener_diversidad,
)
from ..services.business.visualization_service import VisualizationService
from ..models import ResultadoTaxonomico, MuestraSuelo, ArchivoMolecular
from analisis.constants import OPCIONES_TOP_N, NIVELES_VALIDOS, MAPA_NIVELES, NIVELES_ES, NIVELES_CHOICES, MARCADORES_CHOICES

@login_required
def analisis_avanzado(request):
    tipo = request.GET.get("tipo", "16S")
    top_n_raw = request.GET.get("top_n", "10")
    nivel = request.GET.get("nivel", "genus")

    # Acepta lista de muestra_id (multi-select) o producto_id (link desde detalle_producto)
    ids_raw = request.GET.getlist("muestra_id") or ([request.GET.get("producto_id")] if request.GET.get("producto_id") else [])
    muestra_ids = []
    for raw in ids_raw:
        try:
            muestra_ids.append(int(raw))
        except (ValueError, TypeError):
            pass

    try:
        top_n = int(top_n_raw) if int(top_n_raw) in OPCIONES_TOP_N else 10
    except ValueError:
        top_n = 10

    muestras = MuestraSuelo.objects.select_related(
        "cultivo", "variedad_clon"
    ).prefetch_related("archivos_moleculares").order_by("cultivo__nombre", "codigo")

    # Construye {muestra_id: ["16S", "ITS"]} para el filtro JS del panel multi-select.
    # Una muestra puede tener AMBOS tipos de archivo, por eso no usamos .first()
    _tipos_raw: dict = {}
    for mid, t in ArchivoMolecular.objects.values_list("muestra_id", "tipo_analisis").distinct():
        _tipos_raw.setdefault(mid, []).append(t)
    tipos_por_muestra_json = json.dumps(_tipos_raw)

    contexto = {
        "top_microorganismos": [],
        "top_microorganismos_json": "[]",
        "diversidad": {},
        "graficos_avanzados": {},
        "graficos_avanzados_json": "{}",
        "analisis_diferencial": None,
        "muestras": muestras,
        "muestra_ids_seleccionados": muestra_ids,
        "sin_muestra": len(muestra_ids) == 0,
    }

    if not muestra_ids:
        contexto.update({
            "tipo_actual": tipo,
            "top_n_actual": top_n,
            "nivel_actual": nivel,
            "nivel_actual_label": NIVELES_ES.get(nivel, nivel.capitalize()),
            "opciones_top_n": OPCIONES_TOP_N,
            "niveles_choices": NIVELES_CHOICES,
            "marcadores_choices": MARCADORES_CHOICES,
            "tipos_por_muestra_json": tipos_por_muestra_json,
        })
        return render(request, "analisis/analisis_avanzado.html", contexto)

    try:
        # Obtener el análisis avanzado básico (tabla de Top N para visualización)
        resultado = obtener_analisis_avanzado(
            tipo=tipo, top_n=top_n, nivel=nivel, muestra_ids=muestra_ids
        )

        if "resumen" in resultado and resultado["resumen"]:
            contexto["top_microorganismos"] = resultado["resumen"]
            contexto["top_microorganismos_json"] = json.dumps(resultado["resumen"])

        # Diversidad alfa promedio sobre las muestras seleccionadas
        diversidad = obtener_diversidad(tipo=tipo, nivel=nivel, muestra_ids=muestra_ids)
        if diversidad:
            contexto["diversidad"] = diversidad

        # Nota: diversidad beta/gamma y PERMANOVA (estadísticas inherentemente
        # multi-muestra) viven solo en "Comparar Perfiles", que ya exige ≥2
        # muestras para ese propósito — evita mostrar el mismo cálculo dos veces.

        # --- GRÁFICAS AVANZADAS ---
        qs = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo,
            archivo__muestra_id__in=muestra_ids,
        )

        if qs.exists():
            campo_modelo = MAPA_NIVELES.get(nivel, 'genus')

            # Agrega Sum(num_hits) por (taxon, muestra) al nivel elegido — evita
            # que múltiples especies del mismo genus aparezcan como filas separadas
            from analisis.constants import get_taxonomia_annotation as _get_tax_ann
            taxonomia_expr_viz = _get_tax_ann(nivel)
            data_agg = list(
                qs.values(taxon=taxonomia_expr_viz, muestra=F('archivo__muestra__codigo'))
                .annotate(abundancia=Sum('num_hits'))
            )
            if data_agg:
                df_raw = pd.DataFrame(data_agg)
                df_raw = df_raw[df_raw['taxon'].notna() & (df_raw['taxon'] != '')]

                # Orden "Top N" por hits acumulados (pooled), calculado ANTES de
                # normalizar por muestra — el MISMO criterio que usa la tabla de
                # arriba (obtener_analisis_avanzado, que ordena por Sum(num_hits)
                # agrupado). Se pasa explícitamente a las gráficas para que
                # muestren los mismos Top N taxa que la tabla, en vez de que cada
                # una calcule su propio orden con un criterio distinto.
                orden_taxa_pooled = (
                    df_raw.groupby('taxon')['abundancia'].sum()
                    .sort_values(ascending=False)
                    .index.tolist()
                )

                # Normaliza a abundancia relativa por muestra antes del pivot
                totales = df_raw.groupby('muestra')['abundancia'].transform('sum')
                df_raw['abundancia'] = df_raw['abundancia'] / totales.replace(0, 1) * 100

                # Pivote completo — 1 fila por taxon, 1 col por muestra
                df_pivot_full = df_raw.pivot_table(
                    index='taxon', columns='muestra', values='abundancia',
                    fill_value=0, aggfunc='sum',
                )

                # columnas_muestras son los nombres de muestra (antes de reset_index)
                columnas_muestras = df_pivot_full.columns.tolist()

                # reset_index convierte el índice 'taxon' en columna para el servicio
                df_pivot_viz = df_pivot_full.reset_index()

                viz = VisualizationService()
                graficos_avanzados = viz.obtener_paquete_graficos_avanzados(
                    df_pivote=df_pivot_viz,        # todos los taxa → Top N + Otros internamente
                    columnas_muestras=columnas_muestras,
                    nivel='taxon',
                    top_n=top_n,
                    orden_taxa=orden_taxa_pooled,
                )

                contexto["graficos_avanzados"] = graficos_avanzados
                contexto["graficos_avanzados_json"] = json.dumps(graficos_avanzados)

        # Análisis diferencial (solo cuando hay exactamente 1 muestra seleccionada)
        if len(muestra_ids) == 1:
            diff = obtener_analisis_diferencial(tipo=tipo, nivel=nivel, muestra_id=muestra_ids[0])
            if diff:
                contexto["analisis_diferencial"] = diff

    except Exception as e:
        import traceback
        traceback.print_exc()
        messages.error(request, f"Error al computar los perfiles: {str(e)}")
        contexto["graficos_avanzados"] = {'error': str(e)}

    contexto.update({
        "tipo_actual": tipo,
        "top_n_actual": top_n,
        "nivel_actual": nivel,
        "nivel_actual_label": NIVELES_ES.get(nivel, nivel.capitalize()),
        "opciones_top_n": OPCIONES_TOP_N,
        "niveles_choices": NIVELES_CHOICES,
        "marcadores_choices": MARCADORES_CHOICES,
        "tipos_por_muestra_json": tipos_por_muestra_json,
    })

    return render(request, "analisis/analisis_avanzado.html", contexto)


@login_required
def resultado_analisis(request, muestra_id):
    try:
        tipo  = request.GET.get("tipo", "16S")
        nivel = request.GET.get("nivel", "genus")
        if nivel not in NIVELES_VALIDOS:
            nivel = "genus"

        try:
            top_n = int(request.GET.get("top_n", 10))
            if top_n not in OPCIONES_TOP_N:
                top_n = 10
        except (ValueError, TypeError):
            top_n = 10

        contexto = obtener_analisis_avanzado(
            tipo=tipo,
            top_n=top_n,
            nivel=nivel,
            muestra_id=muestra_id,
        )
        diversidad = obtener_diversidad(tipo=tipo, nivel=nivel, muestra_id=muestra_id)
        if diversidad:
            contexto["diversidad"] = diversidad

        contexto["muestra_id"]          = muestra_id
        contexto["opciones_top_n"]      = OPCIONES_TOP_N
        contexto["niveles_disponibles"] = NIVELES_VALIDOS
    except Exception as e:
        messages.error(request, f"No se pudo estructurar el reporte: {str(e)}")
        return redirect("analisis:analisis_avanzado")
    return render(request, "analisis/resultados.html", contexto)