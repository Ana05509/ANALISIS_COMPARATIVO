# models.py
# Arquitectura relacional indexada para el almacenamiento bioinformático y funcional de suelos.

from django.contrib.auth.models import AbstractUser
from django.db import models


class Cultivo(models.Model):
    nombre = models.CharField(max_length=100, unique=True, help_text="Ej: Café, Cacao, Maní")
    descripcion = models.TextField(blank=True)
    
    def __str__(self):
        return self.nombre


class VariedadClon(models.Model):
    cultivo = models.ForeignKey(Cultivo, on_delete=models.CASCADE, related_name="variedades")
    nombre = models.CharField(max_length=100, help_text="Ej: CCN51, Geisha, Caturra")
    descripcion = models.TextField(blank=True)

    class Meta:
        unique_together = ('cultivo', 'nombre')
        verbose_name = "Variedad o Clon"
        verbose_name_plural = "Variedades o Clones"

    def __str__(self):
        return f"{self.cultivo.nombre} - {self.nombre}"


class MuestraSuelo(models.Model):
    # db_index=True automático por ser unique
    codigo = models.CharField(max_length=100, unique=True)
    
    cultivo = models.ForeignKey(Cultivo, on_delete=models.PROTECT, related_name="muestras")
    variedad_clon = models.ForeignKey(
        VariedadClon,
        on_delete=models.PROTECT,
        related_name="muestras"
    )
    
    tipo_muestra = models.CharField(max_length=100, default="Suelo")
    observaciones = models.TextField(blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    localidad = models.CharField(max_length=100, db_index=True, help_text="Provincia, Estado o Región macro")
    finca_lote = models.CharField(max_length=150, help_text="Nombre de la finca o lote de origen específico")
    altitud = models.IntegerField(null=True, blank=True, db_index=True, help_text="Altitud en msnm (crucial para ecología microbiana)")

    class Meta:
        verbose_name = "Muestra de Suelo"
        verbose_name_plural = "Muestras de Suelo"

    def __str__(self):
        return f"Muestra: {self.codigo} [{self.variedad_clon}]"


class ArchivoMolecular(models.Model):
    TIPOS_ANALISIS = [
        ("16S", "16S (Bacterias)"),
        ("ITS", "ITS (Hongos)"),
    ]

    muestra = models.ForeignKey(MuestraSuelo, on_delete=models.CASCADE, related_name="archivos_moleculares")
    tipo_analisis = models.CharField(max_length=10, choices=TIPOS_ANALISIS, db_index=True)
    archivo = models.FileField(upload_to="archivos_moleculares/")
    fecha_carga = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Archivo Molecular"
        verbose_name_plural = "Archivos Moleculares"

    def __str__(self):
        return f"{self.tipo_analisis} - Muestra: {self.muestra.codigo}"


class ResultadoTaxonomico(models.Model):
    archivo = models.ForeignKey(ArchivoMolecular, on_delete=models.CASCADE, related_name="resultados_taxonomicos")
    
    # Indexación estratégica de los rangos de consulta más comunes en ecología
    kingdom = models.CharField(max_length=255, blank=True, db_index=True)
    phylum = models.CharField(max_length=255, blank=True, db_index=True)
    tax_class = models.CharField(max_length=255, blank=True)
    order = models.CharField(max_length=255, blank=True)
    family = models.CharField(max_length=255, blank=True, db_index=True)
    genus = models.CharField(max_length=255, blank=True, db_index=True)
    species = models.CharField(max_length=255, blank=True, db_index=True)
    
    # Corrección biológica del tipo de dato: Conteo discreto entero
    num_hits = models.IntegerField(default=0)
    porcentaje_hits = models.FloatField(default=0.0)

    class Meta:
        verbose_name = "Resultado Taxonómico"
        verbose_name_plural = "Resultados Taxonómicos"
        # Índices compuestos avanzados para acelerar los filtros cruzados y ordenamientos del Top N
        indexes = [
            models.Index(fields=['archivo', 'porcentaje_hits']),
            models.Index(fields=['genus', 'porcentaje_hits']),
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

    nombre = models.CharField(max_length=255, db_index=True, help_text="Nombre científico del taxón (Ej: Bacillus)")
    nivel = models.CharField(max_length=50, db_index=True, help_text="Nivel taxonómico (Ej: genus, species)")
    clasificacion = models.CharField(max_length=30, choices=CLASIFICACIONES, db_index=True)
    descripcion = models.TextField(blank=True)
    referencia = models.TextField(blank=True, help_text="Literatura científica que respalda la clasificación")

    class Meta:
        verbose_name = "Microorganismo de Catálogo"
        verbose_name_plural = "Catálogo de Microorganismos"
        # Índice compuesto para resolver las búsquedas de export_service en O(1) tiempo
        unique_together = ('nombre', 'nivel')

    def __str__(self):
        return f"{self.nombre} [{self.get_clasificacion_display()}]"


class Usuario(AbstractUser):
    ROLES = (
        ('admin', 'Administrador'),
        ('tecnico', 'Técnico / Analista Especialista'),
        ('agricultor', 'Agricultor / Productor'),
        ('estudiante', 'Estudiante de Agronomía'),
    )

    rol = models.CharField(
        max_length=20,
        choices=ROLES,
        default='estudiante'
    )

    def __str__(self):
        rol_display = dict(self.ROLES).get(self.rol, self.rol)
        return f"{self.username} ({rol_display})"