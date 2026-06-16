# analisis/signup_form.py
from django import forms
from .models import Usuario

class CustomSignupForm(forms.Form):  # ← NO heredes de SignupForm
    first_name = forms.CharField(max_length=30, label='Nombre')
    last_name = forms.CharField(max_length=30, label='Apellido')
    rol = forms.ChoiceField(choices=Usuario.ROLES, label='Rol en la plataforma', required=True)

    def signup(self, request, user):
        """Este método es llamado automáticamente por allauth después de crear el usuario"""
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.rol = self.cleaned_data['rol']
        user.save()
        return user