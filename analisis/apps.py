import os

from django.apps import AppConfig
from django.db.models.signals import pre_save


def _ip_cliente(request):
    # Devuelve la IP del cliente (según ALLAUTH_TRUSTED_PROXY_COUNT) o None si
    # no es una IP válida, para que el registro de auditoría no falle.
    import ipaddress
    from allauth.core.internal.httpkit import get_client_ip

    if request is None:
        return None
    try:
        candidato = get_client_ip(request)
    except Exception:
        candidato = request.META.get('REMOTE_ADDR')
    if not candidato:
        return None
    try:
        ipaddress.ip_address(candidato)
    except ValueError:
        return None
    return candidato


def _user_agent(request):
    if request is None:
        return ''
    return request.META.get('HTTP_USER_AGENT', '')[:255]


# Receptores de señales a nivel de módulo y con weak=False, para que el
# recolector de basura no los desconecte en producción.

def _sincronizar_dominio_site(sender, **kwargs):
    from django.conf import settings as dj_settings
    from django.contrib.sites.models import Site
    railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
    if railway_domain:
        Site.objects.filter(id=dj_settings.SITE_ID).update(domain=railway_domain)


def _capitalizar_nombre_y_apellido(sender, instance, **kwargs):
    if instance.first_name:
        instance.first_name = instance.first_name.strip().title()
    if instance.last_name:
        instance.last_name = instance.last_name.strip().title()


def _enviar_bienvenida(sender, request, user, **kwargs):
    # Cualquier error aquí se ignora para no romper el registro del usuario.
    try:
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        from django.conf import settings

        rol_display = dict(user.ROLES).get(user.rol, user.rol)
        login_url = request.build_absolute_uri('/accounts/login/')

        asunto = render_to_string(
            'account/email/welcome_subject.txt',
            {'user': user},
        ).strip()

        cuerpo_html = render_to_string(
            'account/email/welcome_body.html',
            {'user': user, 'rol': rol_display, 'login_url': login_url},
            request=request,
        )

        msg = EmailMultiAlternatives(
            subject=asunto,
            body=f'Bienvenido/a {user.first_name} a BioMicro.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(cuerpo_html, 'text/html')
        msg.send(fail_silently=True)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "No se pudo enviar el correo de bienvenida a %s", getattr(user, 'email', '?')
        )


# La auditoría nunca debe impedir el login/logout si falla al guardar.
def _registrar_login(sender, request, user, **kwargs):
    try:
        from .models import EventoAcceso
        EventoAcceso.objects.create(
            tipo='login_ok', usuario=user,
            ip_address=_ip_cliente(request), user_agent=_user_agent(request),
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "No se pudo registrar el evento de acceso (login_ok) de %s",
            getattr(user, 'email', getattr(user, 'username', '?')),
        )


def _registrar_logout(sender, request, user, **kwargs):
    # user puede venir None si la sesión ya había expirado
    try:
        from .models import EventoAcceso
        EventoAcceso.objects.create(
            tipo='logout', usuario=user,
            ip_address=_ip_cliente(request), user_agent=_user_agent(request),
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "No se pudo registrar el evento de acceso (logout) de %s",
            getattr(user, 'email', getattr(user, 'username', '?')),
        )


def _registrar_login_fallido(sender, credentials, request=None, **kwargs):
    try:
        from .models import EventoAcceso
        username = str(credentials.get('username', ''))[:150]
        EventoAcceso.objects.create(
            tipo='login_fallido', username_intentado=username,
            ip_address=_ip_cliente(request), user_agent=_user_agent(request),
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "No se pudo registrar el evento de acceso (login_fallido)"
        )


class _AdminAuthFormAuditada:
    """Registra en auditoría los intentos de entrar a /admin/ con una cuenta sin is_staff.
    Se combina con AdminAuthenticationForm en ready()."""

    def confirm_login_allowed(self, user):
        from django.core.exceptions import ValidationError
        try:
            super().confirm_login_allowed(user)
        except ValidationError:
            if not user.is_staff:
                try:
                    from .models import EventoAcceso
                    EventoAcceso.objects.create(
                        tipo='login_fallido', usuario=user,
                        username_intentado=user.get_username()[:150],
                        ip_address=_ip_cliente(getattr(self, 'request', None)),
                        user_agent=_user_agent(getattr(self, 'request', None)),
                    )
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception(
                        "No se pudo registrar el intento de acceso admin denegado de %s",
                        user.get_username(),
                    )
            raise


class AnalisisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analisis'
    verbose_name = 'BioMicro'

    def ready(self):
        from django.db.models.signals import post_delete
        from .archivos import limpiar_original_eliminado
        from .models import ArchivoMolecular, ArchivoMolecularRevision
        from bioquimica.models import EnsayoMicrobiologico
        for modelo in (ArchivoMolecular, ArchivoMolecularRevision, EnsayoMicrobiologico):
            post_delete.connect(limpiar_original_eliminado, sender=modelo, weak=False,
                                dispatch_uid=f"limpiar_original_{modelo._meta.label_lower}")
        # Diagnóstico temporal de correo: buscar "DIAGNOSTICO EMAIL" en los logs.
        try:
            from django.conf import settings as dj_settings
            import logging
            logger = logging.getLogger(__name__)
            user_set = bool(getattr(dj_settings, 'EMAIL_HOST_USER', ''))
            pass_set = bool(getattr(dj_settings, 'EMAIL_HOST_PASSWORD', ''))
            logger.warning(
                "=== DIAGNOSTICO EMAIL === EMAIL_BACKEND=%s | EMAIL_HOST_USER definido=%s | "
                "EMAIL_HOST_PASSWORD definido=%s | EMAIL_HOST=%s | EMAIL_PORT=%s | EMAIL_TIMEOUT=%s",
                getattr(dj_settings, 'EMAIL_BACKEND', '?'),
                user_set, pass_set,
                getattr(dj_settings, 'EMAIL_HOST', '?'),
                getattr(dj_settings, 'EMAIL_PORT', '?'),
                getattr(dj_settings, 'EMAIL_TIMEOUT', '?'),
            )
            if not (user_set and pass_set):
                logger.warning(
                    "=== DIAGNOSTICO EMAIL === EMAIL_HOST_USER o EMAIL_HOST_PASSWORD "
                    "está vacío en este entorno -> cae al backend de consola, NO envía "
                    "correos reales aunque la app no muestre ningún error."
                )
        except Exception:
            pass

        # Sincronizar el dominio del Site con Railway (lo usa Google OAuth
        # para la redirect_uri). En local no hace nada.
        from django.db.models.signals import post_migrate
        post_migrate.connect(_sincronizar_dominio_site, sender=self, weak=False)

        from django.contrib.auth import get_user_model
        User = get_user_model()
        pre_save.connect(_capitalizar_nombre_y_apellido, sender=User, weak=False)

        from allauth.account.signals import user_signed_up
        user_signed_up.connect(_enviar_bienvenida, weak=False)

        # Auditoría: registrar login / login fallido / logout
        from django.contrib.auth.signals import (
            user_logged_in, user_logged_out, user_login_failed,
        )
        user_logged_in.connect(_registrar_login, weak=False)
        user_logged_out.connect(_registrar_logout, weak=False)
        user_login_failed.connect(_registrar_login_fallido, weak=False)

        # Auditoría: acceso al panel /admin/ con cuenta sin permiso
        from django.contrib import admin as django_admin
        from django.contrib.admin.forms import AdminAuthenticationForm

        class _FormLoginAdminAuditado(_AdminAuthFormAuditada, AdminAuthenticationForm):
            pass

        django_admin.site.login_form = _FormLoginAdminAuditado
