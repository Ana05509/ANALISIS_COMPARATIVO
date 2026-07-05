from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.i18n import JavaScriptCatalog
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Redirigir la URL de login de allauth a nuestra vista personalizada
    path('accounts/login/', RedirectView.as_view(url='/login/', permanent=False)),
    path('accounts/', include('allauth.urls')),
    path('', include('portal.urls')),
    path('', include('analisis.urls')),
    path('bioquimica/', include('bioquimica.urls')),
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)