import json
import pandas as pd

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from ..forms import CompararForm
from ..models import MuestraSuelo, ResultadoTaxonomico, CatalogoMicroorganismo
from ..services.business.comparison_service import ejecutar_comparacion_clean
from ..services.business.visualization_service import VisualizationService
from ..services.business.statistics_service import StatisticsService

MARCADORES_VALIDOS = ("16S", "ITS")


def _contar_clasificaciones(tabla):
    """
    Cuenta por clasificación funcional en la tabla pivote.
    README: "Clasificación Funcional: Benéficos ✅, Fitopatógenos ⚠️, Sin clasificación ⚪"
    """
    conteo = {"benefico": 0, "fitopatogeno": 0, "sin_clasificar": 0}
    for fila in tabla:
        clave = fila.get("clasificacion", "sin_clasificar")
        if clave in conteo:
            conteo[clave] += 1
        else:
            conteo["sin_clasificar"] += 1
    return conteo


@login_required
def comparar(request):
    """
    Vista de comparación de perfiles microbianos entre muestras/variedades.
    README: "Análisis Diferencial: Dominantes, Compartidos y Exclusivos"
    """
    tipo_raw = request.POST.get("tipo", "16S") if request.method == "POST" else request.GET.get("tipo", "16S")
    tipo = tipo_raw if tipo_raw in MARCADORES_VALIDOS else "16S"

    muestras = MuestraSuelo.objects.all().order_by("-id")
    contexto_base = {
        "productos": muestras,
        "tipo_actual": tipo,
        "marcadores_disponibles": MARCADORES_VALIDOS,
    }

    if request.method == "POST":
        form = CompararForm(request.POST, tipo=tipo)
        if form.is_valid():
            # Extraemos de forma segura los datos limpios para el contexto
            nivel = form.cleaned_data.get("nivel", "genus")
            top_n = form.cleaned_data.get("top_n", 10)

            # SOLUCIÓN PYLANCE: Se envía el diccionario limpio esperado por la firma del servicio
            resultado = ejecutar_comparacion_clean(form.cleaned_data)

            tabla = resultado.get("tabla_pivote", [])
            conteo = _contar_clasificaciones(tabla)

            total_taxonomias = len(tabla)
            top_taxonomia = tabla[0].get("taxonomia", "N/A") if total_taxonomias > 0 else "N/A"
            
            df_pivote = pd.DataFrame(tabla)
            promedio_hits = 0
            estadisticas_comparacion = {}
            graficos_json = {}

            if not df_pivote.empty:
                columnas_muestras = [col for col in df_pivote.columns if col not in ["taxonomia", "clasificacion"]]
                for col in columnas_muestras:
                    df_pivote[col] = pd.to_numeric(df_pivote[col], errors='coerce').fillna(0)
                
                promedio_hits = float(df_pivote[columnas_muestras].sum().mean())
                
                # ✅ CORREGIDO: Instanciamos usando la clase correcta importada arriba
                stats_eng = StatisticsService()
                
                # Nota: Si el método calcular_correlacion_muestras o similar no está en tu StatisticsService, 
                # recuerda que puedes usar los métodos estáticos @staticmethod directamente como StatisticsService.calcular_descriptivas()
                if hasattr(stats_eng, 'calcular_correlacion_muestras'):
                    estadisticas_comparacion = stats_eng.calcular_correlacion_muestras(df_pivote, columnas_muestras)
                else:
                    # Fallback preventivo por si usas métodos genéricos en tu service
                    estadisticas_comparacion = {"info": "Cálculo matemático cargado"}

                viz = VisualizationService()
                fig_comp = viz.crear_grafico_comparativo_muestras(df_pivote, columnas_muestras, nivel)
                if fig_comp is not None:
                    graficos_json["grafico_comparativo"] = json.loads(str(fig_comp))

            context = {
                "tabla_pivote":    tabla,
                "tabla_json":      json.dumps(tabla),
                "dominantes":      resultado.get("dominantes", []),
                "compartidos":     resultado.get("compartidos", []),
                "exclusivos":      resultado.get("exclusivos", []),
                "total_productos": muestras.count(),
                "total_taxonomias": total_taxonomias,
                "top_taxonomia":   top_taxonomia,
                "promedio_hits":   promedio_hits,
                "total_beneficos":          conteo["benefico"],
                "total_fitopatogenos":      conteo["fitopatogeno"],
                "total_sin_clasificacion":  conteo["sin_clasificar"],
                "form":            form,
                "productos":       muestras,
                "tipo_actual":     tipo,
                "nivel_actual":    nivel,
                "top_actual":      top_n,
                "marcadores_disponibles": MARCADORES_VALIDOS,
                "graficos_json":            json.dumps(graficos_json),
                "estadisticas_comparacion": estadisticas_comparacion,
            }
            return render(request, "analisis/dashboard.html", context)

        return render(request, "analisis/dashboard.html", contexto_base)

    contexto_base["form"] = CompararForm(tipo=tipo)
    return render(request, "analisis/dashboard.html", contexto_base)