from django.contrib import admin

from .models import (
    Cultivo,
    VariedadClon,
    MuestraSuelo,
    ArchivoMolecular,
    ResultadoTaxonomico,
    CatalogoMicroorganismo,
    Usuario,
)


# =========================================================
# CULTIVOS
# =========================================================

@admin.register(Cultivo)
class CultivoAdmin(admin.ModelAdmin):

    list_display = ("id", "nombre", "descripcion")

    search_fields = ("nombre",)

    ordering = ("nombre",)

    list_per_page = 15


# =========================================================
# VARIEDADES / CLONES
# =========================================================

@admin.register(VariedadClon)
class VariedadClonAdmin(admin.ModelAdmin):

    list_display = ("id", "nombre", "cultivo")

    list_filter = ("cultivo",)

    search_fields = ("nombre",)

    ordering = ("nombre",)

    list_per_page = 20


# =========================================================
# MUESTRAS DE SUELO
# =========================================================

@admin.register(MuestraSuelo)
class MuestraSueloAdmin(admin.ModelAdmin):

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
        "tipo_muestra",
        "fecha_registro",
    )

    search_fields = ("codigo",)

    ordering = ("-fecha_registro",)

    date_hierarchy = "fecha_registro"

    list_per_page = 20


# =========================================================
# ARCHIVOS MOLECULARES
# =========================================================

@admin.register(ArchivoMolecular)
class ArchivoMolecularAdmin(admin.ModelAdmin):

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


# =========================================================
# RESULTADOS TAXONÓMICOS
# =========================================================

@admin.register(ResultadoTaxonomico)
class ResultadoTaxonomicoAdmin(admin.ModelAdmin):

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
    )

    ordering = ("-num_hits",)

    list_per_page = 30


# =========================================================
# CATÁLOGO MICROORGANISMOS
# =========================================================

@admin.register(CatalogoMicroorganismo)
class CatalogoMicroorganismoAdmin(admin.ModelAdmin):

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
class UsuarioAdmin(admin.ModelAdmin):

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