from django import forms
from analisis.models import MuestraSuelo, Cultivo, VariedadClon

class SubirDatosForm(forms.Form):
    nombre_producto = forms.CharField(
        max_length=100,
        label="Código de muestra",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: CCN51-2024-01"}),
        required=True
    )
    
    TIPO_CHOICES  = [("16S", "16S (Bacterias)"), ("ITS", "ITS (Hongos)")]
    NIVEL_CHOICES = [
        ("genus",   "Género"),
        ("family",  "Familia"),
        ("order",   "Orden"),
        ("class",   "Clase"),
        ("phylum",  "Filo"),
        ("species", "Especie"),
    ]
    TOP_N_CHOICES = [(5,"Top 5"),(10,"Top 10"),(25,"Top 25"),(50,"Top 50")]

    localidad = forms.CharField(
        max_length=100,
        label="Localidad",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Manabí"}),
        required=True
    )

    cultivo = forms.ModelChoiceField(
        queryset=Cultivo.objects.all(),
        label="Cultivo principal",
        empty_label="Seleccione un cultivo...",
        widget=forms.Select(attrs={"class": "form-control", "id": "id_cultivo"}),
        required=True
    )
    
    variedad = forms.ModelChoiceField(
        queryset=VariedadClon.objects.none(),  # Inicialmente vacío
        label="Variedad / clon",
        empty_label="Primero seleccione un cultivo...",
        widget=forms.Select(attrs={"class": "form-control", "id": "id_variedad"}),
        required=True
    )

    tipo = forms.ChoiceField(
        choices=TIPO_CHOICES,
        label="Marcador molecular",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    nivel = forms.ChoiceField(
        choices=NIVEL_CHOICES,
        initial="genus",
        label="Nivel taxonómico",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    top_n = forms.ChoiceField(
        choices=TOP_N_CHOICES,
        initial=10,
        label="Top N",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    
    archivo = forms.FileField(
        label="Archivo CSV / Excel",
        widget=forms.FileInput(attrs={
            "class": "form-control", 
            "accept": ".csv,.tsv,.xlsx,.xls",
            "id": "file-upload"
        }),
    )

    def clean_top_n(self):
        return int(self.cleaned_data.get("top_n", 10))

class CompararForm(forms.Form):
    """Formulario para la selección cruzada de muestras en el laboratorio."""
    MARCADOR_CHOICES = [("16S", "16S (Bacterias)"), ("ITS", "ITS (Hongos)")]
    NIVEL_CHOICES = [
        ("genus", "Género"),
        ("family", "Familia"),
        ("order", "Orden"),
        ("class", "Clase"),
        ("phylum", "Filo"),
        ("species", "Especie"),
    ]

    muestra_1 = forms.ModelChoiceField(
        queryset=MuestraSuelo.objects.all().order_by("-id"),
        label="Muestra Base A",
        empty_label="Seleccione la primera muestra...",
        widget=forms.Select(attrs={"class": "form-control (select2)"})
    )
    muestra_2 = forms.ModelChoiceField(
        queryset=MuestraSuelo.objects.all().order_by("-id"),
        label="Muestra Objetivo B",
        empty_label="Seleccione la segunda muestra...",
        widget=forms.Select(attrs={"class": "form-control (select2)"})
    )
    marcador = forms.ChoiceField(
        choices=MARCADOR_CHOICES,
        label="Filtro de Marcador",
        widget=forms.Select(attrs={"class": "form-control"})
    )
    nivel = forms.ChoiceField(
        choices=NIVEL_CHOICES,
        initial="genus",
        label="Profundidad Taxonómica",
        widget=forms.Select(attrs={"class": "form-control"})
    )

    def clean(self):
        cleaned_data = super().clean()
        m1 = cleaned_data.get("muestra_1")
        m2 = cleaned_data.get("muestra_2")

        if m1 and m2 and m1 == m2:
            raise forms.ValidationError("No se puede realizar un análisis comparativo sobre la misma muestra de suelo.")
        return cleaned_data


class CustomSignupForm(forms.Form):
    first_name = forms.CharField(
        max_length=30, 
        label='Nombre',
        widget=forms.TextInput(attrs={'placeholder': 'Ej: Juan'})
    )
    last_name = forms.CharField(
        max_length=30, 
        label='Apellido',
        widget=forms.TextInput(attrs={'placeholder': 'Ej: Pérez'})
    )

    def signup(self, request, user):
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.save()