from django.urls import path
from django.contrib.auth import views as auth_views # Importamos las vistas de seguridad nativas
from . import views
from .views.auth import CustomLoginView, CustomLogoutView
from analisis.views.subir_datos import cargar_variedades

app_name = "analisis"

urlpatterns = [
    # ==========================================
    # 1. AUTENTICACIÓN Y SEGURIDAD
    # ==========================================
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", CustomLogoutView.as_view(), name="logout"),

    # Flujo nativo de "Olvidé mi Contraseña"
    path("recuperar-password/", auth_views.PasswordResetView.as_view(
        template_name="account/password_reset.html", # Plantilla que diseñaremos luego
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

    # ==========================================
    # 2. DASHBOARD Y CARGA DE DATOS BIOINFORMÁTICOS
    # ==========================================
    path("", views.dashboard, name="dashboard"),
    path("subir/", views.subir_datos, name="subir_datos"),
     path('cargar-variedades/', views.cargar_variedades, name='cargar_variedades'),

    # ==========================================
    # 3. MÓDULOS DE ANÁLISIS E INTERPRETACIÓN
    # ==========================================
    path("comparar/", views.comparar, name="comparar"),
    path("analisis-avanzado/", views.analisis_avanzado, name="analisis_avanzado"),
    path("historial/", views.historial, name="historial"),
    path("producto/<int:id>/", views.ver_producto, name="ver_producto"),

    # ==========================================
    # 4. CATÁLOGO DE MICROORGANISMOS
    # ==========================================
    path("catalogo/", views.catalogo_microorganismos, name="catalogo"),
    path("catalogo/<int:pk>/", views.detalle_microorganismo, name="detalle_microorganismo"),
    path("catalogo/<int:pk>/reclasificar/", views.actualizar_clasificacion, name="reclasificar"),

    # ==========================================
    # 5. REPORTES Y EXPORTACIÓN
    # ==========================================
    path("reportes/", views.reportes, name="reportes"),
    path("reportes/generar/", views.generar_reporte, name="generar_reporte"),
    path("reportes/<int:reporte_id>/", views.detalle_reporte, name="detalle_reporte"),
    path('ajax/cargar-variedades/', cargar_variedades, name='cargar_variedades'),
]