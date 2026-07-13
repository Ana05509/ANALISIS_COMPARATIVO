import json
import plotly.express as px
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Q, Sum
from django.shortcuts import render
import pandas as pd
import numpy as np

from ..models import CatalogoMicroorganismo, MuestraSuelo, ResultadoTaxonomico
from ..services.business.analysis_service import obtener_diversidad
from analisis.constants import MARCADORES_VALIDOS

def convertir_a_serializable(obj):
    """Convierte objetos no serializables (ej. ndarray) a tipos Python nativos."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: convertir_a_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convertir_a_serializable(item) for item in obj]
    return obj

@login_required
def dashboard(request):
    tipo_raw = request.GET.get("tipo", "16S")
    tipo = tipo_raw if tipo_raw in MARCADORES_VALIDOS else "16S"
    
    contexto_estadisticas = {}
    graficos_json = {}

    try:
        # Consultas base
        analisis = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo
        ).select_related("archivo__muestra__variedad_clon").order_by("-id")

        muestras = MuestraSuelo.objects.filter(
            archivos_moleculares__tipo_analisis=tipo
        ).select_related("cultivo", "variedad_clon").distinct().order_by("-id")

        total_analisis = analisis.count()
        total_muestras = muestras.count()

        muestras_por_variedad = list(
            muestras.exclude(cultivo__isnull=True)
            .values(nombre_variedad=F("cultivo__nombre"))
            .annotate(total=Count("id"))
            .order_by("-total")
        )

        # Clasificación funcional
        conteos_funcionales = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo
        ).values("genus").annotate(total_hits=Sum("num_hits"))

        genera_list = [c["genus"] for c in conteos_funcionales if c["genus"]]
        catalogos = CatalogoMicroorganismo.objects.filter(
            nombre__in=genera_list
        ).values("nombre", "clasificacion")
        cat_dict = {c["nombre"].lower(): c["clasificacion"] for c in catalogos}

        total_beneficos = 0
        total_fitopatogenos = 0
        total_sin_clasificacion = 0

        for c in conteos_funcionales:
            genus = c["genus"] or ""
            hits = c["total_hits"] or 0
            clasif = cat_dict.get(genus.lower(), "sin_clasificar")
            if clasif == "benefico":
                total_beneficos += hits
            elif clasif == "fitopatogeno":
                total_fitopatogenos += hits
            else:
                total_sin_clasificacion += hits

        analisis_recientes = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo
        ).select_related("archivo__muestra").order_by("-id")[:5]

        # Diversidad alfa — por muestra individual, sobre todos los taxa
        contexto_estadisticas = obtener_diversidad(tipo=tipo) or {}

        # Gráficos: Top 15 géneros — grand_total sobre TODOS los taxa, no solo los 15
        todos_hits_qs = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo
        ).aggregate(grand_total=Sum('num_hits'))
        grand_total = todos_hits_qs['grand_total'] or 1

        datos_top_qs = ResultadoTaxonomico.objects.filter(
            archivo__tipo_analisis=tipo
        ).exclude(
            Q(genus__isnull=True) | Q(genus='') | Q(genus='Unclassified')
        ).values('genus').annotate(
            total_hits=Sum('num_hits')
        ).order_by('-total_hits')[:15]

        if datos_top_qs.exists():
            df_genera = pd.DataFrame(list(datos_top_qs))
            df_genera['porcentaje'] = (df_genera['total_hits'] / grand_total * 100).round(5)
            df_genera.rename(columns={'genus': 'taxonomia'}, inplace=True)

            fig_bar = px.bar(
                df_genera, x='taxonomia', y='porcentaje',
                title=f'Top 15 Géneros - {tipo}',
                labels={'taxonomia': 'Género', 'porcentaje': 'Abundancia relativa (%)'},
            )
            fig_bar.update_layout(
                xaxis=dict(tickangle=-45, automargin=True, tickfont=dict(size=10)),
                margin=dict(b=160, t=60, l=60, r=20),
                height=480,
            )

            fig_pie = px.pie(
                df_genera, names='taxonomia', values='porcentaje',
                title=f'Distribución de Abundancia - {tipo}',
            )
            fig_pie.update_layout(height=400)

            graficos_json['grafico_barras'] = convertir_a_serializable(fig_bar.to_dict())
            graficos_json['grafico_pie']    = convertir_a_serializable(fig_pie.to_dict())

    except Exception as e:
        import traceback
        traceback.print_exc()
        messages.error(request, f"Error crítico: {str(e)}")
        return render(request, "analisis/dashboard.html", {"error_critico": True})

    return render(request, "analisis/dashboard.html", {
        "analisis": analisis,
        "analisis_recientes": analisis_recientes,
        "productos": muestras,
        "total_analisis": total_analisis,
        "total_productos": total_muestras,
        "total_beneficos": total_beneficos,
        "total_fitopatogenos": total_fitopatogenos,
        "total_sin_clasificacion": total_sin_clasificacion,
        "productos_por_variedad": muestras_por_variedad,
        "tipo_actual": tipo,
        "marcadores_disponibles": MARCADORES_VALIDOS,
        "graficos_json": json.dumps(graficos_json, default=str),  # default=str asegura serialización
        "estadisticas": contexto_estadisticas,
        "es_estudiante": request.user.rol == 'estudiante',
    })