from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.i18n import JavaScriptCatalog
from django.views.generic import RedirectView
from analisis.views.manual_admin import manual_admin_view

urlpatterns = [
    path('admin/manual/', admin.site.admin_view(manual_admin_view), name='admin-manual'),
    path('admin/', admin.site.urls),
    # Redirigir la URL de login de allauth a nuestra vista personalizada
    path('accounts/login/', RedirectView.as_view(url='/login/', permanent=False)),
    path('accounts/', include('allauth.urls')),
    path('', include('portal.urls')),
    path('', include('analisis.urls')),
    path('bioquimica/', include('bioquimica.urls')),
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),
]

# Se sirve siempre (no solo con DEBUG=True): Railway no tiene nginx/S3
# delante como en un despliegue tradicional, así que Django es el único
# que puede responder /media/ también en producción — si esto se dejara
# solo para DEBUG, avatars/ y cultivos/ (subidos al repo) darían 404 en Railway.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)