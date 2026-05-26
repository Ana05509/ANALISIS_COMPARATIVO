from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import pandas as pd
import json

from ..services.business.analysis_service import (
    obtener_analisis_avanzado,
    obtener_top_n,
    obtener_analisis_diferencial,
    obtener_diversidad,
)
from ..services.business.comparison_service import (
    obtener_microorganismos_exclusivos,
    obtener_microorganismos_compartidos,
)
from ..services.business.visualization_service import VisualizationService
from ..services.business.statistics_service import StatisticalAnalyzer
from ..models import ResultadoTaxonomico
from django.db.models import F, Sum


@login_required
def analisis_avanzado(request):
    tipo       = request.GET.get("tipo", "16S")
    top_n_raw  = request.GET.get("top_n", "10")
    nivel      = request.GET.get("nivel", "genus")
    variedad_id = request.GET.get("producto_id", None)   # URL usa producto_id → internamente variedad_id
    muestra_id = request.GET.get("muestra_id", None)

    opciones_top_n = [5, 10, 25, 50]
    try:
        top_n = int(top_n_raw)
        if top_n not in opciones_top_n:
            top_n = 10
    except (ValueError, TypeError):
        top_n = 10

    if tipo not in ("16S", "ITS"):
        tipo = "16S"

    niveles_validos = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
    if nivel not in niveles_validos:
        nivel = "genus"

    try:
        contexto = obtener_analisis_avanzado(
            tipo=tipo,
            top_n=top_n,
            nivel=nivel,
            variedad_id=variedad_id,
            muestra_id=muestra_id,
        )
    except Exception as e:
        messages.error(request, f"Error al procesar el análisis: {str(e)}")
        contexto = {}

    try:
        contexto["top_microorganismos"] = obtener_top_n(
            tipo=tipo,
            n=top_n,
            nivel=nivel,
            variedad_id=variedad_id,
        )
    except Exception:
        contexto["top_microorganismos"] = []

    try:
        contexto["diversidad"] = obtener_diversidad(
            tipo=tipo,
            nivel=nivel,
            variedad_id=variedad_id,
        )
    except Exception:
        contexto["diversidad"] = None

    if variedad_id or muestra_id:
        try:
            contexto["analisis_diferencial"] = obtener_analisis_diferencial(
                tipo=tipo,
                nivel=nivel,
                variedad_id=variedad_id,
                muestra_id=muestra_id,
            )
            contexto["exclusivos"] = obtener_microorganismos_exclusivos(
                tipo=tipo,
                variedad_id=variedad_id,
            )
            contexto["compartidos"] = obtener_microorganismos_compartidos(
                tipo=tipo,
                variedad_id=variedad_id,
            )
        except Exception:
            contexto["analisis_diferencial"] = None
            contexto["exclusivos"] = []
            contexto["compartidos"] = []

    # ========== PHASE 2: ESTADÍSTICA AVANZADA ==========
    
    graficos_json = {}
    estadisticas = {}
    
    try:
        # Obtener datos para estadística
        qs = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo
        )
        
        if variedad_id:
            qs = qs.filter(archivo__muestra__variedad_clon_id=variedad_id)
        if muestra_id:
            qs = qs.filter(archivo__muestra_id=muestra_id)
        
        if qs.exists():
            # Convertir a DataFrame
            data = list(
                qs.values(nombre_tax=F("genus"))
                .annotate(total_hits=Sum("num_hits"), total_porcentaje=Sum("porcentaje_hits"))
                .order_by("-total_porcentaje")[:top_n]
            )
            
            if data:
                df_stats = pd.DataFrame(data)
                
                # Calcular estadísticas descriptivas
                analyzer = StatisticalAnalyzer()
                estadisticas["descriptivas"] = analyzer.calcular_descriptivas(
                    pd.DataFrame({"% _hits": [d['total_porcentaje'] for d in data]})
                )
                
                # Test de normalidad
                estadisticas["normalidad"] = analyzer.test_normalidad_shapiro(
                    pd.DataFrame({"%_hits": [d['total_porcentaje'] for d in data]})
                )
                
                # Gráficos adicionales
                viz = VisualizationService()
                
                # Gráfico de línea de abundancia acumulada
                df_sorted = pd.DataFrame(data).sort_values('total_porcentaje', ascending=False)
                df_sorted['acumulada'] = df_sorted['total_porcentaje'].cumsum()
                
                fig_linea = viz.crear_grafico_diversidad_linea(
                    df_sorted,
                    x='nombre_tax',
                    y='acumulada',
                    titulo=f'Abundancia Acumulada - {tipo}'
                )
                
                if fig_linea:
                    graficos_json["grafico_acumulada"] = json.loads(fig_linea.to_json())
    
    except Exception as e:
        print(f"Error en estadística Phase 2: {e}")
        messages.warning(request, "No se pudieron calcular algunas estadísticas")

    contexto.update({
        "tipo":                   tipo,
        "top_n":                  top_n,
        "nivel":                  nivel,
        "producto_id":            variedad_id,
        "muestra_id":             muestra_id,
        "opciones_top_n":         opciones_top_n,
        "niveles_taxonomicos":    niveles_validos,
        "marcadores_disponibles": ["16S", "ITS"],
        
        # PHASE 2
        "graficos_json":           json.dumps(graficos_json),
        "estadisticas":            estadisticas,
    })

    return render(request, "analisis/analisis_avanzado.html", contexto)


@login_required
def resultado_analisis(request, muestra_id):
    try:
        contexto = obtener_analisis_avanzado(
            tipo=request.GET.get("tipo", "16S"),
            top_n=10,
            nivel="genus",
            muestra_id=muestra_id,
        )
        contexto["muestra_id"] = muestra_id
    except Exception as e:
        messages.error(request, f"No se pudo cargar el resultado de la muestra: {str(e)}")
        return redirect("analisis:analisis_avanzado")

    return render(request, "analisis/resultados.html", contexto)


@login_required
@require_POST
def exportar_analisis(request):
    from ..services.business.report_service import generar_reporte_analisis

    tipo        = request.POST.get("tipo", "16S")
    top_n       = int(request.POST.get("top_n", 10))
    nivel       = request.POST.get("nivel", "genus")
    variedad_id = request.POST.get("producto_id", None)
    formato     = request.POST.get("formato", "pdf")

    try:
        resultado = generar_reporte_analisis(
            tipo=tipo,
            top_n=top_n,
            nivel=nivel,
            producto_id=variedad_id,
            formato=formato,
            usuario=request.user,
        )
        return JsonResponse({"ok": True, "url_reporte": resultado.get("url")})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)