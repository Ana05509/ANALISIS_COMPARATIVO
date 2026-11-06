import os
import posixpath

from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.urls import path, re_path, include
from django.conf import settings
from django.views.i18n import JavaScriptCatalog
from django.views.generic import RedirectView
from django.views.static import serve as serve_media
from analisis.permisos import puede_cargar_datos
from analisis.views.manual_admin import manual_admin_view

urlpatterns = [
    path('admin/manual/', admin.site.admin_view(manual_admin_view), name='admin-manual'),
    # El login propio del admin no tiene límite de intentos: se redirige al
    # login de la plataforma (bloqueo tras 3 fallos), conservando ?next=
    path('admin/login/', RedirectView.as_view(url='/login/', query_string=True, permanent=False)),
    path('admin/', admin.site.urls),
    # Redirigir la URL de login de allauth a nuestra vista personalizada
    path('accounts/login/', RedirectView.as_view(url='/login/', permanent=False)),
    path('accounts/', include('allauth.urls')),
    path('', include('portal.urls')),
    path('', include('analisis.urls')),
    path('bioquimica/', include('bioquimica.urls')),
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),
]

# Archivos /media/ servidos por Django también en producción, con sesión obligatoria;
# los originales de laboratorio solo para Docente/Investigador/Admin.
_MEDIA_RESTRINGIDA = ('bioquimica_pdfs/', 'archivos_moleculares/')
_MEDIA_INLINE = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}


@login_required
def media_protegida(request, path):
    # Autorizar el mismo destino normalizado que se entrega al servidor de archivos.
    path = posixpath.normpath(path.replace('\\', '/')).lstrip('/')
    if path == '..' or path.startswith('../'):
        raise PermissionDenied
    if path.casefold().startswith(_MEDIA_RESTRINGIDA) and not puede_cargar_datos(request.user):
        raise PermissionDenied
    response = serve_media(request, path, document_root=settings.MEDIA_ROOT)
    # Lo que no es imagen se descarga en vez de abrirse en el navegador.
    if os.path.splitext(path)[1].lower() not in _MEDIA_INLINE:
        response['Content-Disposition'] = 'attachment'
    return response


urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', media_protegida),
]