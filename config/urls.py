import os

from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.urls import path, re_path, include
from django.conf import settings
from django.views.i18n import JavaScriptCatalog
from django.views.generic import RedirectView
from django.views.static import serve as serve_media
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

# No se usa django.conf.urls.static.static(): esa función trae su propio
# chequeo de DEBUG incrustado y devuelve [] si DEBUG=False, sin importar
# si esto se envuelve o no en un "if settings.DEBUG". Se registra la vista
# django.views.static.serve directamente para que funcione también en
# producción — Railway no tiene nginx/S3 delante para servir /media/.
#
# Antes se servía sin ningún control: cualquiera sin sesión podía bajar
# /media/bioquimica_pdfs/<codigo>.pdf o /media/archivos_moleculares/...
# con solo adivinar el nombre (los nombres son predecibles: código del
# ensayo / código de muestra). Ahora exige sesión, y los originales de
# laboratorio quedan solo para Docente/Investigador/Admin — mismo criterio
# que bioquimica.views.ver_pdf.
_MEDIA_RESTRINGIDA = ('bioquimica_pdfs/', 'archivos_moleculares/')
_MEDIA_INLINE = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}


@login_required
def media_protegida(request, path):
    if path.startswith(_MEDIA_RESTRINGIDA) and getattr(request.user, 'rol', None) == 'estudiante':
        raise PermissionDenied
    response = serve_media(request, path, document_root=settings.MEDIA_ROOT)
    # Todo lo que no sea imagen se descarga en vez de abrirse en el
    # navegador: un .html/.svg subido como "adjunto" no debe poder
    # ejecutarse con el origen (y las cookies) de la app.
    if os.path.splitext(path)[1].lower() not in _MEDIA_INLINE:
        response['Content-Disposition'] = 'attachment'
    return response


urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', media_protegida),
]