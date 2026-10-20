from django.urls import path
from . import views
from .views.auth import CustomLoginView, CustomLogoutView
from .views.analysis import resultado_analisis
from .views.api import (
    api_muestras, api_muestra_detalle,
    api_catalogo, api_catalogo_entrada,
    api_estadisticas,
)

app_name = "analisis"

urlpatterns = [
    # 1. AUTENTICACIÓN
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", CustomLogoutView.as_view(), name="logout"),
    # Textos legales (públicos) y aceptación obligatoria para cuentas que aún no aceptaron
    path("terminos/", views.terminos, name="terminos"),
    path("privacidad/", views.privacidad, name="privacidad"),
    path("aceptar-terminos/", views.aceptar_terminos, name="aceptar_terminos"),
    # La recuperación de contraseña la maneja allauth (accounts/password/reset/...),
    # que ya cuenta con sus propias plantillas (account/password_reset*.html).

    # 2. DASHBOARD Y CARGA
    path("dashboard/", views.dashboard, name="dashboard"),
    path("perfil/", views.perfil_usuario, name="perfil"),
    path("subir/", views.subir_datos, name="subir_datos"),
    path("cargar-variedades/", views.cargar_variedades, name="cargar_variedades"),

    # 3. ANÁLISIS
    path("comparar/", views.comparar, name="comparar"),
    path("analisis-avanzado/", views.analisis_avanzado, name="analisis_avanzado"),
    path("historial/", views.historial, name="historial"),
    path("producto/<int:id>/", views.ver_producto, name="ver_producto"),
    path("muestra/<int:muestra_id>/resultados/", resultado_analisis, name="resultado_analisis"),

    # 4. CATÁLOGO
    path("catalogo/", views.catalogo_microorganismos, name="catalogo"),
    path("catalogo/importar/", views.importar_catalogo, name="importar_catalogo"),    path("catalogo/<int:pk>/reclasificar/", views.actualizar_clasificacion, name="reclasificar"),

    # 5. AYUDA
    path("ayuda/", views.ayuda, name="ayuda"),

    # 6. REPORTES
    path("reportes/", views.reportes, name="reportes"),
    path("reportes/generar/", views.generar_reporte, name="generar_reporte"),
    path("reportes/generar-general/", views.generar_reporte_general, name="generar_reporte_general"),

    # 6. API REST v1 — Solo lectura, respuestas JSON
    path("api/v1/muestras/",                    api_muestras,          name="api_muestras"),
    path("api/v1/muestras/<int:pk>/",           api_muestra_detalle,   name="api_muestra_detalle"),
    path("api/v1/catalogo/",                    api_catalogo,          name="api_catalogo"),
    path("api/v1/catalogo/<str:nombre>/",       api_catalogo_entrada,  name="api_catalogo_entrada"),
    path("api/v1/estadisticas/",                api_estadisticas,      name="api_estadisticas"),
]