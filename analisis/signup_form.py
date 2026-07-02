import re
from django import forms

# Acepta letras (incluye acentos/ñ), con separadores simples (espacio, guion, apóstrofe)
# solo entre palabras — nunca al inicio, al final, ni consecutivos.
_NAME_RE = re.compile(
    r"^[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]+([ '\-][a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]+)*$"
)


def _validate_name(value, field_label):
    value = value.strip()
    if not value:
        raise forms.ValidationError(f"El {field_label} no puede estar vacío.")
    if len(value) < 2:
        raise forms.ValidationError(f"El {field_label} debe tener al menos 2 letras.")
    if not _NAME_RE.match(value):
        raise forms.ValidationError(
            f"El {field_label} solo puede contener letras. "
            "Los guiones, espacios o apóstrofes deben ir entre letras, no repetidos ni al inicio/final."
        )
    return value.title()


class CustomSignupForm(forms.Form):
    first_name = forms.CharField(
        max_length=30,
        label='Nombre',
        widget=forms.TextInput(attrs={'placeholder': 'Ej: Juan', 'class': 'form-control'}),
    )
    last_name = forms.CharField(
        max_length=30,
        label='Apellido',
        widget=forms.TextInput(attrs={'placeholder': 'Ej: Pérez', 'class': 'form-control'}),
    )

    def clean_first_name(self):
        return _validate_name(self.cleaned_data.get('first_name', ''), 'nombre')

    def clean_last_name(self):
        return _validate_name(self.cleaned_data.get('last_name', ''), 'apellido')

    def signup(self, request, user):
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.rol = 'estudiante'
        user.save()
