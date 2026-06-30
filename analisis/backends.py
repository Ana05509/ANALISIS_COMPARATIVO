from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """
    Acepta tanto el email como el username en el campo de login.
    - Usuarios nuevos (signup): username == email  → entran con su correo
    - Usuario admin (createsuperuser): username == 'admin' → entra con 'admin'
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        user = None

        if username is None:
            return None

        # 1) Buscar por username exacto (cubre 'admin' y usuarios nuevos donde username=email)
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            pass

        # 2) Si no se encontró, buscar por email (permite login con email aunque el username sea distinto)
        if user is None:
            try:
                user = User.objects.get(email__iexact=username)
            except User.DoesNotExist:
                # Ejecutar hash de todas formas para mitigar timing attacks
                User().set_password(password)
                return None
            except User.MultipleObjectsReturned:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
