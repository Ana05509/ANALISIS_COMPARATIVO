from django.db import models
from django.contrib.auth.models import AbstractUser
import os

# -------------------------------
# Modelos de Catálogo Agronómico
# -------------------------------

class Cultivo(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre del Cultivo")
    descripcion = models.TextField(blank=True, verbose_name="Descripción")

    class Meta:
        verbose_name = "Cultivo"
        verbose_name_plural = "Cultivos"

    def __str__(self):
        return self.nombre


class VariedadClon(models.Model):
    cultivo = models.ForeignKey(
        Cultivo, on_delete=models.CASCADE,
        related_name="variedades", verbose_name="Cultivo Base"
    )
    nombre = models.CharField(max_length=100, verbose_name="Nombre de la Variedad/Clon")
    descripcion = models.TextField(blank=True, verbose_name="Descripción")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['cultivo', 'nombre'],
                name='unique_cultivo_variedad'
            )
        ]
        verbose_name = "Variedad o Clon"
        verbose_name_plural = "Variedades o Clones"

    def __str__(self):
        return f"{self.cultivo.nombre} - {self.nombre}"


# ---------------------------------
# Muestras de Suelo y Datos Asociados
# ---------------------------------

class MuestraSuelo(models.Model):
    codigo = models.CharField(max_length=100, unique=True, verbose_name="Código de la Muestra")
    cultivo = models.ForeignKey(
        Cultivo, on_delete=models.PROTECT,
        related_name="muestras", verbose_name="Cultivo"
    )
    variedad_clon = models.ForeignKey(
        VariedadClon, on_delete=models.PROTECT,
        related_name="muestras", verbose_name="Variedad o Clon"
    )
    tipo_muestra = models.CharField(max_length=100, default="Suelo", verbose_name="Tipo de Muestra")
    observaciones = models.TextField(blank=True, verbose_name="Observaciones de Campo")
    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Ingreso")
    localidad = models.CharField(max_length=100, db_index=True, verbose_name="Localidad")
    finca_lote = models.CharField(max_length=150, verbose_name="Finca / Lote")
    altitud = models.IntegerField(null=True, blank=True, db_index=True, verbose_name="Altitud (msnm)")

    class Meta:
        verbose_name = "Muestra de Suelo"
        verbose_name_plural = "Muestras de Suelo"

    def __str__(self):
        return f"Muestra: {self.codigo}"


# Ruta dinámica para archivos moleculares
def ruta_archivo_molecular(instance, filename):
    # Ejemplo: archivos_moleculares/16S/M001_muestra.csv
    return f"archivos_moleculares/{instance.tipo_analisis}/{instance.muestra.codigo}_{filename}"


class ArchivoMolecular(models.Model):
    TIPOS_ANALISIS = [
        ("16S", "16S (Bacterias)"),
        ("ITS", "ITS (Hongos)"),
    ]

    muestra = models.ForeignKey(
        MuestraSuelo, on_delete=models.CASCADE,
        related_name="archivos_moleculares", verbose_name="Muestra de Suelo"
    )
    tipo_analisis = models.CharField(max_length=10, choices=TIPOS_ANALISIS, db_index=True, verbose_name="Tipo de Marcador")
    archivo = models.FileField(upload_to=ruta_archivo_molecular, verbose_name="Archivo de Secuenciación (CSV/Excel)")
    fecha_carga = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Subida")

    class Meta:
        verbose_name = "Archivo Molecular"
        verbose_name_plural = "Archivos Moleculares"

    def __str__(self):
        return f"{self.tipo_analisis} - Muestra: {self.muestra.codigo}"


class ResultadoTaxonomico(models.Model):
    archivo = models.ForeignKey(
        ArchivoMolecular, on_delete=models.CASCADE,
        related_name="resultados_taxonomicos"
    )

    kingdom = models.CharField(max_length=255, blank=True, db_index=True)
    phylum = models.CharField(max_length=255, blank=True, db_index=True)
    tax_class = models.CharField(max_length=255, blank=True)
    order = models.CharField(max_length=255, blank=True)
    family = models.CharField(max_length=255, blank=True, db_index=True)
    genus = models.CharField(max_length=255, blank=True, db_index=True)
    species = models.CharField(max_length=255, blank=True, db_index=True)

    num_hits = models.IntegerField(default=0, verbose_name="Conteo de Abundancia")
    porcentaje_hits = models.FloatField(default=0.0, verbose_name="Abundancia Relativa (%)")

    class Meta:
        verbose_name = "Resultado Taxonómico"
        verbose_name_plural = "Resultados Taxonómicos"
        indexes = [
            models.Index(fields=['archivo', 'num_hits']),
            models.Index(fields=['genus', 'num_hits']),
        ]

    def __str__(self):
        genus_display = self.genus if self.genus else "Unclassified"
        species_display = self.species if self.species else "sp."
        return f"{genus_display} {species_display} ({self.porcentaje_hits}%)"


class CatalogoMicroorganismo(models.Model):
    CLASIFICACIONES = [
        ("benefico", "Benéfico"),
        ("fitopatogeno", "Potencial fitopatógeno"),
        ("neutral", "Neutral"),
        ("sin_clasificar", "Sin clasificar"),
    ]

    MARCADOR_CHOICES = [
        ("16S", "Bacteria"),
        ("ITS", "Hongo"),
    ]

    nombre = models.CharField(max_length=255, db_index=True, verbose_name="Nombre Científico",
                              help_text="Ej: Bacillus")
    nivel = models.CharField(max_length=50, db_index=True, verbose_name="Nivel Taxonómico",
                             help_text="Ej: genus, species")
    clasificacion = models.CharField(max_length=30, choices=CLASIFICACIONES, db_index=True,
                                     verbose_name="Rol Funcional")
    descripcion = models.TextField(blank=True, verbose_name="Descripción Agronómica")
    referencia = models.TextField(blank=True, verbose_name="Referencia Literaria",
                                  help_text="Literatura científica que respalda la clasificación")

    # Nuevo campo solo con 16S e ITS
    marcador = models.CharField(
        max_length=10,
        choices=MARCADOR_CHOICES,
        default="16S",          # valor por defecto
        verbose_name="Marcador Molecular",
        help_text="Región genética usada para identificación (16S o ITS)"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['nombre', 'nivel'], name='unique_nombre_nivel')
        ]
        verbose_name = "Microorganismo de Catálogo"
        verbose_name_plural = "Catálogo de Microorganismos"

    def __str__(self):
        return f"{self.nombre} [{self.get_clasificacion_display()}] - {self.get_marcador_display()}"

# ---------------------------------
# Modelo de Usuario Personalizado
# ---------------------------------

class Usuario(AbstractUser):
    ROLES = (
        ('admin', 'Administrador'),
        ('docente', 'Docente / Investigador'),
        ('estudiante', 'Estudiante'),
    )

    rol = models.CharField(
        max_length=20,
        choices=ROLES,
        default='estudiante',
        verbose_name="Rol en la Plataforma"
    )

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self):
        rol_display = dict(self.ROLES).get(self.rol, self.rol)
        return f"{self.username} ({rol_display})"