from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views.auth import CustomLoginView, CustomLogoutView
from .views.analysis import exportar_analisis

app_name = "analisis"

urlpatterns = [
    # 1. AUTENTICACIÓN
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", CustomLogoutView.as_view(), name="logout"),
    path("recuperar-password/", auth_views.PasswordResetView.as_view(
        template_name="account/password_reset.html",
        email_template_name="account/password_reset_email.html",
        success_url="/recuperar-password/enviado/"
    ), name="password_reset"),
    path("recuperar-password/enviado/", auth_views.PasswordResetDoneView.as_view(
        template_name="account/password_reset_done.html"
    ), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="account/password_reset_confirm.html",
        success_url="/reset/completo/"
    ), name="password_reset_confirm"),
    path("reset/completo/", auth_views.PasswordResetCompleteView.as_view(
        template_name="account/password_reset_complete.html"
    ), name="password_reset_complete"),

    # 2. DASHBOARD Y CARGA
    path("", views.dashboard, name="dashboard"),
    path("subir/", views.subir_datos, name="subir_datos"),
    path("cargar-variedades/", views.cargar_variedades, name="cargar_variedades"),

    # 3. ANÁLISIS
    path("comparar/", views.comparar, name="comparar"),
    path("analisis-avanzado/", views.analisis_avanzado, name="analisis_avanzado"),
    path("analisis-avanzado/exportar/", exportar_analisis, name="exportar_analisis"),
    path("historial/", views.historial, name="historial"),
    path("producto/<int:id>/", views.ver_producto, name="ver_producto"),

    # 4. CATÁLOGO
    path("catalogo/", views.catalogo_microorganismos, name="catalogo"),
    path("catalogo/<int:pk>/", views.detalle_microorganismo, name="detalle_microorganismo"),
    path("catalogo/<int:pk>/reclasificar/", views.actualizar_clasificacion, name="reclasificar"),

    # 5. REPORTES
    path("reportes/", views.reportes, name="reportes"),
    path("reportes/generar/", views.generar_reporte, name="generar_reporte"),
    path("reportes/<int:reporte_id>/", views.detalle_reporte, name="detalle_reporte"),
]