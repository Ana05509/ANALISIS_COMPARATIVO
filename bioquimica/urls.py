from django.urls import path
from . import views

app_name = 'bioquimica'

urlpatterns = [
    path('', views.lista_ensayos, name='lista'),
    path('subir/', views.subir_pdf, name='subir_pdf'),
    path('<int:pk>/', views.detalle_ensayo, name='detalle'),
]
