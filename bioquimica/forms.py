from django import forms

from .models import EnsayoMicrobiologico


class EnsayoManualForm(forms.Form):
    """Cabecera del ensayo para el flujo de ingreso manual (sin PDF)."""

    codigo = forms.CharField(
        max_length=50, label="Código del Ensayo",
        widget=forms.TextInput(attrs={'placeholder': 'Ej: MAg-225-2023', 'class': 'form-control'}),
    )
    tipo = forms.ChoiceField(
        choices=EnsayoMicrobiologico.TIPO_ENSAYO, label="Tipo de Ensayo",
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_tipo'}),
    )
    nombre_muestra = forms.CharField(
        max_length=200, label="Nombre de la Muestra",
        widget=forms.TextInput(attrs={'placeholder': 'Ej: Suelo #1', 'class': 'form-control'}),
    )
    etiqueta = forms.CharField(
        required=False, label="Etiqueta de la Muestra",
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control',
                                      'placeholder': 'Fecha, lote, sección… (opcional)'}),
    )
    fecha_recepcion = forms.DateField(
        label="Fecha de Recepción",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    fecha_ejecucion = forms.DateField(
        label="Fecha de Ejecución",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    fecha_reporte = forms.DateField(
        label="Fecha del Reporte",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    temp_ambiental = forms.DecimalField(
        required=False, label="Temperatura Ambiental (°C)",
        widget=forms.NumberInput(attrs={'step': '0.1', 'class': 'form-control'}),
    )
    humedad_ambiental = forms.DecimalField(
        required=False, label="Humedad Ambiental (%)",
        widget=forms.NumberInput(attrs={'step': '0.1', 'class': 'form-control'}),
    )
    observaciones = forms.CharField(
        required=False, label="Observaciones",
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
    )
    archivo_pdf = forms.FileField(
        required=False, label="Adjuntar PDF de respaldo (opcional)",
    )
