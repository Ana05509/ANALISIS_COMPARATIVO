import json
import os
from pathlib import Path
import pandas as pd

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Q, Sum
from django.shortcuts import render

from ..models import CatalogoMicroorganismo, MuestraSuelo, ResultadoTaxonomico
from ..services.business.statistics_service import StatisticsService
from ..services.business.visualization_service import VisualizationService

MARCADORES_VALIDOS = ("16S", "ITS")

@login_required
def dashboard(request):
    """
    Vista principal del dashboard de análisis microbianos.
    Adaptado para discriminar qué ve un estudiante de agronomía frente a un administrador.
    """
    tipo_raw = request.GET.get("tipo", "16S")
    tipo = tipo_raw if tipo_raw in MARCADORES_VALIDOS else "16S"

    try:
        analisis = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo
        ).select_related("archivo__muestra__variedad_clon").order_by("-id")

        muestras = MuestraSuelo.objects.filter(
            archivos_moleculares__tipo_analisis=tipo
        ).select_related("cultivo", "variedad_clon").distinct().order_by("-id")

        total_analisis = analisis.count()
        total_muestras  = muestras.count()

        muestras_por_variedad = list(
            muestras.values(nombre_variedad=F("variedad_clon__nombre"))
            .annotate(total=Count("id"))
            .order_by("-total")
        )

        conteos_funcionales = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo
        ).values("genus").annotate(total_hits=Sum("num_hits"))

        genera_list = [c["genus"] for c in conteos_funcionales if c["genus"]]
        catalogos = CatalogoMicroorganismo.objects.filter(nombre__in=genera_list).values("nombre", "clasificacion")
        cat_dict = {c["nombre"]: c["clasificacion"] for c in catalogos}

        total_beneficos = 0
        total_fitopatogenos = 0
        total_sin_clasificacion = 0

        for c in conteos_funcionales:
            genus = c["genus"]
            hits = c["total_hits"] or 0
            clasif = cat_dict.get(genus, "sin_clasificar")
            if clasif == "benefico":
                total_beneficos += hits
            elif clasif == "fitopatogeno":
                total_fitopatogenos += hits
            else:
                total_sin_clasificacion += hits

        analisis_recientes = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo
        ).select_related("archivo__muestra").order_by("-id")[:5]

        # --- GENERACIÓN DE GRÁFICOS INTERACTIVOS (FASE 2) ---
        graficos_json = {}
        try:
            raw_data = list(ResultadoTaxonomico.objects.filter(
                archivo__tipo_analisis=tipo
            ).values("genus", "porcentaje_hits"))
            
            if raw_data:
                df_genera = pd.DataFrame(raw_data).groupby("genus", as_index=False).sum()
                df_genera = df_genera.sort_values(by="porcentaje_hits", ascending=False).head(15)
                df_genera.rename(columns={"porcentaje_hits": "total_porcentaje"}, inplace=True)

                viz = VisualizationService()
                
                # Gráfico de barras
                fig_barras = viz.crear_grafico_abundancia_barras(
                    df_genera,
                    x="genus",
                    y="total_porcentaje",
                    titulo=f"Top 15 Géneros más Abundantes - {tipo}"
                )
                if fig_barras is not None:
                    graficos_json["grafico_barras"] = json.loads(str(fig_barras))
                
                # Gráfico de pastel
                fig_pie = viz.crear_grafico_abundancia_pie(
                    df_genera,
                    nombres="genus",
                    valores="total_porcentaje",
                    titulo=f"Distribución de Abundancia - {tipo}"
                )
                if fig_pie is not None:
                    graficos_json["grafico_pie"] = json.loads(str(fig_pie))
        
        except Exception as e:
            print(f"Error generando gráficos: {e}")
            messages.warning(request, "No se pudieron generar algunos gráficos interactivos debido a la data.")

    except Exception as e:
        messages.error(request, f"Error crítico al cargar el dashboard: {str(e)}")
        return render(request, "analisis/dashboard.html", {"error_critico": True})

    return render(request, "analisis/dashboard.html", {
        "analisis":              analisis,
        "analisis_recientes":    analisis_recientes,
        "productos":             muestras,
        "total_analisis":        total_analisis,
        "total_productos":       total_muestras,
        "total_beneficos":         total_beneficos,
        "total_fitopatogenos":     total_fitopatogenos,
        "total_sin_clasificacion": total_sin_clasificacion,
        "productos_por_variedad":  muestras_por_variedad,
        "tipo_actual":            tipo,
        "marcadores_disponibles":  MARCADORES_VALIDOS,
        "graficos_json":           json.dumps(graficos_json),
        "es_estudiante":           request.user.rol == 'estudiante', # Bandera para ocultar celdas en el template
    })