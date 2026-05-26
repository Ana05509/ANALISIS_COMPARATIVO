from django import forms
from .models import MuestraSuelo, Cultivo, VariedadClon


class CompararForm(forms.Form):
    TIPO_CHOICES = [("16S", "16S"), ("ITS", "ITS")]
    NIVEL_CHOICES = [
        ("genus",   "Género"),
        ("family",  "Familia"),
        ("order",   "Orden"),
        ("class",   "Clase"),
        ("phylum",  "Filo"),
        ("species", "Especie"),
    ]
    TOP_N_CHOICES = [(5,"Top 5"),(10,"Top 10"),(25,"Top 25"),(50,"Top 50")]

    tipo    = forms.ChoiceField(choices=TIPO_CHOICES, initial="16S")
    nivel   = forms.ChoiceField(choices=NIVEL_CHOICES, initial="genus")
    top_n   = forms.ChoiceField(choices=TOP_N_CHOICES, initial=10)
    productos = forms.ModelMultipleChoiceField(
        queryset=MuestraSuelo.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Muestras a comparar",
    )

    def __init__(self, *args, tipo="16S", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["productos"].queryset = MuestraSuelo.objects.filter(
            archivomolecular__tipo_analisis=tipo
        ).distinct().order_by("-id")

    def clean_top_n(self):
        return int(self.cleaned_data.get("top_n", 10))


class SubirDatosForm(forms.Form):
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

    nombre_producto = forms.CharField(
        max_length=100,
        label="Código de muestra",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: CCN51-2024-01"}),
    )
    tipo = forms.ChoiceField(
        choices=TIPO_CHOICES,
        label="Marcador molecular",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    cultivo = forms.ModelChoiceField(
        queryset=Cultivo.objects.all(),
        required=False,
        label="Cultivo",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    variedad = forms.ModelChoiceField(
        queryset=VariedadClon.objects.all(),
        required=False,
        label="Variedad / Clon",
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
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".csv,.tsv,.xlsx,.xls"}),
    )

    def clean_top_n(self):
        return int(self.cleaned_data.get("top_n", 10))