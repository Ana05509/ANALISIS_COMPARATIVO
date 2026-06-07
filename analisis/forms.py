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
            archivos_moleculares__tipo_analisis=tipo
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
    
    # CORRECCIÓN AQUÍ: Se añade id="id_cultivo" para que actúe el JavaScript
    cultivo = forms.ModelChoiceField(
        queryset=Cultivo.objects.all(),
        required=True,
        label="Cultivo",
        empty_label="Seleccione un cultivo",
        widget=forms.Select(attrs={"class": "form-control", "id": "id_cultivo"}),
    )
    
    # CORRECCIÓN AQUÍ: Se añade id="id_variedad_clon" para que actúe el JavaScript
    variedad = forms.ModelChoiceField(
        queryset=VariedadClon.objects.all(),
        required=True,
        label="Variedad / Clon",
        empty_label="---------",
        widget=forms.Select(attrs={"class": "form-control", "id": "id_variedad_clon"}),
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
    
    # CORRECCIÓN OPCIONAL: Si estás usando una caja drag & drop interactiva en HTML, 
    # a veces requiere que el input tenga id="file-upload" o clase específica para ocultarse
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
    
    # =========================================================
# FORMULARIO PERSONALIZADO DE REGISTRO (ALLAUTH)
# =========================================================
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
        # Guardar el nombre y apellido en el modelo de usuario de la base de datos
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.save()
        return user
