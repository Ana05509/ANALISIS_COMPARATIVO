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
admin.site.site_header = "TerraBioLab UTC"
admin.site.site_title = "Administración TerraBioLab"
admin.site.index_title = "Panel de Control Microbiológico"


# =========================================================
# CULTIVOS
# =========================================================

@admin.register(Cultivo)
class CultivoAdmin(ModelAdmin): 

    list_display = ("id", "nombre", "descripcion")
    search_fields = ("nombre", "descripcion") # Nota: Corregido 'nombreord' a 'nombre'
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
    ordering = ("nombre",)
    list_per_page = 20


# =========================================================
# MUESTRAS DE SUELO
# =========================================================

@admin.register(MuestraSuelo)
class MuestraSueloAdmin(ModelAdmin): 

    list_display = (
        "id",
        "codigo",
        "cultivo",
        "variedad_clon",
        "tipo_muestra",
        "fecha_registro",
    )

    list_filter = (
        "cultivo",
        "variedad_clon",
        "tipo_muestra",
        "fecha_registro",
    )

    search_fields = ("codigo", "cultivo__nombre", "variedad_clon__nombre")
    ordering = ("-fecha_registro",)
    date_hierarchy = "fecha_registro"
    list_per_page = 20

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
# ARCHIVOS MOLECULARES
# =========================================================

@admin.register(ArchivoMolecular)
class ArchivoMolecularAdmin(ModelAdmin): 

    list_display = (
        "id",
        "muestra",
        "tipo_analisis",
        "fecha_carga",
    )

    list_filter = (
        "tipo_analisis",
        "fecha_carga",
    )

    search_fields = ("muestra__codigo",)
    ordering = ("-fecha_carga",)
    date_hierarchy = "fecha_carga"
    list_per_page = 20

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

    list_display = (
        "id",
        "archivo",
        "genus",
        "species",
        "num_hits",
        "porcentaje_hits",
    )

    list_filter = (
        "archivo__tipo_analisis",
    )

    search_fields = (
        "genus",
        "species",
        "phylum",
        "archivo__muestra__codigo",
    )

    ordering = ("-num_hits",)
    list_per_page = 30


# =========================================================
# CATÁLOGO MICROORGANISMOS
# =========================================================

@admin.register(CatalogoMicroorganismo)
class CatalogoMicroorganismoAdmin(ModelAdmin): 

    list_display = (
        "id",
        "nombre",
        "nivel",
        "clasificacion",
    )

    list_filter = (
        "clasificacion",
        "nivel",
    )

    search_fields = ("nombre",)
    ordering = ("nombre",)
    list_per_page = 20


# =========================================================
# USUARIOS
# =========================================================

@admin.register(Usuario)
class UsuarioAdmin(BaseUserAdmin, ModelAdmin): 

    list_display = (
        "id",
        "username",
        "email",
        "rol",
        "is_staff",
    )

    list_filter = (
        "rol",
        "is_staff",
    )

    search_fields = (
        "username",
        "email",
    )

    ordering = ("username",)
    list_per_page = 20
    
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        fieldsets_list = list(fieldsets or [])
        fieldsets_list.append((
            "Información de Roles TerraBioLab",
            {
                "fields": ("rol",)
            }
        ))
        return fieldsets_list