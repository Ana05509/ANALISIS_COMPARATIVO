import re
import dns.resolver
from difflib import SequenceMatcher
from django.core.exceptions import ValidationError
from allauth.account.adapter import DefaultAccountAdapter

# Patrón estricto: local@dominio.tld — rechaza comas, espacios y caracteres raros
_EMAIL_RE = re.compile(
    r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
)

# Proveedores de correo legítimos conocidos
_KNOWN_PROVIDERS = {
    'gmail.com', 'googlemail.com',
    'hotmail.com', 'hotmail.es', 'hotmail.co.uk',
    'outlook.com', 'outlook.es',
    'yahoo.com', 'yahoo.es',
    'live.com', 'live.es',
    'icloud.com', 'me.com',
    'protonmail.com', 'proton.me',
    'utc.edu.ec',
}


def _check_typo(domain):
    """Si el dominio es muy similar a un proveedor conocido pero no es ese proveedor,
    devuelve la sugerencia correcta. Devuelve None si está bien."""
    d = domain.lower()
    if d in _KNOWN_PROVIDERS:
        return None
    best_ratio, best_match = 0, None
    for known in _KNOWN_PROVIDERS:
        ratio = SequenceMatcher(None, d, known).ratio()
        if ratio > best_ratio:
            best_ratio, best_match = ratio, known
    # ≥ 80% similar pero no idéntico → probable error tipográfico
    if best_ratio >= 0.80:
        return best_match
    return None


def _domain_can_receive_email(domain):
    """Devuelve True si el dominio tiene registros MX (puede recibir correos)."""
    try:
        dns.resolver.resolve(domain, 'MX', lifetime=5)
        return True
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        return False
    except Exception:
        # Error de red u otro problema transitorio — no bloqueamos el registro
        return True


class CustomAccountAdapter(DefaultAccountAdapter):
    error_messages = {
        **DefaultAccountAdapter.error_messages,
        "email_taken": "Ya existe una cuenta registrada con este correo electrónico.",
        "username_taken": "Ya existe una cuenta registrada con este nombre de usuario.",
        "email_password_mismatch": "El correo electrónico y/o la contraseña no son correctos.",
        "username_password_mismatch": "El nombre de usuario y/o la contraseña no son correctos.",
        "account_inactive": "Esta cuenta se encuentra inactiva.",
    }

    def clean_email(self, email):
        email = super().clean_email(email)

        if not _EMAIL_RE.match(email):
            raise ValidationError(
                "Introduce un correo electrónico válido (ejemplo: nombre@dominio.com)."
            )

        domain = email.split('@')[1]

        suggestion = _check_typo(domain)
        if suggestion:
            raise ValidationError(
                f"El dominio '{domain}' no es válido. "
                f"¿Quisiste escribir '{suggestion}'?"
            )

        if not _domain_can_receive_email(domain):
            raise ValidationError(
                f"El dominio '{domain}' no existe o no puede recibir correos. "
                "Verifica que tu dirección de correo sea correcta."
            )

        return email

    def send_mail(self, template_prefix, email, context):
        """
        Punto único por el que allauth manda TODOS sus correos (recuperar
        contraseña, confirmación de email, etc.) — ver
        DefaultAccountAdapter.send_mail(). msg.send() es una llamada SMTP
        síncrona y bloqueante dentro del propio request; sin este try/except,
        si el envío falla o tarda (EMAIL_TIMEOUT en settings.py acota esto a
        10s) la excepción sube sin capturar y el usuario ve un error
        genérico ("algo salió mal") en vez de la pantalla normal de "revisa
        tu correo" — igual de mal si el correo sí se pudo enviar como si no,
        ya que por seguridad esa pantalla no debe delatar si el envío
        falló. Mismo criterio que enviar_bienvenida() en apps.py.
        """
        try:
            super().send_mail(template_prefix, email, context)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "No se pudo enviar el correo '%s' a %s", template_prefix, email
            )

    def pre_login(self, request, user, **kwargs):
        """Tras registrarse, no autentica automáticamente: redirige a login
        con un mensaje de éxito para que el usuario ingrese con sus propias
        credenciales."""
        response = super().pre_login(request, user, **kwargs)
        if response is not None:
            return response

        if kwargs.get('signup'):
            from django.contrib import messages
            from django.http import HttpResponseRedirect
            from django.urls import reverse

            messages.success(
                request,
                "¡Tu cuenta ha sido creada exitosamente! Ya puedes iniciar sesión con tus credenciales."
            )
            return HttpResponseRedirect(reverse('analisis:login'))

        return None

    def populate_username(self, request, user):
        """Deriva el username directamente del email para evitar duplicación de campos."""
        from allauth.account.utils import user_email, user_username
        email = user_email(user) or ""
        # Usa el email completo como username (el validador de Django acepta @, ., +, -)
        username = email[:150]  # AbstractUser.username max_length=150
        # Si ya existe (rara vez, p.ej. dos registros simultáneos), añade sufijo numérico
        from django.contrib.auth import get_user_model
        User = get_user_model()
        base = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base[:147]}{counter}"
            counter += 1
        user_username(user, username)
