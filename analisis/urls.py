from django.urls import path
from . import views

app_name = "analisis"

urlpatterns = [
    # Dashboard principal
    path("", views.dashboard, name="dashboard"),

    # Carga de archivos 16S / ITS
    path("subir/", views.subir_datos, name="subir_datos"),

    # Comparación de perfiles
    path("comparar/", views.comparar, name="comparar"),

    # Historial de muestras
    path("historial/", views.historial, name="historial"),

    # Detalle de muestra/producto
    path("producto/<int:id>/", views.ver_producto, name="ver_producto"),

    # Análisis avanzado
    path("analisis-avanzado/", views.analisis_avanzado, name="analisis_avanzado"),

    # Catálogo de microorganismos
    path("catalogo/", views.catalogo_microorganismos, name="catalogo"),
    path("catalogo/<int:pk>/", views.detalle_microorganismo, name="detalle_microorganismo"),
    path("catalogo/<int:pk>/reclasificar/", views.actualizar_clasificacion, name="reclasificar"),

    # Reportes
    path("reportes/", views.reportes, name="reportes"),
    path("reportes/generar/", views.generar_reporte, name="generar_reporte"),
    path("reportes/<int:reporte_id>/", views.detalle_reporte, name="detalle_reporte"),
]