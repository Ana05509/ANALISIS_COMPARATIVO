from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from allauth.core.ratelimit import consume_or_429

class CustomLoginView(LoginView):
    """
    Vista de login personalizada usando el template en templates/registration/login.html

    Usa el LoginView nativo de Django (no el de allauth) para conservar
    nuestro template/formulario propios. Eso significa que la protección
    contra fuerza bruta que allauth trae de fábrica (ACCOUNT_RATE_LIMITS)
    NO se aplica aquí automáticamente, así que se reutiliza manualmente
    el mismo limitador que ya usa allauth internamente — sin límite,
    cualquiera podría probar contraseñas sin freno alguno contra /login/.
    """
    template_name = 'account/login.html'

    def post(self, request, *args, **kwargs):
        bloqueado = consume_or_429(request, action="login")
        if bloqueado is not None:
            return bloqueado
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        # Clave por el username/email tal como se envió, no por cleaned_data:
        # si la autenticación falla, el form puede no llegar a poblar cleaned_data.
        intentado = form.data.get('username', '')
        bloqueado = consume_or_429(self.request, action="login_failed", key=intentado)
        if bloqueado is not None:
            return bloqueado
        return super().form_invalid(form)

class CustomLogoutView(LogoutView):
    """Vista de logout personalizada"""
    next_page = reverse_lazy('analisis:login')
