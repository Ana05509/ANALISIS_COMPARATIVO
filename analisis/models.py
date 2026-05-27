from django.contrib.auth.models import AbstractUser
from django.db import models


class Cultivo(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    
    def __str__(self):
        return self.nombre


class VariedadClon(models.Model):
    cultivo = models.ForeignKey(Cultivo, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)

    class Meta:
        unique_together = ('cultivo', 'nombre')

    # CORRECCIÓN VISUAL: Muestra el nombre real del Clon (ej: CCN51) en lugar de "object (1)"
    def __str__(self):
        return self.nombre


class MuestraSuelo(models.Model):
    codigo = models.CharField(max_length=100)
    cultivo = models.ForeignKey(Cultivo, on_delete=models.PROTECT)
    variedad_clon = models.ForeignKey(
        VariedadClon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    tipo_muestra = models.CharField(max_length=100, default="Suelo")
    observaciones = models.TextField(blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Muestra: {self.codigo} - {self.cultivo.nombre}"


class ArchivoMolecular(models.Model):
    TIPOS_ANALISIS = [
        ("16S", "16S"),
        ("ITS", "ITS"),
    ]

    muestra = models.ForeignKey(MuestraSuelo, on_delete=models.CASCADE)
    tipo_analisis = models.CharField(max_length=10, choices=TIPOS_ANALISIS)
    archivo = models.FileField(upload_to="archivos/")
    fecha_carga = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tipo_analisis} - Muestra: {self.muestra.codigo}"


class ResultadoTaxonomico(models.Model):
    archivo = models.ForeignKey(ArchivoMolecular, on_delete=models.CASCADE)
    kingdom = models.CharField(max_length=255, blank=True)
    phylum = models.CharField(max_length=255, blank=True)
    tax_class = models.CharField(max_length=255, blank=True)
    order = models.CharField(max_length=255, blank=True)
    family = models.CharField(max_length=255, blank=True)
    genus = models.CharField(max_length=255, blank=True)
    species = models.CharField(max_length=255, blank=True)
    num_hits = models.FloatField(default=0)
    porcentaje_hits = models.FloatField(default=0)

    def __str__(self):
        return f"{self.genus} {self.species} ({self.porcentaje_hits}%)"


class CatalogoMicroorganismo(models.Model):
    CLASIFICACIONES = [
        ("benefico", "Benéfico"),
        ("fitopatogeno", "Potencial fitopatógeno"),
        ("neutral", "Neutral"),
        ("sin_clasificar", "Sin clasificar"),
    ]

    nombre = models.CharField(max_length=255)
    nivel = models.CharField(max_length=50)
    clasificacion = models.CharField(max_length=30, choices=CLASIFICACIONES)
    descripcion = models.TextField(blank=True)
    referencia = models.TextField(blank=True)

    def __str__(self):
        return f"{self.nombre} [{self.get_clasificacion_display()}]"


# =========================================================
# USUARIOS
# =========================================================

class Usuario(AbstractUser):

    ROLES = (
        ('admin', 'Administrador'),
        ('tecnico', 'Técnico'),
        ('agricultor', 'Agricultor'),
    )

    rol = models.CharField(
        max_length=20,
        choices=ROLES,
        default='admin'
    )

    def __str__(self):
        rol_display = dict(self.ROLES).get(self.rol, self.rol)
        return f"{self.username} ({rol_display})"
