from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import pandas as pd
import plotly.express as px

from ..services.business.analysis_service import (
    obtener_analisis_avanzado,
    obtener_analisis_diferencial,
    obtener_diversidad,
)
from ..services.business.visualization_service import VisualizationService
from ..models import ResultadoTaxonomico
from analisis.services.processing.diversity import DiversityService

@login_required
def analisis_avanzado(request):
    tipo = request.GET.get("tipo", "16S")
    top_n_raw = request.GET.get("top_n", "10")
    nivel = request.GET.get("nivel", "genus")
    variedad_id = request.GET.get("producto_id", None)
    muestra_id = request.GET.get("muestra_id", None)

    opciones_top_n = [5, 10, 25, 50]
    try:
        top_n = int(top_n_raw) if int(top_n_raw) in opciones_top_n else 10
    except ValueError:
        top_n = 10

    contexto = {
        "top_microorganismos": [],
        "diversidad": {},
        "graficos_avanzados": {},
        "analisis_diferencial": None,
    }

    try:
        # Obtener el análisis avanzado básico (tabla de Top N para visualización)
        resultado = obtener_analisis_avanzado(
            tipo=tipo, top_n=top_n, nivel=nivel, variedad_id=variedad_id, muestra_id=muestra_id
        )

        if "resumen" in resultado and resultado["resumen"]:
            contexto["top_microorganismos"] = resultado["resumen"]

        # Diversidad alfa: calculada por muestra sobre datos COMPLETOS (no el resumen truncado)
        diversidad = obtener_diversidad(tipo=tipo, nivel=nivel, variedad_id=variedad_id)
        if diversidad:
            contexto["diversidad"] = diversidad

        # --- GRÁFICAS AVANZADAS ---
        qs = ResultadoTaxonomico.objects.filter(archivo__tipo_analisis=tipo)
        if variedad_id:
            qs = qs.filter(archivo__muestra__variedad_clon_id=variedad_id)
        if muestra_id:
            qs = qs.filter(archivo__muestra_id=muestra_id)

        if qs.exists():
            mapa_campo = {
                'kingdom': 'kingdom', 'phylum': 'phylum', 'class': 'tax_class',
                'order': 'order', 'family': 'family', 'genus': 'genus', 'species': 'species'
            }
            campo_modelo = mapa_campo.get(nivel, 'genus')

            data = list(qs.values(campo_modelo, 'archivo__muestra__codigo', 'porcentaje_hits'))
            if data:
                df_raw = pd.DataFrame(data)
                df_raw.rename(columns={
                    campo_modelo: 'taxon',
                    'archivo__muestra__codigo': 'muestra',
                    'porcentaje_hits': 'abundancia'
                }, inplace=True)

                # Pivote completo — todos los taxones; el servicio aplica Top N internamente
                df_pivot_full = df_raw.pivot_table(
                    index='taxon', columns='muestra', values='abundancia', fill_value=0
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
                )

                # Boxplot de Shannon: calculado sobre TODOS los taxones de cada muestra
                diversidad_por_muestra = {}
                for muestra_codigo in df_pivot_full.columns:
                    serie = df_pivot_full[muestra_codigo]
                    df_m = pd.DataFrame({'%_hits': serie[serie > 0].values})
                    if not df_m.empty:
                        alfa = DiversityService.calcular_diversidad_alfa(df_m)
                        diversidad_por_muestra[muestra_codigo] = alfa.get('shannon', 0)
                    else:
                        diversidad_por_muestra[muestra_codigo] = 0

                if diversidad_por_muestra:
                    df_boxplot = pd.DataFrame(
                        list(diversidad_por_muestra.items()), columns=['muestra', 'shannon']
                    )
                    fig_box = px.bar(
                        df_boxplot, x='muestra', y='shannon',
                        title='Índice de Shannon por Muestra (todos los taxones)',
                        template='plotly_white',
                    )
                    fig_box.update_layout(
                        yaxis_title='Shannon H\'', xaxis_title='Muestra', xaxis_tickangle=-30
                    )
                    graficos_avanzados['grafico_boxplot'] = fig_box.to_dict()

                contexto["graficos_avanzados"] = graficos_avanzados

        # Análisis diferencial (si hay variedad seleccionada)
        if variedad_id:
            diff = obtener_analisis_diferencial(tipo=tipo, nivel=nivel, variedad_id=variedad_id)
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
        "opciones_top_n": opciones_top_n,
        "niveles_taxonomicos": ["kingdom", "phylum", "class", "order", "family", "genus", "species"],
        "marcadores_disponibles": ("16S", "ITS"),
    })

    return render(request, "analisis/analisis_avanzado.html", contexto)


OPCIONES_TOP_N = [5, 10, 25, 50]
NIVELES_VALIDOS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

@login_required
def resultado_analisis(request, muestra_id):
    try:
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
            tipo=request.GET.get("tipo", "16S"),
            top_n=top_n,
            nivel=nivel,
            muestra_id=muestra_id,
        )
        contexto["muestra_id"]    = muestra_id
        contexto["opciones_top_n"] = OPCIONES_TOP_N
        contexto["niveles_disponibles"] = NIVELES_VALIDOS
    except Exception as e:
        messages.error(request, f"No se pudo estructurar el reporte: {str(e)}")
        return redirect("analisis:analisis_avanzado")
    return render(request, "analisis/resultados.html", contexto)


@login_required
@require_POST
def exportar_analisis(request):
    from analisis.services.business.report_generation_service import ReportGenerationService
    tipo = request.POST.get("tipo", "16S")
    top_n = int(request.POST.get("top_n", 10))
    nivel = request.POST.get("nivel", "genus")
    variedad_id = request.POST.get("producto_id", None)
    formato = request.POST.get("formato", "pdf")

    try:
        resultado = ReportGenerationService.generar_reporte_analisis(
            tipo=tipo, variedad_id=variedad_id, formato=formato,
            top_n=top_n, nivel=nivel, usuario=request.user,
        )
        return JsonResponse({"ok": True, "url": resultado.get("url")})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)