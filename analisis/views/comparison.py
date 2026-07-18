import json
import pandas as pd
import plotly.express as px
from typing import Any, Dict, List

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseBase
from django.views.decorators.http import require_POST

from django.db.models import Sum

from analisis.models import ResultadoTaxonomico, ArchivoMolecular
from analisis.services.business.comparison_service import ejecutar_comparacion_clean
from analisis.services.processing.diversity import DiversityService
from analisis.services.business.analysis_service import (
    obtener_analisis_avanzado,
    obtener_diversidad_beta_inter,
    obtener_diversidad_gamma,
    obtener_permanova,
)
from analisis.services.business.export_service import ExportService
from analisis.services.business.report_generation_service import ReportGenerationService
from analisis.constants import (
    MARCADORES_VALIDOS, OPCIONES_TOP_N, NIVELES_ES, MARCADORES_ES,
    NIVELES_CHOICES, MARCADORES_CHOICES, get_taxonomia_annotation,
)

FORMATOS_VALIDOS = ("pdf", "excel", "html", "json")


def _contar_clasificaciones(tabla: List[Dict[str, Any]]) -> Dict[str, int]:
    conteo = {"benefico": 0, "fitopatogeno": 0, "sin_clasificar": 0}
    for fila in tabla:
        clave = fila.get("clasificacion", "sin_clasificar")
        if clave in conteo:
            conteo[clave] += 1
    return conteo


@login_required
def comparar(request):
    from analisis.forms import CompararForm

    form = CompararForm(request.GET or None)

    _tipos_raw: dict = {}
    for mid, t in ArchivoMolecular.objects.values_list("muestra_id", "tipo_analisis").distinct():
        _tipos_raw.setdefault(mid, []).append(t)
    tipos_por_muestra_json = json.dumps(_tipos_raw)

    contexto: Dict[str, Any] = {
        "form": form,
        "marcador_seleccionado": None,
        "tabla_comparativa": [],
        "graficos_json": "{}",
        "conteo_clasificaciones": {"benefico": 0, "fitopatogeno": 0, "sin_clasificar": 0},
        "dominantes": [],
        "compartidos": [],
        "exclusivos": [],
        "total_muestras": 0,
        "total_taxonomias": 0,
        "pct_compartidos": 0.0,
        "top_taxonomia": "—",
        "top_actual": 10,
        "nivel_actual": "genus",
        "nivel_actual_label": NIVELES_ES.get("genus", "Género"),
        "opciones_top_n": OPCIONES_TOP_N,
        "tabla_json": "[]",
        "shannon_json": "{}",
        "alfa_json": "{}",
        "alfa_por_muestra": {},
        "diversidad_beta": None,
        "diversidad_gamma": None,
        "permanova": None,
        "tipos_por_muestra_json": tipos_por_muestra_json,
    }

    if request.GET and form.is_valid():
        muestras_seleccionadas = form.cleaned_data.get("muestras")
        marcador = form.cleaned_data.get("marcador")
        nivel = form.cleaned_data.get("nivel")
        try:
            top_n_form = int(form.cleaned_data.get("top_n", 10))
            TOP_N_VISUALIZACION = top_n_form if top_n_form in OPCIONES_TOP_N else 10
        except (ValueError, TypeError):
            TOP_N_VISUALIZACION = 10

        if muestras_seleccionadas and len(muestras_seleccionadas) >= 2:
            contexto["marcador_seleccionado"] = marcador
            contexto["total_muestras"] = len(muestras_seleccionadas)
            contexto["top_actual"] = TOP_N_VISUALIZACION
            contexto["nivel_actual"] = nivel
            contexto["nivel_actual_label"] = NIVELES_ES.get(nivel, nivel.capitalize())

            cleaned_data = {
                "tipo": marcador,
                "nivel": nivel,
                "top_n": TOP_N_VISUALIZACION,
                "productos": list(muestras_seleccionadas),
            }

            try:
                resultado = ejecutar_comparacion_clean(cleaned_data)
                tabla = resultado.get("tabla", [])

                if tabla:
                    compartidos = resultado.get("compartidos", [])
                    contexto["tabla_comparativa"] = tabla
                    contexto["conteo_clasificaciones"] = _contar_clasificaciones(tabla)
                    contexto["dominantes"] = resultado.get("dominantes", [])
                    contexto["compartidos"] = compartidos
                    contexto["exclusivos"] = resultado.get("exclusivos", [])
                    contexto["total_taxonomias"] = len(tabla)
                    contexto["top_taxonomia"] = tabla[0].get("taxonomia", "—")

                    # Fix 1 — % taxa compartidos (ecológicamente significativo vs promedio de porcentajes)
                    taxa_unicos = len([f for f in tabla if "Otros microorganismos" not in str(f.get("taxonomia", ""))])
                    contexto["pct_compartidos"] = (
                        round(len(compartidos) / taxa_unicos * 100, 1) if taxa_unicos > 0 else 0.0
                    )

                    # Fix 3 — gráfico con todas las muestras seleccionadas
                    df_comp = pd.DataFrame(tabla)
                    if not df_comp.empty and "taxonomia" in df_comp.columns:
                        muestras_cols = [c for c in df_comp.columns if c not in ["taxonomia", "clasificacion"]]
                        if muestras_cols:
                            df_plot = df_comp.melt(
                                id_vars=["taxonomia"],
                                value_vars=muestras_cols,
                                var_name="Muestra",
                                value_name="Abundancia"
                            )
                            fig = px.bar(
                                df_plot, x="taxonomia", y="Abundancia", color="Muestra",
                                barmode="group",
                                title=f"Comparación de Abundancias — {(nivel or '').capitalize()} (Top {TOP_N_VISUALIZACION})",
                                template="plotly_white",
                            )
                            fig.update_layout(
                                xaxis=dict(tickangle=-45, automargin=True, tickfont=dict(size=10)),
                                margin=dict(b=160, t=60, l=60, r=20),
                                height=460,
                            )
                            contexto["graficos_json"] = fig.to_json()

                    contexto["tabla_json"] = json.dumps(tabla)

                    # Diversidad alfa completa por muestra
                    # Agrega Sum(num_hits) por taxon al nivel elegido para evitar
                    # contar múltiples especies del mismo genus como taxa distintos
                    taxonomia_expr = get_taxonomia_annotation(nivel)
                    alfa_por_muestra = {}
                    shannon_por_muestra = {}
                    for muestra in muestras_seleccionadas:
                        rows = list(
                            ResultadoTaxonomico.objects
                            .filter(archivo__tipo_analisis=marcador, archivo__muestra=muestra)
                            .values(t=taxonomia_expr)
                            .annotate(h=Sum('num_hits'))
                        )
                        rows = [r for r in rows if r['t']]
                        if rows:
                            total = sum(r['h'] for r in rows) or 1
                            df_m = pd.DataFrame({'%_hits': [r['h'] / total * 100 for r in rows]})
                            df_m = df_m[df_m['%_hits'] > 0]
                            if not df_m.empty:
                                alfa = DiversityService.calcular_diversidad_alfa(df_m)
                                alfa_por_muestra[muestra.codigo] = {
                                    'riqueza': int(alfa.get('riqueza', 0)),
                                    'shannon': round(alfa.get('shannon', 0), 4),
                                    'simpson': round(alfa.get('simpson', 0), 4),
                                    'equitatividad': round(alfa.get('equitatividad', 0), 4),
                                }
                                shannon_por_muestra[muestra.codigo] = alfa_por_muestra[muestra.codigo]['shannon']
                    contexto["alfa_por_muestra"] = alfa_por_muestra
                    contexto["alfa_json"] = json.dumps(alfa_por_muestra)
                    contexto["shannon_json"] = json.dumps(shannon_por_muestra)

                    muestra_ids = [m.id for m in muestras_seleccionadas]

                    # Diversidad beta inter-muestra
                    beta_inter = obtener_diversidad_beta_inter(tipo=marcador, nivel=nivel, muestra_ids=muestra_ids)
                    if beta_inter:
                        contexto["diversidad_beta"] = beta_inter

                    # Diversidad gamma (metacomunidad)
                    gamma = obtener_diversidad_gamma(tipo=marcador, nivel=nivel, muestra_ids=muestra_ids)
                    if gamma:
                        contexto["diversidad_gamma"] = gamma

                    # PERMANOVA
                    permanova = obtener_permanova(tipo=marcador, nivel=nivel, muestra_ids=muestra_ids)
                    if permanova:
                        contexto["permanova"] = permanova

                else:
                    messages.info(request, "No se encontraron datos para las muestras seleccionadas.")

            except Exception as e:
                messages.error(request, f"Error en el procesamiento comparativo: {str(e)}")
        else:
            messages.error(request, "Seleccione al menos dos muestras para comparar.")

    return render(request, "analisis/comparar.html", contexto)


@login_required
@require_POST
def exportar_reporte_comparativo(request) -> HttpResponseBase:
    try:
        tipo = request.POST.get("marcador", "16S")
        nivel = request.POST.get("nivel", "genus")
        formato = request.POST.get("formato", "pdf")
        variedad_id = request.POST.get("producto_id") or None

        if tipo not in MARCADORES_VALIDOS:
            tipo = "16S"
        if formato not in FORMATOS_VALIDOS:
            return JsonResponse({"ok": False, "error": "Formato de exportación inválido"}, status=400)

        try:
            top_n = int(request.POST.get("top_n", 10))
            if top_n not in OPCIONES_TOP_N:
                top_n = 10
        except (ValueError, TypeError):
            top_n = 10

        # Fix 2 — construir DataFrame real en lugar de vacío
        resultado_analisis = obtener_analisis_avanzado(
            tipo=tipo, top_n=top_n, nivel=nivel, variedad_id=variedad_id
        )
        resumen = resultado_analisis.get("resumen", [])
        df_reporte = pd.DataFrame(resumen) if resumen else pd.DataFrame()

        titulo = f"Reporte Comparativo {tipo} — {nivel.capitalize()} (Top {top_n})"

        if formato == "html":
            html_puro = ExportService.generar_html_reporte(
                titulo=titulo,
                datos_analisis=resultado_analisis,
                df_datos=df_reporte,
                usuario=request.user,
                nombre_archivo=f"reporte_{tipo}_{nivel}.html"
            )
            if isinstance(html_puro, str):
                return HttpResponse(html_puro, content_type="text/html")
            return html_puro

        elif formato == "pdf":
            return ExportService.exportar_pdf_response(
                titulo=titulo,
                datos_analisis=resultado_analisis,
                df_datos=df_reporte,
                usuario=request.user
            )

        elif formato == "json":
            return ExportService.exportar_json(
                df_reporte.to_dict("records"),
                nombre_archivo=f"reporte_comparativo_{tipo}_{nivel}.json"
            )

        else:
            resultado = ReportGenerationService.generar_reporte_analisis(
                tipo=tipo, variedad_id=variedad_id, formato=formato,
                top_n=top_n, nivel=nivel, usuario=request.user,
            )
            return JsonResponse({"ok": True, "url_reporte": resultado.get("url")})

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)