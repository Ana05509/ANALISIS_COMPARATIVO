from django.apps import AppConfig
from django.db.models.signals import pre_save


class AnalisisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analisis'
    verbose_name = 'BioSuelo'

    def ready(self):
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
                body=f'Bienvenido/a {user.first_name} a BioSuelo.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
            )
            msg.attach_alternative(cuerpo_html, 'text/html')
            msg.send(fail_silently=True)

        user_signed_up.connect(enviar_bienvenida)