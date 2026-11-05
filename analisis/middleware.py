from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from analisis import seguridad


class TerminosMiddleware:
    """Redirige a /aceptar-terminos/ a los usuarios que no aceptaron la versión vigente
    de los Términos y la Política de privacidad."""

    _PREFIJOS_LIBRES = ("/accounts/", "/api/", "/jsi18n/", "/csp-report/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not self._ruta_libre(request.path):
            if not seguridad.acepto_terminos(request):
                destino = urlencode({"next": request.get_full_path()})
                return redirect(f"{reverse('analisis:aceptar_terminos')}?{destino}")
        return self.get_response(request)

    def _ruta_libre(self, ruta):
        libres = {
            reverse("analisis:aceptar_terminos"),
            reverse("analisis:terminos"),
            reverse("analisis:privacidad"),
            reverse("analisis:logout"),
            reverse("analisis:login"),
        }
        return (
            ruta in libres
            or ruta.startswith(self._PREFIJOS_LIBRES)
            or ruta.startswith((settings.STATIC_URL, settings.MEDIA_URL))
        )
