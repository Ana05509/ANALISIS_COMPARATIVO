import json
import pandas as pd
from typing import Any, Dict, List, cast

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseBase
from django.views.decorators.http import require_POST

# Importaciones Locales del Módulo usando rutas absolutas para robustez
from analisis.models import MuestraSuelo

# Servicios de Negocio - Arquitectura de Capas Estabilizada
from analisis.services.business.comparison_service import ejecutar_comparacion_clean
from analisis.services.business.visualization_service import VisualizationService
from analisis.services.business.statistics_service import StatisticsService
from analisis.services.business.export_service import ExportService
from analisis.services.business.report_generation_service import ReportGenerationService


MARCADORES_VALIDOS = ("16S", "ITS")
FORMATOS_VALIDOS = ("pdf", "excel", "html", "json")


def _contar_clasificaciones(tabla: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Helper para procesar el conteo de clasificaciones funcionales de microorganismos.
    """
    conteo = {"benefico": 0, "fitopatogeno": 0, "sin_clasificar": 0}
    for fila in tabla:
        clave = fila.get("clasificacion", "sin_clasificar")
        if clave in conteo:
            conteo[clave] += 1
    return conteo

@login_required
def comparar(request):
    """
    Vista de comparación actualizada para consumir la estructura 
    retornada por ejecutar_comparacion_clean.
    """
    from analisis.forms import CompararForm

    form = CompararForm(request.GET or None)
    contexto: Dict[str, Any] = {
        "form": form,
        "marcador_seleccionado": None,
        "tabla_comparativa": [],
        "graficos_json": "{}",
        "conteo_clasificaciones": {"benefico": 0, "fitopatogeno": 0, "sin_clasificar": 0},
        "exclusivos_m1": [],
        "exclusivos_m2": [],
    }

    if request.GET and form.is_valid():
        muestra_1 = form.cleaned_data.get("muestra_1")
        muestra_2 = form.cleaned_data.get("muestra_2")
        marcador  = form.cleaned_data.get("marcador")

        if muestra_1 and muestra_2:
            contexto["marcador_seleccionado"] = marcador

            try:
                # RECEPTOR DE ESTRUCTURA: Recibe el diccionario completo del servicio
                resultado_comp = ejecutar_comparacion_clean(form.cleaned_data)
                
                # Transformación de datos adaptada a la nueva estructura
                tabla_datos = resultado_comp.get("tabla", [])
                
                if tabla_datos:
                    # Convertimos la lista de dicts a DataFrame para las visualizaciones
                    df_comp = pd.DataFrame(tabla_datos)
                    
                    contexto["tabla_comparativa"] = tabla_datos
                    contexto["conteo_clasificaciones"] = _contar_clasificaciones(tabla_datos)
                    
                    # Asignación de exclusivos (ajustar lógica según cómo el servicio los entregue)
                    exclusivos = resultado_comp.get("exclusivos", [])
                    # Si 'exclusivos' llega como lista única, distribuimos; 
                    # si viene como dict, asigna directamente según clave.
                    contexto["exclusivos_m1"] = exclusivos[:len(exclusivos)//2] 
                    contexto["exclusivos_m2"] = exclusivos[len(exclusivos)//2:]

                    # Renderizado de Gráficos
                    viz_service = VisualizationService()
                    fig = viz_service.crear_grafico_comparativo_barras(
                        df_comp, 
                        muestra_1_nombre=str(muestra_1.codigo), 
                        muestra_2_nombre=str(muestra_2.codigo)
                    )
                    if fig is not None:
                        contexto["graficos_json"] = json.dumps(json.loads(str(fig)))

                else:
                    messages.info(request, "No se encontraron taxones coincidentes bajo los filtros estipulados.")

            except Exception as e:
                messages.error(request, f"Error en el procesamiento comparativo: {str(e)}")
        else:
            messages.error(request, "Las muestras seleccionadas no son válidas.")

    return render(request, "analisis/comparar.html", contexto)

@require_POST
def exportar_reporte_comparativo(request) -> HttpResponseBase:
    """
    Exportación polimórfica de los resultados de la comparación.
    Garantiza retornar un HttpResponseBase estricto para satisfacer a Pylance y @login_required.
    """
    try:
        tipo         = request.POST.get("marcador", "16S")
        nivel        = request.POST.get("nivel", "genus")
        formato      = request.POST.get("formato", "pdf")
        top_n        = int(request.POST.get("top_n", 10))
        variedad_id  = request.POST.get("producto_id", None)

        if formato not in FORMATOS_VALIDOS:
            return JsonResponse({"ok": False, "error": "Formato de exportación inválido"}, status=400)

        # Dataset vacío base para el reporte
        df_reporte = pd.DataFrame() 

        if formato == "html":
            html_puro = ExportService.generar_html_reporte(
                df_reporte.to_html(classes="table table-striped"),
                f"reporte_{tipo}_{nivel}.html"
            )
            # CORRECCIÓN PYLANCE: Retornar HttpResponse puro encapsulando el texto, nunca un str directo
            return HttpResponse(str(html_puro), content_type="text/html")

        elif formato == "pdf":
            response = ExportService.exportar_pdf_response(
                titulo=f"Reporte Comparativo {tipo}",
                datos_analisis={},
                df_datos=df_reporte,
                usuario=request.user
            )
            return response

        elif formato == "json":
            json_response = ExportService.exportar_json(
                df_reporte.to_dict('records'),
                nombre_archivo=f"reporte_comparativo_{tipo}_{nivel}.json"
            )
            return json_response

        else:
            
            resultado = ReportGenerationService.generar_reporte_analisis(
                tipo=tipo, variedad_id=variedad_id, formato=formato,
                top_n=top_n, nivel=nivel, usuario=request.user,
            )
            return JsonResponse({"ok": True, "url_reporte": resultado.get("url")})

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)