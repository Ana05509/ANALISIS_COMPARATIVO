from django.contrib import admin
from django.utils.html import format_html, mark_safe
from django.contrib import messages

from unfold.admin import ModelAdmin, TabularInline

from .models import (
    EnsayoMicrobiologico, RecuentoUFC,
    MicroorganismoAislado, PruebaBioquimica,
)


# =========================================================
# INLINES
# =========================================================

class RecuentoUFCInline(TabularInline):
    model = RecuentoUFC
    extra = 3
    fields = ('tipo_organismo', 'nombre', 'coeficiente', 'exponente', 'menor_que_limite', 'orden')
    ordering = ['orden']


class PruebaBioquimicaInline(TabularInline):
    model = PruebaBioquimica
    extra = 5
    fields = ('numero', 'nombre_prueba', 'resultado')
    ordering = ['numero']


class MicroorganismoAisladoInline(TabularInline):
    model = MicroorganismoAislado
    extra = 1
    fields = ('tipo', 'nombre_cientifico', 'genero', 'especie')
    show_change_link = True


# =========================================================
# RECUENTO UFC (standalone para edición detallada)
# =========================================================

@admin.register(RecuentoUFC)
class RecuentoUFCAdmin(ModelAdmin):
    list_display = ('ensayo', 'tipo_organismo', 'nombre', 'valor_ufc_display', 'menor_que_limite')
    list_filter = ('tipo_organismo', 'ensayo')
    search_fields = ('nombre', 'ensayo__codigo')
    list_per_page = 25
    list_fullwidth = True

    fieldsets = (
        ("Vínculo", {"fields": ("ensayo",)}),
        ("Microorganismo", {"fields": ("tipo_organismo", "nombre", "orden")}),
        ("Recuento", {
            "description": "Ingrese el valor en notación científica: coeficiente × 10^exponente (ej. 3 × 10⁶).",
            "fields": ("coeficiente", "exponente", "menor_que_limite"),
        }),
    )

    @admin.display(description="UFC/g")
    def valor_ufc_display(self, obj):
        return obj.valor_display


# =========================================================
# PRUEBA BIOQUÍMICA (standalone)
# =========================================================

@admin.register(PruebaBioquimica)
class PruebaBioquimicaAdmin(ModelAdmin):
    list_display = ('numero', 'nombre_prueba', 'resultado_badge', 'microorganismo')
    list_filter = ('microorganismo__ensayo',)
    search_fields = ('nombre_prueba', 'microorganismo__nombre_cientifico')
    list_per_page = 30
    list_fullwidth = True

    @admin.display(description="Resultado")
    def resultado_badge(self, obj):
        clase = obj.resultado_clase
        colores = {
            'positivo': ('#E1F5EE', '#085041'),
            'negativo': ('#FAEEDA', '#5a3a00'),
            'neutro':   ('#F1EFE8', '#5F5E5A'),
        }
        bg, color = colores.get(clase, ('#F1EFE8', '#5F5E5A'))
        return format_html(
            '<span style="background:{};color:{};padding:2px 10px;border-radius:20px;'
            'font-size:12px;font-weight:500;">{}</span>',
            bg, color, obj.resultado
        )


# =========================================================
# MICROORGANISMO AISLADO
# =========================================================

@admin.register(MicroorganismoAislado)
class MicroorganismoAisladoAdmin(ModelAdmin):
    list_display = ('nombre_cientifico', 'tipo_badge', 'genero', 'especie',
                    'total_pruebas', 'ensayo')
    list_filter = ('tipo', 'ensayo')
    search_fields = ('nombre_cientifico', 'genero', 'familia', 'ensayo__codigo')
    list_per_page = 20
    list_fullwidth = True
    inlines = [PruebaBioquimicaInline]

    fieldsets = (
        ("Vínculo", {"fields": ("ensayo",)}),
        ("Identificación", {"fields": ("tipo", "nombre_cientifico")}),
        ("Taxonomía", {
            "fields": ("dominio", "filo", "clase", "orden_taxonomico", "familia", "genero", "especie"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Tipo")
    def tipo_badge(self, obj):
        if obj.tipo == 'hongo':
            return mark_safe(
                '<span style="background:#FAEEDA;color:#5a3a00;padding:2px 10px;border-radius:20px;'
                'font-size:12px;font-weight:500;">🍄 Hongo</span>'
            )
        return mark_safe(
            '<span style="background:#E1F5EE;color:#085041;padding:2px 10px;border-radius:20px;'
            'font-size:12px;font-weight:500;">🦠 Bacteria</span>'
        )

    @admin.display(description="Pruebas")
    def total_pruebas(self, obj):
        n = obj.pruebas.count()
        return f"{n} prueba(s)" if n > 0 else "—"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            messages.info(request, f"Microorganismo '{obj.nombre_cientifico}' registrado. Ahora puede agregar sus pruebas bioquímicas.")


# =========================================================
# ENSAYO MICROBIOLÓGICO (principal)
# =========================================================

@admin.register(EnsayoMicrobiologico)
class EnsayoMicrobiologicoAdmin(ModelAdmin):
    list_display = ('codigo', 'tipo_badge', 'nombre_muestra', 'fecha_reporte',
                    'total_registros', 'registrado_por', 'ver_detalle')
    list_display_links = ('codigo',)
    list_filter = ('tipo', 'fecha_reporte')
    search_fields = ('codigo', 'nombre_muestra', 'etiqueta')
    ordering = ('-fecha_reporte',)
    date_hierarchy = 'fecha_reporte'
    list_per_page = 20
    list_fullwidth = True
    readonly_fields = ('fecha_registro',)

    fieldsets = (
        ("Identificación del Ensayo", {
            "fields": ("codigo", "tipo", "nombre_muestra", "etiqueta"),
        }),
        ("Fechas", {
            "fields": ("fecha_recepcion", "fecha_ejecucion", "fecha_reporte"),
        }),
        ("Condiciones Ambientales", {
            "fields": ("temp_ambiental", "humedad_ambiental"),
            "classes": ("collapse",),
        }),
        ("Notas y Sistema", {
            "fields": ("observaciones", "registrado_por", "fecha_registro"),
            "classes": ("collapse",),
        }),
    )

    def get_inlines(self, request, obj):
        if obj is None:
            return []
        if obj.tipo == 'recuento':
            return [RecuentoUFCInline]
        return [MicroorganismoAisladoInline]

    @admin.display(description="Tipo")
    def tipo_badge(self, obj):
        if obj.tipo == 'recuento':
            return mark_safe(
                '<span style="background:#E6F1FB;color:#0C447C;padding:2px 10px;border-radius:20px;'
                'font-size:12px;font-weight:500;">📊 Recuento</span>'
            )
        return mark_safe(
            '<span style="background:#F1EFE8;color:#5F5E5A;padding:2px 10px;border-radius:20px;'
            'font-size:12px;font-weight:500;">🔬 Aislamiento</span>'
        )

    @admin.display(description="Registros")
    def total_registros(self, obj):
        n = obj.total_organismos()
        return format_html('<span style="color:#085041;font-weight:500;">{}</span>', f"{n} registro(s)")

    @admin.display(description="Ver")
    def ver_detalle(self, obj):
        from django.urls import reverse
        url = reverse('bioquimica:detalle', args=[obj.pk])
        return format_html(
            '<a href="{}" target="_blank" style="background:#1D9E75;color:white;padding:4px 12px;'
            'border-radius:6px;font-size:12px;font-weight:600;text-decoration:none;">Ver</a>',
            url
        )

    def save_model(self, request, obj, form, change):
        if not obj.registrado_por_id:
            obj.registrado_por = request.user
        super().save_model(request, obj, form, change)
        if not change:
            messages.success(request, f"Ensayo '{obj.codigo}' registrado. Ahora ingrese los datos del ensayo.")
        else:
            messages.info(request, f"Ensayo '{obj.codigo}' actualizado.")
