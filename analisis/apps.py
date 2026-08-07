import os

from django.apps import AppConfig
from django.db.models.signals import pre_save


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
        # esto no hace nada.
        railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
        if railway_domain:
            from django.db.models.signals import post_migrate

            def sincronizar_dominio_site(sender, **kwargs):
                from django.conf import settings as dj_settings
                from django.contrib.sites.models import Site
                Site.objects.filter(id=dj_settings.SITE_ID).update(domain=railway_domain)

            post_migrate.connect(sincronizar_dominio_site, sender=self)

        from django.contrib.auth import get_user_model
        User = get_user_model()

        # ── Capitalizar nombres al guardar ──────────────────────────────────
        def capitalizar_nombre_y_apellido(sender, instance, **kwargs):
            if instance.first_name:
                instance.first_name = instance.first_name.strip().title()
            if instance.last_name:
                instance.last_name = instance.last_name.strip().title()

        pre_save.connect(capitalizar_nombre_y_apellido, sender=User)

        # ── Correo de bienvenida al completar el registro ───────────────────
        from allauth.account.signals import user_signed_up

        def enviar_bienvenida(sender, request, user, **kwargs):
            # user_signed_up.send() (allauth) no usa send_robust(): si esta
            # función deja escapar una excepción, se propaga hasta
            # complete_signup() y rompe el registro completo — la persona
            # vería un error 500 en vez de quedar registrada, solo porque el
            # correo de bienvenida falló. fail_silently=True en msg.send()
            # de más abajo protege apenas el envío en sí (errores SMTP); todo
            # lo anterior (armar la URL, renderizar las plantillas) queda
            # bajo este try para que CUALQUIER falla aquí sea, como pretende
            # el nombre, silenciosa — nunca a costa de bloquear el alta.
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

        user_signed_up.connect(enviar_bienvenida)

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
        from .models import EventoAcceso

        def _ip_cliente(request):
            # ip_address es un GenericIPAddressField -> columna "inet" en
            # Postgres, que no acepta cualquier texto. Algunos proxys/redes
            # (institucionales, VPN, ciertas extensiones de privacidad)
            # meten valores no-IP en X-Forwarded-For como "unknown" o un
            # hostname; sin validar, el INSERT entero fallaba con DataError
            # y —desde que el create() quedó en try/except— ese evento de
            # login/logout se perdía en silencio, sin avisar a nadie. Mejor
            # guardar sin IP que no guardar el evento.
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

        # user_logged_in/user_logged_out/user_login_failed tampoco usan
        # send_robust() — si EventoAcceso.objects.create() lanza una
        # excepción (p. ej. la tabla desincronizada con una migración, o un
        # corte puntual de conexión a la base), sin este try/except esa
        # excepción se propagaría hasta la vista de login/logout y rompería
        # el acceso mismo solo porque falló la bitácora de auditoría — el
        # registro debe ser best-effort, nunca a costa de bloquear el login.
        def registrar_login(sender, request, user, **kwargs):
            try:
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

        def registrar_logout(sender, request, user, **kwargs):
            # user puede venir None si la sesión ya había expirado
            try:
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

        def registrar_login_fallido(sender, credentials, request=None, **kwargs):
            try:
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

        user_logged_in.connect(registrar_login)
        user_logged_out.connect(registrar_logout)
        user_login_failed.connect(registrar_login_fallido)