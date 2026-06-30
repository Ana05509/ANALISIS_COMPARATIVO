from allauth.account.adapter import DefaultAccountAdapter


class CustomAccountAdapter(DefaultAccountAdapter):
    error_messages = {
        **DefaultAccountAdapter.error_messages,
        "email_taken": "Ya existe una cuenta registrada con este correo electrónico.",
        "username_taken": "Ya existe una cuenta registrada con este nombre de usuario.",
        "email_password_mismatch": "El correo electrónico y/o la contraseña no son correctos.",
        "username_password_mismatch": "El nombre de usuario y/o la contraseña no son correctos.",
        "account_inactive": "Esta cuenta se encuentra inactiva.",
    }

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
