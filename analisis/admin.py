from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin
from django.contrib import messages

from .models import (
    Cultivo,
    VariedadClon,
    MuestraSuelo,
    ArchivoMolecular,
    ResultadoTaxonomico,
    CatalogoMicroorganismo,
    Usuario,
)

# Títulos personalizados para el panel administrativo
admin.site.site_header = "BioSoil Analytics"
admin.site.site_title = "Administración BioSoil Analytics"
admin.site.index_title = "Panel de Control Microbiológico"

# =========================================================
# CULTIVOS
# =========================================================

@admin.register(Cultivo)
class CultivoAdmin(ModelAdmin): 
    list_display = ("id", "nombre", "descripcion")
    search_fields = ("nombre", "descripcion") 
    ordering = ("nombre",)
    list_per_page = 15

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            messages.info(request, f"Cultivo '{obj.nombre}' actualizado correctamente.")
        else:
            messages.success(request, f"¡Éxito! Cultivo agrícola '{obj.nombre}' registrado en la plataforma.")


# =========================================================
# VARIEDADES / CLONES
# =========================================================

@admin.register(VariedadClon)
class VariedadClonAdmin(ModelAdmin): 
    list_display = ("id", "nombre", "cultivo")
    list_filter = ("cultivo",) 
    search_fields = ("nombre", "cultivo__nombre")
    # Autocomplete: Búsqueda rápida de cultivos en lugar de un select tradicional
    autocomplete_fields = ["cultivo"]
    ordering = ("nombre",)
    list_per_page = 20
    
    fieldsets = (
        ("Información de la Variedad", {
            "fields": ("cultivo", "nombre", "descripcion"),
            "description": "Especifique a qué cultivo pertenece esta variedad o clon."
        }),
    )


# =========================================================
# MUESTRAS DE SUELO
# =========================================================

@admin.register(MuestraSuelo)
class MuestraSueloAdmin(ModelAdmin): 
    list_display = (
        "id", "codigo", "cultivo", "variedad_clon", 
        "tipo_muestra", "localidad", "fecha_registro"
    )
    list_filter = ("cultivo", "variedad_clon", "tipo_muestra", "fecha_registro")
    search_fields = ("codigo", "cultivo__nombre", "variedad_clon__nombre", "localidad", "finca_lote")
    
    # Búsqueda dinámica de FKs
    autocomplete_fields = ["cultivo", "variedad_clon"]
    
    ordering = ("-fecha_registro",)
    date_hierarchy = "fecha_registro"
    list_per_page = 20

    # Agrupación visual en tarjetas de Unfold
    fieldsets = (
        ("Identificación de la Muestra", {
            "fields": ("codigo", "tipo_muestra"),
            "description": "Asigne un código único y el tipo de material analizado (ej. Suelo Rizosférico)."
        }),
        ("Vinculación Agronómica", {
            "fields": ("cultivo", "variedad_clon"),
            "description": "Especifique el cultivo y la variedad correspondientes a esta muestra."
        }),
        ("Datos Geográficos y Ecológicos", {
            "fields": ("localidad", "finca_lote", "altitud"),
            "description": "Información del origen que impacta en la ecología microbiana."
        }),
        ("Metadatos Adicionales", {
            "fields": ("observaciones",),
            "classes": ("collapse",), # Sección colapsable
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            messages.info(request, f"Datos de la muestra microbiológica '{obj.codigo}' modificados con éxito.")
        else:
            messages.success(
                request, 
                f"¡Registro Exitoso! La muestra '{obj.codigo}' ha sido indexada. "
                "Ya puedes proceder a vincular sus archivos secuenciación 16S / ITS."
            )


# =========================================================
# ARCHIVOS MOLECULARES (Carga de CSVs)
# =========================================================

@admin.register(ArchivoMolecular)
class ArchivoMolecularAdmin(ModelAdmin): 
    list_display = ("id", "muestra", "tipo_analisis", "fecha_carga")
    list_filter = ("tipo_analisis", "fecha_carga")
    search_fields = ("muestra__codigo",)
    
    autocomplete_fields = ["muestra"]
    
    ordering = ("-fecha_carga",)
    date_hierarchy = "fecha_carga"
    list_per_page = 20

    fieldsets = (
        ("Contexto de la Secuenciación", {
            "fields": ("muestra", "tipo_analisis"),
            "description": "Seleccione a qué muestra de suelo pertenece y el tipo de marcador (16S o ITS)."
        }),
        ("Carga de Datos", {
            "fields": ("archivo",),
            "description": "Suba el archivo tabular (.csv o .xlsx) generado por el secuenciador. Asegúrese de que las columnas coincidan con el formato requerido."
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            messages.info(request, f"Configuración del archivo molecular de la muestra '{obj.muestra.codigo}' actualizada.")
        else:
            messages.success(
                request, 
                f"¡Secuenciación Cargada! Archivo analítico [{obj.tipo_analisis}] acoplado a la muestra '{obj.muestra.codigo}'. "
                "El pipeline bioinformático comenzará a procesar la taxonomía."
            )


# =========================================================
# RESULTADOS TAXONÓMICOS
# =========================================================

@admin.register(ResultadoTaxonomico)
class ResultadoTaxonomicoAdmin(ModelAdmin): 
    list_display = ("id", "archivo", "genus", "species", "num_hits", "porcentaje_hits")
    list_filter = ("archivo__tipo_analisis",)
    search_fields = ("genus", "species", "phylum", "archivo__muestra__codigo")
    
    autocomplete_fields = ["archivo"]
    
    ordering = ("-num_hits",)
    list_per_page = 30


# =========================================================
# CATÁLOGO MICROORGANISMOS
# =========================================================

@admin.register(CatalogoMicroorganismo)
class CatalogoMicroorganismoAdmin(ModelAdmin): 
    list_display = ("id", "nombre", "nivel", "clasificacion")
    list_filter = ("clasificacion", "nivel")
    search_fields = ("nombre", "descripcion")
    ordering = ("nombre",)
    list_per_page = 20

    fieldsets = (
        ("Identificación del Taxón", {
            "fields": ("nombre", "nivel"),
            "description": "Ejemplo: Nombre: 'Bacillus', Nivel: 'genus'"
        }),
        ("Impacto Agronómico", {
            "fields": ("clasificacion", "descripcion", "referencia"),
            "description": "Clasifique el rol de este microorganismo en la salud del cultivo."
        }),
    )


# =========================================================
# USUARIOS
# =========================================================

@admin.register(Usuario)
class UsuarioAdmin(BaseUserAdmin, ModelAdmin): 
    list_display = ("id", "username", "email", "rol", "is_staff")
    list_filter = ("rol", "is_staff")
    search_fields = ("username", "email")
    ordering = ("username",)
    list_per_page = 20
    
    # Excelente forma de inyectar el rol manteniendo la seguridad de BaseUserAdmin
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        fieldsets_list = list(fieldsets or [])
        fieldsets_list.append((
            "Información de Roles TerraBioLab",
            {
                "fields": ("rol",),
                "description": "Asigne el rol adecuado para determinar los permisos de visualización en el Dashboard."
            }
        ))
        return fieldsets_list