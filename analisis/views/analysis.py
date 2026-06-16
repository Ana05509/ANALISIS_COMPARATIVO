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
from ..services.business.statistics_service import StatisticsService as StatisticalAnalyzer
from ..models import ResultadoTaxonomico

@login_required
def analisis_avanzado(request):
    tipo        = request.GET.get("tipo", "16S")
    top_n_raw   = request.GET.get("top_n", "10")
    nivel       = request.GET.get("nivel", "genus")
    variedad_id = request.GET.get("producto_id", None)   
    muestra_id  = request.GET.get("muestra_id", None)

    opciones_top_n = [5, 10, 25, 50]
    try:
        top_n = int(top_n_raw) if int(top_n_raw) in opciones_top_n else 10
    except ValueError:
        top_n = 10

    contexto = {}
    try:
        contexto = obtener_analisis_avanzado(
            tipo=tipo, top_n=top_n, nivel=nivel, variedad_id=variedad_id, muestra_id=muestra_id
        )
        
        if "resumen" in contexto and contexto["resumen"]:
            df = pd.DataFrame(contexto["resumen"])
            
            # La columna que contiene el nombre del taxón es 'nombre_tax'
            if "nombre_tax" in df.columns:
                df["taxonomia"] = df["nombre_tax"]
            elif nivel in df.columns:
                df["taxonomia"] = df[nivel]
            else:
                # Fallback: usar el índice
                df["taxonomia"] = df.index.astype(str)
                
            # Asegurar columna de abundancia
            if "total_porcentaje" not in df.columns:
                df["total_porcentaje"] = 0.0
                
            from analisis.services.processing.diversity import DiversityService
            df_agrupado = df.groupby("taxonomia", as_index=False)["total_porcentaje"].sum()
            contexto["estadisticas"] = DiversityService.calcular_diversidad_alfa(df_agrupado)
            
        else:
            contexto["estadisticas"] = {}

    except Exception as e:
        messages.error(request, f"Error al computar los perfiles filogenéticos: {str(e)}")

    contexto.update({
        "tipo_actual": tipo,
        "top_n_actual": top_n,
        "nivel_actual": nivel,
        "opciones_top_n": opciones_top_n,
        "niveles_taxonomicos": ["kingdom", "phylum", "tax_class", "order", "family", "genus", "species"],
    })

    return render(request, "analisis/analisis_avanzado.html", contexto)


@login_required
def resultado_analisis(request, muestra_id):
    try:
        nivel = request.GET.get("nivel", "genus")
        contexto = obtener_analisis_avanzado(
            tipo=request.GET.get("tipo", "16S"),
            top_n=10,
            nivel=nivel,
            muestra_id=muestra_id,
        )
        contexto["muestra_id"] = muestra_id
        
        if "resumen" in contexto and contexto["resumen"]:
            df = pd.DataFrame(contexto["resumen"])
            
            # Aplicando el mismo fallback para evitar un KeyError en esta vista
            if "nombre_tax" in df.columns:
                df["taxonomia"] = df["nombre_tax"]
            elif nivel in df.columns:
                df["taxonomia"] = df[nivel]
            else:
                df["taxonomia"] = df.index.astype(str)

    except Exception as e:
        messages.error(request, f"No se pudo estructurar el reporte de la muestra: {str(e)}")
        return redirect("analisis:analisis_avanzado")

    return render(request, "analisis/resultados.html", contexto)


@login_required
@require_POST
def exportar_analisis(request):
    from analisis.services.business.report_generation_service import ReportGenerationService
    tipo        = request.POST.get("tipo", "16S")
    top_n       = int(request.POST.get("top_n", 10))
    nivel       = request.POST.get("nivel", "genus")
    variedad_id = request.POST.get("producto_id", None)
    formato     = request.POST.get("formato", "pdf")

    try:
        resultado = ReportGenerationService.generar_reporte_analisis( 
            tipo=tipo, variedad_id=variedad_id, formato=formato,
            top_n=top_n, nivel=nivel, usuario=request.user,
        )
        
        return JsonResponse({"ok": True, "url": resultado.get("url")})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)