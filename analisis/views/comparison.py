import json
import pandas as pd

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from ..forms import CompararForm
from ..models import MuestraSuelo, ResultadoTaxonomico, CatalogoMicroorganismo
from ..services.business.comparison_service import ejecutar_comparacion_clean
from ..services.business.visualization_service import VisualizationService
from ..services.business.statistics_service import StatisticalAnalyzer

MARCADORES_VALIDOS = ("16S", "ITS")


def _contar_clasificaciones(tabla):
    """
    Cuenta por clasificacion funcional en la tabla pivote.
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
    tipo_raw = request.POST.get("tipo") or request.GET.get("tipo") or "16S"
    tipo = tipo_raw if tipo_raw in MARCADORES_VALIDOS else "16S"

    muestras = MuestraSuelo.objects.filter(
        archivomolecular__tipo_analisis=tipo
    ).distinct().order_by("-id")

    contexto_base = {
        "form":                   None,
        "productos":              muestras,
        "tipo_actual":            tipo,
        "marcadores_disponibles": MARCADORES_VALIDOS,
        "total_productos":        muestras.count(),
        "total_taxonomias":       0,
        "top_taxonomia":          "-",
        "promedio_hits":          0,
        "total_beneficos":        0,
        "total_fitopatogenos":    0,
        "total_sin_clasificacion": 0,
    }

    if request.method == "POST":
        form = CompararForm(request.POST, tipo=tipo)
        contexto_base["form"] = form

        if form.is_valid():
            try:
                resultado = ejecutar_comparacion_clean(form.cleaned_data)
            except Exception as e:
                messages.error(request, f"Error al ejecutar la comparación: {str(e)}")
                return render(request, "analisis/dashboard.html", contexto_base)

            tabla = resultado.get("tabla", [])
            total_taxonomias = len(tabla)
            top_taxonomia = tabla[0]["taxonomia"] if tabla else "-"

            promedio_hits = (
                round(
                    sum(
                        sum(v for k, v in fila.items()
                            if k not in ("taxonomia", "clasificacion"))
                        for fila in tabla
                    ) / total_taxonomias, 2,
                ) if tabla else 0
            )

            conteo = _contar_clasificaciones(tabla)

            # ========== PHASE 2: GRÁFICOS Y ESTADÍSTICA ==========
            
            graficos_json = {}
            estadisticas_comparacion = {}
            
            try:
                if tabla:
                    # Preparar datos para gráficos
                    df_comparacion = pd.DataFrame(tabla)
                    
                    # Gráfico de heatmap comparativo
                    if len(df_comparacion.columns) > 3:  # Al menos 2 muestras + taxonomia + clasificacion
                        viz = VisualizationService()
                        
                        # Crear matriz para heatmap
                        columnas_abundancia = [c for c in df_comparacion.columns 
                                             if c not in ["taxonomia", "clasificacion"]]
                        
                        if columnas_abundancia:
                            matriz_heatmap = df_comparacion[columnas_abundancia].head(15).values.tolist()
                            etiquetas_taxa = df_comparacion["taxonomia"].head(15).tolist()
                            
                            fig_heatmap = viz.crear_grafico_comparacion_heatmap(
                                matriz_heatmap,
                                etiquetas_x=columnas_abundancia,
                                etiquetas_y=etiquetas_taxa,
                                titulo=f"Comparación de Abundancia - {tipo}"
                            )
                            
                            if fig_heatmap:
                                graficos_json["heatmap_comparacion"] = json.loads(fig_heatmap.to_json())
                    
                    # Estadística: Similitud Jaccard entre muestras
                    analyzer = StatisticalAnalyzer()
                    
                    if len(df_comparacion) > 0:
                        dominantes = set(resultado.get("dominantes", []))
                        compartidos = set(resultado.get("compartidos", []))
                        exclusivos = set(resultado.get("exclusivos", []))
                        
                        if dominantes and compartidos:
                            jaccard = analyzer.calcular_similitud_jaccard(dominantes, compartidos)
                            estadisticas_comparacion["similitud_jaccard"] = {
                                "valor": round(jaccard, 4),
                                "interpretacion": "Similitud entre taxa dominantes y compartidos"
                            }
            
            except Exception as e:
                print(f"Error en Phase 2 comparison: {e}")
                messages.warning(request, "Algunas estadísticas no pudieron calcularse")

            context = {
                "tabla":           tabla,
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
                "nivel_actual":    form.cleaned_data.get("nivel"),
                "top_actual":      form.cleaned_data.get("top_n"),
                "marcadores_disponibles": MARCADORES_VALIDOS,
                
                # PHASE 2
                "graficos_json":            json.dumps(graficos_json),
                "estadisticas_comparacion": estadisticas_comparacion,
            }
            return render(request, "analisis/dashboard.html", context)

        return render(request, "analisis/dashboard.html", contexto_base)

    contexto_base["form"] = CompararForm(tipo=tipo)
    return render(request, "analisis/dashboard.html", contexto_base)