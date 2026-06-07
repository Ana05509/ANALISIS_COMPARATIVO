from django.apps import AppConfig
from django.db.models.signals import pre_save

class AnalisisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analisis'

    def ready(self):
        # Importamos el modelo de usuario aquí adentro para evitar errores de carga de Django
        from django.contrib.auth import get_user_model
        User = get_user_model()

        # Definimos la función que limpia y capitaliza los nombres
        def capitalizar_nombre_y_apellido(sender, instance, **kwargs):
            if instance.first_name:
                instance.first_name = instance.first_name.strip().title()
            if instance.last_name:
                instance.last_name = instance.last_name.strip().title()

        # Conectamos la función al evento pre_save directamente
        pre_save.connect(capitalizar_nombre_y_apellido, sender=User)