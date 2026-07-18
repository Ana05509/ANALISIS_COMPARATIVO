from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import F, Sum
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from ..services.business.analysis_service import (
    obtener_analisis_avanzado,
    obtener_analisis_diferencial,
    obtener_diversidad,
    obtener_diversidad_beta_inter,
    obtener_diversidad_gamma,
    obtener_permanova,
)
from ..services.business.visualization_service import VisualizationService
from ..models import ResultadoTaxonomico, MuestraSuelo, ArchivoMolecular
from analisis.services.processing.diversity import DiversityService
from analisis.constants import OPCIONES_TOP_N, NIVELES_VALIDOS, MAPA_NIVELES, NIVELES_ES, MARCADORES_ES, NIVELES_CHOICES, MARCADORES_CHOICES

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

        # Diversidad beta inter-muestra (Bray-Curtis y Jaccard entre pares)
        if len(muestra_ids) >= 2:
            beta_inter = obtener_diversidad_beta_inter(tipo=tipo, nivel=nivel, muestra_ids=muestra_ids)
            if beta_inter:
                contexto["diversidad_beta"] = beta_inter

        # Diversidad gamma (metacomunidad: todas las muestras combinadas)
        if len(muestra_ids) >= 2:
            gamma = obtener_diversidad_gamma(tipo=tipo, nivel=nivel, muestra_ids=muestra_ids)
            if gamma:
                contexto["diversidad_gamma"] = gamma

        # PERMANOVA: ¿difieren significativamente los grupos (cultivos)?
        if len(muestra_ids) >= 2:
            permanova = obtener_permanova(tipo=tipo, nivel=nivel, muestra_ids=muestra_ids)
            if permanova:
                contexto["permanova"] = permanova

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
                )

                # Shannon completo: calcula los 4 índices alfa por muestra sobre TODOS los taxones
                alfa_completo = {}
                for muestra_codigo in df_pivot_full.columns:
                    serie = df_pivot_full[muestra_codigo]
                    df_m = pd.DataFrame({'%_hits': serie[serie > 0].values})
                    if not df_m.empty:
                        alfa_completo[muestra_codigo] = DiversityService.calcular_diversidad_alfa(df_m)
                    else:
                        alfa_completo[muestra_codigo] = {
                            'riqueza': 0, 'shannon': 0.0, 'simpson': 0.0, 'equitatividad': 0.0
                        }

                if alfa_completo:
                    df_sh = pd.DataFrame([
                        {'muestra': k, **v} for k, v in alfa_completo.items()
                    ]).sort_values('shannon', ascending=False)

                    h_max = float(df_sh['shannon'].max())

                    # Colores por umbral absoluto — el color es independiente de
                    # las muestras seleccionadas, así rojo siempre significa baja
                    # diversidad y verde siempre significa alta, sin engañar al especialista
                    def _color_shannon(h):
                        if h < 1.0:   return '#DC2626'   # rojo   — muy baja
                        if h < 2.0:   return '#F97316'   # naranja — baja
                        if h < 3.0:   return '#EAB308'   # ámbar  — moderada
                        return '#16A34A'                  # verde  — alta

                    bar_colors = [_color_shannon(h) for h in df_sh['shannon']]

                    hover_texts = [
                        [f"<b>{row['muestra']}</b><br>"
                         f"Shannon H': <b>{row['shannon']:.4f}</b><br>"
                         f"Riqueza (S): {int(row['riqueza'])} taxa<br>"
                         f"Simpson (1-D): {row['simpson']:.4f}<br>"
                         f"Equitatividad (J'): {row['equitatividad']:.4f}"]
                        for _, row in df_sh.iterrows()
                    ]

                    fig_box = go.Figure()
                    fig_box.add_trace(go.Bar(
                        x=df_sh['muestra'],
                        y=df_sh['shannon'],
                        marker=dict(color=bar_colors, line=dict(color='white', width=1.5)),
                        text=[f"{v:.3f}" for v in df_sh['shannon']],
                        textposition='outside',
                        textfont=dict(size=10),
                        customdata=hover_texts,
                        hovertemplate='%{customdata[0]}<extra></extra>',
                        showlegend=False,
                    ))

                    # Líneas de referencia con etiquetas dentro del área del gráfico
                    # (xref='paper' garantiza que el texto siempre sea visible)
                    for ref_y, ref_label, ref_color in [
                        (1.0, "Diversidad baja  (H'=1)",     'rgba(220,38,38,0.6)'),
                        (2.0, "Diversidad moderada  (H'=2)", 'rgba(234,179,8,0.7)'),
                        (3.0, "Diversidad alta  (H'=3)",     'rgba(22,163,74,0.7)'),
                    ]:
                        if ref_y <= h_max * 1.25:
                            fig_box.add_hline(
                                y=ref_y,
                                line=dict(dash='dot', color=ref_color, width=1.2),
                            )
                            fig_box.add_annotation(
                                x=0.99, y=ref_y,
                                xref='paper', yref='y',
                                text=ref_label,
                                showarrow=False,
                                xanchor='right',
                                yanchor='bottom',
                                font=dict(size=9, color='gray'),
                                bgcolor='rgba(255,255,255,0.75)',
                            )

                    fig_box.update_layout(
                        title=dict(text="Shannon H' por Muestra (perfil taxonómico completo)",
                                   font=dict(size=14), x=0.5, xanchor='center'),
                        yaxis=dict(title="Shannon H'", rangemode='tozero',
                                   gridcolor='rgba(220,220,220,0.5)', zeroline=False),
                        xaxis=dict(title='Muestra', tickangle=-30,
                                   automargin=True, tickfont=dict(size=10)),
                        template='plotly_white',
                        height=460,
                        margin=dict(b=120, t=80, l=60, r=30),
                        bargap=0.35,
                    )
                    graficos_avanzados['grafico_boxplot'] = json.loads(fig_box.to_json())

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