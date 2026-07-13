from django import forms
from analisis.models import MuestraSuelo, Cultivo, VariedadClon
from analisis.constants import OPCIONES_TOP_N, NIVELES_CHOICES, MARCADORES_CHOICES

class SubirDatosForm(forms.Form):
    TIPO_CHOICES = [("16S", "16S (Bacterias)"), ("ITS", "ITS (Hongos)")]

    nombre_producto = forms.CharField(
        max_length=100,
        label="Código de muestra",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: CCN51-2024-01"}),
        required=True
    )

    localidad = forms.CharField(
        max_length=100,
        label="Localidad",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Manabí"}),
        required=True
    )

    finca_lote = forms.CharField(
        max_length=150,
        label="Finca / Lote",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Finca La Esperanza"}),
        required=True
    )

    altitud = forms.IntegerField(
        label="Altitud (msnm)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Ej: 1200"}),
        required=False
    )

    cultivo = forms.ModelChoiceField(
        queryset=Cultivo.objects.all(),
        label="Cultivo principal",
        empty_label="Seleccione un cultivo...",
        widget=forms.Select(attrs={"class": "form-control", "id": "id_cultivo"}),
        required=True
    )

    variedad_clon = forms.ModelChoiceField(
        queryset=VariedadClon.objects.none(),
        label="Variedad / clon",
        empty_label="Primero seleccione un cultivo...",
        widget=forms.Select(attrs={"class": "form-control", "id": "id_variedad"}),
        required=False
    )

    tipo = forms.ChoiceField(
        choices=TIPO_CHOICES,
        label="Marcador molecular",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    archivo = forms.FileField(
        label="Archivo CSV / Excel",
        widget=forms.FileInput(attrs={
            "class": "form-control",
            "accept": ".csv,.tsv,.xlsx,.xls",
            "id": "file-upload"
        }),
        required=True
    )

    def clean_archivo(self):
        archivo = self.cleaned_data.get('archivo')
        if archivo:
            ext = archivo.name.split('.')[-1].lower()
            if ext not in ['csv', 'tsv', 'xlsx', 'xls']:
                raise forms.ValidationError("Formato no permitido. Use CSV, TSV o Excel.")
            if archivo.size > 10 * 1024 * 1024:
                raise forms.ValidationError("El archivo no puede superar los 10 MB.")
        return archivo


class _MuestraMultipleField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        parts = [obj.codigo]
        if obj.cultivo_id:
            parts.append(obj.cultivo.nombre)
        if obj.variedad_clon_id:
            parts.append(obj.variedad_clon.nombre)
        if obj.localidad:
            parts.append(obj.localidad)
        return " — ".join(parts)


class CompararForm(forms.Form):
    muestras = _MuestraMultipleField(
        queryset=MuestraSuelo.objects.select_related("cultivo", "variedad_clon").order_by("-id"),
        label="Seleccione las muestras a comparar",
        widget=forms.SelectMultiple(attrs={
            "id": "id_muestras",
            "multiple": "multiple",
            "style": "display:none;",
        }),
        required=True,
    )

    marcador = forms.ChoiceField(
        choices=MARCADORES_CHOICES,
        label="Marcador Molecular",
        widget=forms.Select(attrs={"class": "form-control"})
    )

    nivel = forms.ChoiceField(
        choices=NIVELES_CHOICES,
        initial="genus",
        label="Nivel Taxonómico",
        widget=forms.Select(attrs={"class": "form-control"})
    )

    top_n = forms.ChoiceField(
        choices=[(str(n), f"Top {n}") for n in OPCIONES_TOP_N],
        initial="10",
        label="Top N taxa",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        muestras = cleaned_data.get("muestras")
        if muestras and len(muestras) < 2:
            raise forms.ValidationError("Seleccione al menos dos muestras para comparar.")
        return cleaned_data


class CatalogoImportarForm(forms.Form):
    archivo = forms.FileField(
        label="Archivo CSV / Excel",
        widget=forms.FileInput(attrs={
            "class": "form-control",
            "accept": ".csv,.tsv,.xlsx,.xls",
            "id": "import-catalogo-file"
        }),
        help_text=(
            "Columnas requeridas: nombre, nivel, marcador (16S o ITS), clasificacion. "
            "Opcionales: descripcion, referencia."
        )
    )

    def clean_archivo(self):
        archivo = self.cleaned_data.get('archivo')
        if archivo:
            ext = archivo.name.rsplit('.', 1)[-1].lower()
            if ext not in ('csv', 'tsv', 'xlsx', 'xls'):
                raise forms.ValidationError("Formato no permitido. Use CSV, TSV o Excel.")
            if archivo.size > 5 * 1024 * 1024:
                raise forms.ValidationError("El archivo no puede superar los 5 MB.")
        return archivo