import os

from django.apps import AppConfig
from django.db.models.signals import pre_save


def _ip_cliente(request):
    # ip_address es un GenericIPAddressField -> columna "inet" en
    # Postgres, que no acepta cualquier texto. Algunos proxys/redes
    # (institucionales, VPN, ciertas extensiones de privacidad) meten
    # valores no-IP en X-Forwarded-For como "unknown" o un hostname; sin
    # validar, el INSERT entero fallaba con DataError y —desde que el
    # create() quedó en try/except— ese evento de login/logout se perdía
    # en silencio, sin avisar a nadie. Mejor guardar sin IP que no guardar
    # el evento. A nivel de módulo (no dentro de AnalisisConfig.ready())
    # para poder reusarla también desde _AdminAuthFormAuditada más abajo.
    import ipaddress

    if request is None:
        return None
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    candidato = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')
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


# =========================================================
# Receptores de señales — a nivel de MÓDULO, no anidados dentro de
# AnalisisConfig.ready() (como estaban antes).
#
# Motivo: signal.connect() por defecto usa weak=True, que guarda una
# referencia DÉBIL al receptor. Si el receptor es una función anidada
# definida dentro de ready(), una vez que ready() termina de ejecutarse
# nada más en el programa mantiene una referencia FUERTE a esa función —
# queda a merced de cuándo el recolector de basura decida liberarla. En un
# proceso de gunicorn de larga duración, con tráfico real, eventualmente
# se recolecta y la señal se desconecta sola, en silencio, sin ningún
# error — el login/logout sigue funcionando perfecto, pero deja de
# registrarse en la auditoría. Esto es justo lo que se vio en producción:
# la página de diagnóstico (ver EventoAccesoAdmin.diagnostico en admin.py)
# mostró CERO receptores conectados a user_logged_out/user_login_failed
# después de un tiempo corriendo, aunque local (procesos cortos de
# `manage.py shell`) nunca alcanzaba a mostrar el problema.
#
# Es la misma causa raíz, muy probablemente, del bloque "DIAGNOSTICO
# EMAIL" de acá abajo (correos de bienvenida que a veces no salían en
# producción): enviar_bienvenida también estaba anidada dentro de ready().
#
# Al definirlas acá, el propio módulo (que Python mantiene cargado en
# sys.modules mientras el proceso viva) es la referencia fuerte permanente
# — no dependen de recolección de basura para seguir vivas. Además se
# pasa weak=False explícito en cada connect() como cinturón de seguridad.
# =========================================================

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
    # user_signed_up.send() (allauth) no usa send_robust(): si esta
    # función deja escapar una excepción, se propaga hasta
    # complete_signup() y rompe el registro completo — la persona vería
    # un error 500 en vez de quedar registrada, solo porque el correo de
    # bienvenida falló. fail_silently=True en msg.send() de más abajo
    # protege apenas el envío en sí (errores SMTP); todo lo anterior
    # (armar la URL, renderizar las plantillas) queda bajo este try para
    # que CUALQUIER falla acá sea, como pretende el nombre, silenciosa —
    # nunca a costa de bloquear el alta.
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


# user_logged_in/user_logged_out/user_login_failed tampoco usan
# send_robust() — si EventoAcceso.objects.create() lanza una excepción
# (p. ej. la tabla desincronizada con una migración, o un corte puntual
# de conexión a la base), sin este try/except esa excepción se
# propagaría hasta la vista de login/logout y rompería el acceso mismo
# solo porque falló la bitácora de auditoría — el registro debe ser
# best-effort, nunca a costa de bloquear el login.
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
    """Mixin sobre AdminAuthenticationForm (se combina con ella en
    ready(), no puede heredar de ella acá arriba: importar
    django.contrib.admin al nivel del módulo, antes de que la app registry
    termine de cargar, puede romper el arranque).

    El caso que tapa: alguien con credenciales VÁLIDAS pero cuenta sin
    is_staff (docente/estudiante) prueba /admin/login/. Django lo rechaza
    en confirm_login_allowed() — pero eso pasa DESPUÉS de que authenticate()
    ya tuvo éxito, así que user_login_failed nunca se dispara (no fueron
    credenciales incorrectas), y como el form nunca queda válido tampoco se
    llama a login(), así que user_logged_in tampoco. Sin este parche, ese
    intento de entrar al panel admin sin permiso no deja NINGÚN rastro en
    la auditoría — ideal para no detectarlo si alguien está probando
    cuentas contra el panel de administración."""

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
        # ── Diagnóstico temporal: por qué no llegan los correos en producción ──
        # Se imprime UNA vez en cada arranque de la app (incluye los que
        # corre Railway antes de levantar el server: migrate, collectstatic,
        # y el propio gunicorn) — no hace ninguna conexión SMTP, solo lee la
        # configuración ya resuelta. Buscar "DIAGNOSTICO EMAIL" en los logs
        # de Railway. Quitar este bloque una vez resuelto el problema.
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

        # ── Sincronizar el dominio del Site con Railway automáticamente ──
        # Mismo problema que ya resuelven ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS
        # en settings.py: Railway puede regenerar el dominio público en
        # cada despliegue. django-allauth arma la redirect_uri de Google
        # OAuth a partir del dominio guardado en la tabla django_site
        # (Site.domain), NO del dominio real de la petición — si ese
        # registro queda desactualizado (p. ej. sigue en "127.0.0.1:8000"
        # de una migración local), Google responde "Error 400:
        # redirect_uri_mismatch" aunque el resto de la app funcione bien y
        # Google Cloud Console tenga el URI correcto configurado. Se
        # sincroniza después de cada migrate (Railway corre migrate en
        # cada deploy); en local RAILWAY_PUBLIC_DOMAIN no existe, así que
        # esto no hace nada (el propio receptor revisa la env var).
        from django.db.models.signals import post_migrate
        post_migrate.connect(_sincronizar_dominio_site, sender=self, weak=False)

        from django.contrib.auth import get_user_model
        User = get_user_model()
        pre_save.connect(_capitalizar_nombre_y_apellido, sender=User, weak=False)

        from allauth.account.signals import user_signed_up
        user_signed_up.connect(_enviar_bienvenida, weak=False)

        # ── Auditoría: registrar login / login fallido / logout ─────────────
        # Cubre las tres vías de entrada del sistema por igual: el LoginView
        # propio (analisis.views.auth.CustomLoginView), y las de allauth
        # (login social con Google, alta de cuenta) — todas pasan tarde o
        # temprano por django.contrib.auth.login()/logout()/authenticate(),
        # que son quienes disparan estas señales, así que no hace falta
        # engancharse a cada vista por separado.
        from django.contrib.auth.signals import (
            user_logged_in, user_logged_out, user_login_failed,
        )
        user_logged_in.connect(_registrar_login, weak=False)
        user_logged_out.connect(_registrar_logout, weak=False)
        user_login_failed.connect(_registrar_login_fallido, weak=False)

        # ── Auditoría: acceso al panel /admin/ con cuenta sin permiso ───────
        # Cubre el hueco que las tres señales de arriba no ven: alguien con
        # contraseña correcta pero is_staff=False probando /admin/login/
        # (docente/estudiante) — ver el docstring de _AdminAuthFormAuditada.
        from django.contrib import admin as django_admin
        from django.contrib.admin.forms import AdminAuthenticationForm

        class _FormLoginAdminAuditado(_AdminAuthFormAuditada, AdminAuthenticationForm):
            pass

        django_admin.site.login_form = _FormLoginAdminAuditado
