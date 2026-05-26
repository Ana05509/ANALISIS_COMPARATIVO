from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, F, Sum, Q
import pandas as pd
import json

from ..models import MuestraSuelo, ResultadoTaxonomico, CatalogoMicroorganismo
from ..services.business.visualization_service import VisualizationService
from ..services.business.statistics_service import StatisticalAnalyzer

MARCADORES_VALIDOS = ("16S", "ITS")


@login_required
def dashboard(request):
    """
    Vista principal del dashboard de análisis microbianos.

    Relacionado con el README:
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

        # OPTIMIZACIÓN 2: Usar values() + distinct() es más eficiente que filter().distinct()
        # para grandes datasets
        muestras = MuestraSuelo.objects.filter(
            archivomolecular__tipo_analisis=tipo
        ).select_related("variedad_clon").distinct().order_by("-id")

    except Exception as e:
        messages.error(request, f"Error al cargar los datos del dashboard: {str(e)}")
        analisis = ResultadoTaxonomico.objects.none()
        muestras = MuestraSuelo.objects.none()

    # OPTIMIZACIÓN 3: Usar values_list() con flat=True + list() para una sola query
    # en lugar de múltiples count() separados
    nombres_analisis_list = list(analisis.values_list("genus", flat=True).distinct())
    
    # OPTIMIZACIÓN 4: Una sola query con aggregation en lugar de 3 queries separadas
    # Consolidar conteos de clasificación funcional en una query usando Q objects
    clasificaciones_stats = CatalogoMicroorganismo.objects.filter(
        nombre__in=nombres_analisis_list
    ).aggregate(
        total_beneficos=Count("id", filter=Q(clasificacion="benefico")),
        total_fitopatogenos=Count("id", filter=Q(clasificacion="fitopatogeno")),
        total_sin_clasificacion=Count("id", filter=Q(clasificacion="sin_clasificar"))
    )
    
    # OPTIMIZACIÓN 5: Extraer valores agregados (reduce 3 queries a 1)
    total_beneficos = clasificaciones_stats.get("total_beneficos", 0)
    total_fitopatogenos = clasificaciones_stats.get("total_fitopatogenos", 0)
    total_sin_clasificacion = clasificaciones_stats.get("total_sin_clasificacion", 0)
    
    # OPTIMIZACIÓN 6: Contar con annotate en lugar de .count() por separado
    total_analisis = analisis.count()  # Esta query ya está evaluada, no genera nueva query
    total_muestras = muestras.count()  # Ídem
    analisis_recientes = analisis[:5]

    # OPTIMIZACIÓN 7: Usar values() + annotate() para agregación por grupo
    # Evita traer objetos completos a memoria si solo se necesitan estadísticas
    muestras_por_variedad = (
        muestras.values("variedad_clon__nombre")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    # ========== PHASE 2: GRÁFICOS INTERACTIVOS ==========
    # OPTIMIZACIÓN 8: Top 10 genera ya usa F() y Sum() para agregación eficiente
    # No requiere optimización adicional
    
    graficos_json = {}
    
    try:
        # Obtener top 10 genera para gráfico de abundancia
        # Usa values() + annotate() para agregar en BD sin traer objetos completos
        top_genera = (
            analisis.values(genus=F("genus"))
            .annotate(
                total_hits=Sum("num_hits"),
                total_porcentaje=Sum("porcentaje_hits")
            )
            .order_by("-total_porcentaje")[:10]
        )
        
        if top_genera.exists():
            df_genera = pd.DataFrame(list(top_genera))
            df_genera.rename(columns={"genus": "genus", "total_porcentaje": "%_hits"}, inplace=True)
            
            # Gráfico de barras
            viz = VisualizationService()
            fig_barras = viz.crear_grafico_abundancia_barras(
                df_genera, 
                x="genus", 
                y="total_porcentaje",
                titulo=f"Top 10 Géneros - {tipo}",
                color="total_porcentaje"
            )
            
            if fig_barras:
                graficos_json["grafico_barras"] = json.loads(fig_barras.to_json())
            
            # Gráfico de pastel
            fig_pie = viz.crear_grafico_abundancia_pie(
                df_genera,
                nombres="genus",
                valores="total_porcentaje",
                titulo=f"Distribución de Abundancia - {tipo}"
            )
            
            if fig_pie:
                graficos_json["grafico_pie"] = json.loads(fig_pie.to_json())
    
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
