import json
import os
from pathlib import Path
import pandas as pd

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Q, Sum
from django.shortcuts import render

from ..models import CatalogoMicroorganismo, MuestraSuelo, ResultadoTaxonomico
from ..services.business.statistics_service import StatisticalAnalyzer
from ..services.business.visualization_service import VisualizationService

MARCADORES_VALIDOS = ("16S", "ITS")


@login_required
def dashboard(request):
    """
    Vista principal del dashboard de análisis microbianos.

    Relacionado con le README:
      - "Gestión de Muestras Agrícolas": listado de muestras y variedades registradas.
      - "Rankings de Abundancia": métricas rápidas de los análisis existentes.
      - "Clasificación Funcional": conteo de Benéficos ✅, Fitopatógenos ⚠️, Sin clasificación ⚪.
    """
    tipo_raw = request.GET.get("tipo", "16S")
    tipo = tipo_raw if tipo_raw in MARCADORES_VALIDOS else "16S"

    try:
        # OPTIMIZACIÓN 1: select_related() para evitar queries de ForeignKey
        # Precarga: ArchivoMolecular → MuestraSuelo → VariedadClon
        analisis = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo
        ).select_related(
            "archivo",
            "archivo__muestra",
            "archivo__muestra__variedad_clon"
        ).order_by("-id")

        # CORRECCIÓN DE FILTRO: Se remueve la restricción estricta de 'archivomolecular__tipo_analisis'
        # para permitir que el dashboard muestre los cultivos y clones creados en el admin,
        # incluso antes de que se cargue su primer archivo secuenciado.
        muestras = MuestraSuelo.objects.select_related("variedad_clon").distinct().order_by("-id")

    except Exception as e:
        messages.error(request, f"Error al cargar los datos del dashboard: {str(e)}")
        analisis = ResultadoTaxonomico.objects.none()
        muestras = MuestraSuelo.objects.none()

    # OPTIMIZACIÓN 3: Usar values_list() con flat=True + list() para una sola query
    nombres_analisis_list = list(analisis.values_list("genus", flat=True).distinct())
    
    # OPTIMIZACIÓN 4: Una sola query con aggregation en lugar de 3 queries separadas
    clasificaciones_stats = CatalogoMicroorganismo.objects.filter(
        nombre__in=nombres_analisis_list
    ).aggregate(
        total_beneficos=Count("id", filter=Q(clasificacion="benefico")),
        total_fitopatogenos=Count("id", filter=Q(clasificacion="fitopatogeno")),
        total_sin_clasificacion=Count("id", filter=Q(clasificacion="sin_clarificar"))
    )
    
    # OPTIMIZACIÓN 5: Extraer valores agregados (reduce 3 queries a 1)
    total_beneficos = clasificaciones_stats.get("total_beneficos", 0) or 0
    total_fitopatogenos = clasificaciones_stats.get("total_fitopatogenos", 0) or 0
    total_sin_clasificacion = clasificaciones_stats.get("total_sin_clasificacion", 0) or 0
    
    # OPTIMIZACIÓN 6: Contar con annotate en lugar de .count() por separado
    total_analisis = analisis.count()  
    total_muestras = muestras.count()  
    analisis_recientes = analisis[:5]

    # OPTIMIZACIÓN 7: Usar values() + annotate() para agregación por grupo
    muestras_por_variedad = (
        muestras.values("variedad_clon__nombre")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    # ========== PHASE 2: GRÁFICOS INTERACTIVOS ==========
    # CORRECCIÓN DE INICIALIZACIÓN: Se estructuran las llaves por defecto como 'None' 
    # para evitar que JavaScript o los servicios de reporte rompan la ejecución si la BD está vacía.
    graficos_json = {
        "grafico_barras": None,
        "grafico_pie": None
    }
    
    try:
        # CORRECCIÓN POSTGRESQL: Cambiamos la anotación a 'nombre_genus' para evitar el conflicto con el campo real
        top_genera = (
            analisis.values(nombre_genus=F("genus"))
            .annotate(
                total_hits=Sum("num_hits"),
                total_porcentaje=Sum("porcentaje_hits")
            )
            .order_by("-total_porcentaje")[:10]
        )
        
        if top_genera.exists():
            df_genera = pd.DataFrame(list(top_genera))
            
            # CONTROL DE NULOS POSTGRESQL: Reemplazar valores nulos (None/NaN) con 0
            df_genera["total_porcentaje"] = df_genera["total_porcentaje"].fillna(0)
            df_genera["total_hits"] = df_genera["total_hits"].fillna(0)
            
            # CORRECCIÓN DE COLUMNAS: Ajustamos el renombrado usando la nueva columna 'nombre_genus' para mantener compatibilidad
            df_genera.rename(columns={"nombre_genus": "genus"}, inplace=True)
            
            viz = VisualizationService()
            
            # Gráfico de barras
            fig_barras = viz.crear_grafico_abundancia_barras(
                df_genera, 
                x="genus", 
                y="total_porcentaje",
                titulo=f"Top 10 Géneros - {tipo}",
                color="total_porcentaje"
            )
            # CORRECCIÓN PYLANCE: Validación explícita de nulidad y casteo a string seguro
            if fig_barras is not None:
                graficos_json["grafico_barras"] = json.loads(str(fig_barras))
            
            # Gráfico de pastel
            fig_pie = viz.crear_grafico_abundancia_pie(
                df_genera,
                nombres="genus",
                valores="total_porcentaje",
                titulo=f"Distribución de Abundancia - {tipo}"
            )
            # CORRECCIÓN PYLANCE: Validación explícita de nulidad y casteo a string seguro
            if fig_pie is not None:
                graficos_json["grafico_pie"] = json.loads(str(fig_pie))
    
    except Exception as e:
        print(f"Error generando gráficos: {e}")
        messages.warning(request, "No se pudieron generar algunos gráficos interactivos")

    return render(request, "analisis/dashboard.html", {
        "analisis":              analisis,
        "analisis_recientes":    analisis_recientes,
        "productos":             muestras,          # alias para compatibilidad con template

        "total_analisis":        total_analisis,
        "total_productos":       total_muestras,

        "total_beneficos":         total_beneficos,
        "total_fitopatogenos":     total_fitopatogenos,
        "total_sin_clasificacion": total_sin_clasificacion,

        "productos_por_variedad":  muestras_por_variedad,

        "tipo_actual":             tipo,
        "marcadores_disponibles":  MARCADORES_VALIDOS,
        
        # PHASE 2
        "graficos_json":           json.dumps(graficos_json),
    })
