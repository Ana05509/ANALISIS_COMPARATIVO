from allauth.account.adapter import DefaultAccountAdapter


class CustomAccountAdapter(DefaultAccountAdapter):
    error_messages = {
        **DefaultAccountAdapter.error_messages,
        "email_taken": "Ya fue registrado con este correo electrónico.",
        "username_taken": "Ya fue registrado con este nombre de usuario.",
        "email_password_mismatch": "El correo electrónico y/o la contraseña no son correctos.",
        "username_password_mismatch": "El nombre de usuario y/o la contraseña no son correctos.",
        "account_inactive": "Esta cuenta se encuentra inactiva.",
    }
