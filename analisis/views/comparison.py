import json
import logging
import pandas as pd
import plotly.express as px
from typing import Any, Dict, List

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from django.db.models import F, Sum

from analisis.models import ResultadoTaxonomico, ArchivoMolecular
from analisis.services.business.comparison_service import ejecutar_comparacion_clean
from analisis.services.processing.diversity import DiversityService
from analisis.services.business.analysis_service import (
    obtener_diversidad_beta_inter,
    obtener_diversidad_gamma,
    obtener_permanova,
)
from analisis.constants import (
    OPCIONES_TOP_N, NIVELES_ES, get_taxonomia_annotation,
)

logger = logging.getLogger(__name__)


def _contar_clasificaciones(tabla: List[Dict[str, Any]]) -> Dict[str, int]:
    conteo = {"benefico": 0, "fitopatogeno": 0, "sin_clasificar": 0}
    for fila in tabla:
        clave = fila.get("clasificacion", "sin_clasificar")
        if clave in conteo:
            conteo[clave] += 1
    return conteo


def _aviso_profundidad(lecturas: List[int]) -> str:
    """Avisa si la profundidad de secuenciación difiere más del doble entre muestras."""
    lecturas = [n for n in lecturas if n > 0]
    if len(lecturas) < 2 or max(lecturas) / min(lecturas) <= 2:
        return ""
    def _fmt(x):
        return f"{x:,}".replace(",", ".")
    return (
        f"Las muestras tienen profundidades de secuenciación muy distintas "
        f"({_fmt(min(lecturas))}–{_fmt(max(lecturas))} lecturas); la riqueza no es "
        f"directamente comparable (Schloss, 2024)."
    )


@login_required
def comparar(request):
    from analisis.forms import CompararForm

    # El menú lateral envía ?tipo=, pero este formulario usa "marcador".
    get_params = request.GET
    if "tipo" in get_params and "marcador" not in get_params:
        get_params = get_params.copy()
        get_params["marcador"] = get_params["tipo"]

    form = CompararForm(get_params or None)

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
        "aviso_profundidad": "",
        "diversidad_beta": None,
        "diversidad_gamma": None,
        "permanova": None,
        "tipos_por_muestra_json": tipos_por_muestra_json,
    }

    if request.GET and form.is_valid():
        muestras_seleccionadas = form.cleaned_data.get("muestras")
        # Campos requeridos: tras is_valid() siempre tienen valor.
        marcador = form.cleaned_data["marcador"]
        nivel = form.cleaned_data["nivel"]
        try:
            top_n_form = int(form.cleaned_data.get("top_n", 10))
            TOP_N_VISUALIZACION = top_n_form if top_n_form in OPCIONES_TOP_N else 10
        except (ValueError, TypeError):
            TOP_N_VISUALIZACION = 10

        # Solo entran las muestras con datos del marcador elegido: una sin datos
        # deja en cero el core (taxa en TODAS) y los dominantes (en más de la mitad).
        if muestras_seleccionadas:
            con_datos = set(ArchivoMolecular.objects.filter(
                muestra__in=muestras_seleccionadas, tipo_analisis=marcador
            ).values_list("muestra_id", flat=True))
            sin_datos = [m.codigo for m in muestras_seleccionadas if m.id not in con_datos]
            muestras_seleccionadas = [m for m in muestras_seleccionadas if m.id in con_datos]
            if sin_datos:
                messages.warning(
                    request,
                    f"No se incluyeron por no tener datos {marcador}: {', '.join(sin_datos)}.",
                )
            if len(muestras_seleccionadas) < 2:
                messages.error(request, f"Se necesitan al menos dos muestras con datos {marcador} para comparar.")

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

                    # % de taxa compartidos dentro del Top N mostrado (máximo 100%).
                    taxa_en_tabla = {
                        f.get("taxonomia") for f in tabla
                        if "Otros microorganismos" not in str(f.get("taxonomia", ""))
                    }
                    taxa_unicos = len(taxa_en_tabla)
                    compartidos_en_tabla = [t for t in compartidos if t in taxa_en_tabla]
                    contexto["pct_compartidos"] = (
                        round(len(compartidos_en_tabla) / taxa_unicos * 100, 1) if taxa_unicos > 0 else 0.0
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
                            nivel_label = NIVELES_ES.get(nivel, (nivel or '').capitalize())
                            fig = px.bar(
                                df_plot, x="taxonomia", y="Abundancia", color="Muestra",
                                barmode="group",
                                title=f"Comparación de Abundancias — {nivel_label} (Top {TOP_N_VISUALIZACION})",
                                labels={
                                    "taxonomia": f"{nivel_label} taxonómico",
                                    "Abundancia": "Abundancia relativa (%)",
                                    "Muestra": "Muestra",
                                },
                                template="plotly_white",
                            )
                            fig.update_layout(
                                xaxis=dict(tickangle=-45, automargin=True, tickfont=dict(size=10)),
                                yaxis=dict(rangemode="tozero"),
                                margin=dict(b=160, t=60, l=60, r=20),
                                height=460,
                            )
                            contexto["graficos_json"] = fig.to_json()

                    contexto["tabla_json"] = json.dumps(tabla)

                    # Diversidad alfa por muestra (agrupada al nivel elegido).
                    taxonomia_expr = get_taxonomia_annotation(nivel)
                    alfa_por_muestra = {}
                    shannon_por_muestra = {}
                    # Una sola consulta para todas las muestras (antes, una por muestra)
                    filas_por_muestra: Dict[int, List[Dict[str, Any]]] = {}
                    for fila in (
                        ResultadoTaxonomico.objects
                        .filter(archivo__tipo_analisis=marcador,
                                archivo__muestra__in=list(muestras_seleccionadas))
                        .values(mid=F('archivo__muestra_id'), t=taxonomia_expr)
                        .annotate(h=Sum('num_hits'))
                    ):
                        filas_por_muestra.setdefault(fila['mid'], []).append(fila)
                    for muestra in muestras_seleccionadas:
                        rows = filas_por_muestra.get(muestra.id, [])
                        # Profundidad = todas las lecturas de la muestra, incluidas
                        # las que no tienen asignación a este nivel taxonómico
                        lecturas_totales = int(sum(r['h'] or 0 for r in rows))
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
                                    'lecturas_totales': lecturas_totales,
                                }
                                shannon_por_muestra[muestra.codigo] = alfa_por_muestra[muestra.codigo]['shannon']
                    contexto["alfa_por_muestra"] = alfa_por_muestra
                    contexto["aviso_profundidad"] = _aviso_profundidad(
                        [m['lecturas_totales'] for m in alfa_por_muestra.values()]
                    )
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

            except Exception:
                logger.exception("Fallo en comparación de perfiles (usuario=%s)", request.user.pk)
                messages.error(request, "No se pudo completar la comparación. Intente de nuevo o con otra selección.")
    elif request.GET:
        # Formulario inválido (p. ej. menos de 2 muestras): avisar al usuario.
        primer_error = next(
            (str(err) for errs in form.errors.values() for err in errs), None
        )
        messages.error(request, primer_error or "Revise los campos del formulario.")

    return render(request, "analisis/comparar.html", contexto)