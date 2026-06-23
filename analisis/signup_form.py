from django import forms


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
        value = self.cleaned_data.get('first_name', '').strip()
        if not value:
            raise forms.ValidationError("El nombre no puede estar vacío.")
        if not all(c.isalpha() or c in " '-" for c in value):
            raise forms.ValidationError("El nombre solo puede contener letras.")
        return value.title()

    def clean_last_name(self):
        value = self.cleaned_data.get('last_name', '').strip()
        if not value:
            raise forms.ValidationError("El apellido no puede estar vacío.")
        if not all(c.isalpha() or c in " '-" for c in value):
            raise forms.ValidationError("El apellido solo puede contener letras.")
        return value.title()

    def signup(self, request, user):
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.rol = 'estudiante'
        user.save()
