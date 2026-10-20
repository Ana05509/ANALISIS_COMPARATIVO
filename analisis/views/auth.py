from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from allauth.core import ratelimit
from allauth.core.ratelimit import consume_or_429

from analisis import seguridad


class CustomLoginView(LoginView):
    """
    Vista de login personalizada usando el template en templates/registration/login.html

    Usa el LoginView nativo de Django (no el de allauth) para conservar
    nuestro template/formulario propios. Eso significa que la protección
    contra fuerza bruta que allauth trae de fábrica (ACCOUNT_RATE_LIMITS)
    NO se aplica aquí automáticamente, así que se reutiliza manualmente
    el mismo limitador que ya usa allauth internamente (por IP) y, encima,
    el bloqueo por cuenta de analisis.seguridad: 3 intentos fallidos con un
    mismo correo bloquean el acceso 15 minutos, también con la contraseña
    correcta, y el usuario ve cuántos intentos le quedan.
    """
    template_name = 'account/login.html'

    def _correo(self):
        return self.request.POST.get('username', '')

    def _respuesta_bloqueo(self, minutos):
        form = self.get_form_class()(self.request, initial={'username': self._correo()})
        contexto = self.get_context_data(
            form=form,
            bloqueo_minutos=minutos,
            bloqueo_intentos=seguridad.INTENTOS_MAXIMOS,
        )
        return self.render_to_response(contexto, status=429)

    def post(self, request, *args, **kwargs):
        bloqueado = consume_or_429(request, action="login")
        if bloqueado is not None:
            return bloqueado
        # Se comprueba ANTES de autenticar: durante el bloqueo no se acepta
        # ninguna contraseña, ni siquiera la correcta.
        minutos = seguridad.minutos_bloqueo_restantes(self._correo())
        if minutos:
            return self._respuesta_bloqueo(minutos)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        seguridad.limpiar_fallos(self._correo())
        ratelimit.clear(self.request, action="login_failed", key=self._correo())
        return super().form_valid(form)

    def form_invalid(self, form):
        # Clave por el username/email tal como se envió, no por cleaned_data:
        # si la autenticación falla, el form puede no llegar a poblar cleaned_data.
        intentado = form.data.get('username', '')
        bloqueado = consume_or_429(self.request, action="login_failed", key=intentado)
        if bloqueado is not None:
            return bloqueado

        restantes = seguridad.registrar_fallo(intentado)
        if restantes == 0:
            return self._respuesta_bloqueo(seguridad.MINUTOS_BLOQUEO)
        return self.render_to_response(self.get_context_data(
            form=form,
            intentos_restantes=restantes if intentado.strip() else None,
            bloqueo_tras=seguridad.MINUTOS_BLOQUEO,
        ))


class CustomLogoutView(LogoutView):
    """Vista de logout personalizada"""
    next_page = reverse_lazy('analisis:login')
