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
    # required=False: igual que en la importación automática, hay reportes
    # de origen que no traen fecha en ningún lado — forzar un valor acá
    # obligaría a inventar uno. Dejarlo vacío es una fecha real "sin dato",
    # no un error de captura (ver EnsayoMicrobiologico.fecha_recepcion).
    fecha_recepcion = forms.DateField(
        required=False, label="Fecha de Recepción",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    fecha_ejecucion = forms.DateField(
        required=False, label="Fecha de Ejecución",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    fecha_reporte = forms.DateField(
        required=False, label="Fecha del Reporte",
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

    def clean_archivo_pdf(self):
        # Sin esto se podía adjuntar cualquier archivo (.html, .exe…) y
        # quedaba guardado en media/ como si fuera el PDF del ensayo.
        archivo = self.cleaned_data.get('archivo_pdf')
        if not archivo:
            return archivo
        if not archivo.name.lower().endswith('.pdf'):
            raise forms.ValidationError("El respaldo debe ser un archivo PDF.")
        if archivo.size > 20 * 1024 * 1024:
            raise forms.ValidationError("El PDF no debe superar 20 MB.")
        archivo.seek(0)
        es_pdf = archivo.read(5) == b'%PDF-'
        archivo.seek(0)
        if not es_pdf:
            raise forms.ValidationError("El archivo no es un PDF válido.")
        return archivo
