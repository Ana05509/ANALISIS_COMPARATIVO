from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.views.i18n import JavaScriptCatalog
from django.views.generic import RedirectView
from django.views.static import serve as serve_media
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

# No se usa django.conf.urls.static.static(): esa función trae su propio
# chequeo de DEBUG incrustado y devuelve [] si DEBUG=False, sin importar
# si esto se envuelve o no en un "if settings.DEBUG". Se registra la vista
# django.views.static.serve directamente para que funcione también en
# producción — Railway no tiene nginx/S3 delante para servir /media/.
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve_media, {'document_root': settings.MEDIA_ROOT}),
]