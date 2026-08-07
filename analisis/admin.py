from django.contrib import admin
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html, mark_safe
from django.db import transaction
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.template.response import TemplateResponse
from django import forms
import pandas as pd
import io

# Importaciones de Unfold
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

# Historial de cambios (Cultivo, MuestraSuelo, CatalogoMicroorganismo, Usuario)
from simple_history.admin import SimpleHistoryAdmin

# Importaciones de tu app
from .models import (
    Cultivo, VariedadClon, MuestraSuelo, ArchivoMolecular,
    ResultadoTaxonomico, CatalogoMicroorganismo, Usuario, EventoAcceso,
)
from analisis.services.processing.pipeline import PipelineProcesamiento

# Configuración de cabeceras
admin.site.site_header = "BioMicro UTC"
admin.site.site_title  = "Administración BioMicro"
admin.site.index_title = "Panel de Control Microbiológico"


# =========================================================
# ACCIONES EXPLÍCITAS (Ver/Editar/Eliminar) EN LAS TABLAS
# =========================================================
class AccionesColumnaMixin:
    """
    Agrega una columna final con íconos de acción explícitos. Django ya
    hace clickeable toda la fila hacia la edición (list_display_links),
    pero para un administrador con poca experiencia técnica un ícono
    visible es más intuitivo que tener que descubrir eso por su cuenta.

    "Ver" y "Editar" no son dos destinos distintos acá: en este sistema
    todos los administradores tienen permiso de edición completo, así que
    ambos apuntarían a la misma pantalla — se muestra un solo ícono
    (lápiz si hay permiso de edición, ojo si el modelo es de solo
    lectura, como Auditoría) en vez de duplicar el mismo enlace dos veces.
    """

    def get_list_display(self, request):
        self._request_acciones = request
        return super().get_list_display(request)

    @admin.display(description="Acciones")
    def acciones(self, obj):
        request = getattr(self, "_request_acciones", None)
        if request is None:
            return ""

        opts = self.model._meta
        botones = []

        puede_editar = self.has_change_permission(request, obj)
        puede_ver = self.has_view_permission(request, obj)
        if puede_editar or puede_ver:
            url = reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk])
            icono, titulo = ("edit", "Editar") if puede_editar else ("visibility", "Ver")
            botones.append(format_html(
                '<a href="{}" class="tb-accion-btn tb-accion-ver" title="{}">'
                '<span class="material-symbols-outlined">{}</span></a>',
                url, titulo, icono
            ))

        if self.has_delete_permission(request, obj):
            url = reverse(f"admin:{opts.app_label}_{opts.model_name}_delete", args=[obj.pk])
            botones.append(format_html(
                '<a href="{}" class="tb-accion-btn tb-accion-borrar" title="Eliminar">'
                '<span class="material-symbols-outlined">delete</span></a>',
                url
            ))

        return mark_safe(f'<span class="tb-acciones">{"".join(botones)}</span>')


# =========================================================
# CULTIVOS
# =========================================================
@admin.register(Cultivo)
class CultivoAdmin(AccionesColumnaMixin, SimpleHistoryAdmin, ModelAdmin):
    list_display  = ("id", "nombre", "descripcion", "acciones")
    list_display_links = ("id", "nombre")
    search_fields = ("nombre", "descripcion")
    ordering      = ("nombre",)
    list_per_page = 15

    fieldsets = (
        ("Información del Cultivo", {
            "description": "Registre el cultivo agrícola principal. El nombre debe ser único.",
            "fields": ("nombre", "descripcion"),
        }),
        ("Imagen / Fotografía", {
            "description": "Sube un archivo o pega el enlace a una imagen externa. Si se cargan ambos, el archivo subido tiene prioridad.",
            "fields": ("imagen", "imagen_url"),
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            messages.info(request, f"Cultivo '{obj.nombre}' actualizado correctamente.")
        else:
            messages.success(request, f"¡Éxito! Cultivo '{obj.nombre}' registrado. Ahora puede crear sus variedades o clones.")


# =========================================================
# VARIEDADES / CLONES
# =========================================================
@admin.register(VariedadClon)
class VariedadClonAdmin(AccionesColumnaMixin, ModelAdmin):
    list_display  = ("id", "nombre", "cultivo", "acciones")
    list_display_links = ("id", "nombre")
    list_filter   = ("cultivo",)
    search_fields = ("nombre", "cultivo__nombre")
    ordering      = ("cultivo__nombre", "nombre")
    list_per_page = 20

    fieldsets = (
        ("Clasificación Taxonómica Agrícola", {
            "fields": ("cultivo", "nombre", "descripcion"),
        }),
    )


# =========================================================
# MUESTRAS DE SUELO (FORMULARIO CON PLACEHOLDERS)
# =========================================================
class VariedadClonSelect(forms.Select):
    """
    <select> de variedad/clon donde cada <option> lleva data-cultivo="<id>".
    admin/js/filtro_cultivos.js usa ese atributo para mostrar solo las
    variedades del cultivo elegido, sin necesidad de una petición AJAX.
    """
    @property
    def _cultivo_por_variedad(self):
        # Se consulta al primer uso (durante el render del form), nunca al
        # importar el módulo admin.py, para no golpear la BD antes de migrar.
        if not hasattr(self, '_cultivo_por_variedad_cache'):
            self._cultivo_por_variedad_cache = dict(VariedadClon.objects.values_list('id', 'cultivo_id'))
        return self._cultivo_por_variedad_cache

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        try:
            pk = int(str(value))
        except (TypeError, ValueError):
            pk = None
        cultivo_id = self._cultivo_por_variedad.get(pk) if pk else None
        if cultivo_id:
            option['attrs']['data-cultivo'] = cultivo_id
        return option


class MuestraSueloForm(forms.ModelForm):
    """
    Formulario encargado de inyectar las guías de texto invisibles (placeholders)
    que desaparecen al escribir dentro de los inputs de Unfold.
    """
    class Meta:
        model = MuestraSuelo
        fields = '__all__'
        widgets = {
            'codigo': forms.TextInput(attrs={'placeholder': 'Ej: MUESTRA-001, SUELO-CACAO-01...'}),
            'tipo_muestra': forms.TextInput(attrs={'placeholder': 'Ej: Suelo, Suelo Rizosférico...'}),
            'observaciones': forms.Textarea(attrs={'placeholder': 'Escribe notas opcionales sobre el estado o recolección del suelo...', 'rows': 2}),
            'localidad': forms.TextInput(attrs={'placeholder': 'Ej: Manabí, Guayas, Loja...'}),
            'finca_lote': forms.TextInput(attrs={'placeholder': 'Ej: Finca La Esperanza - Lote Norte'}),
            'altitud': forms.NumberInput(attrs={'placeholder': 'Ej: 250'}),
            'variedad_clon': VariedadClonSelect(),
        }


@admin.register(MuestraSuelo)
class MuestraSueloAdmin(AccionesColumnaMixin, SimpleHistoryAdmin, ModelAdmin):
    form = MuestraSueloForm  # 🌟 Acoplamos el formulario con guías de texto

    list_display = ("codigo", "cultivo", "variedad_clon", "localidad", "altitud_display", "tipo_muestra", "fecha_registro_corta", "acciones")
    list_display_links = ("codigo",)
    list_filter   = ("cultivo", "variedad_clon", "tipo_muestra", "fecha_registro")
    search_fields = ("codigo", "cultivo__nombre", "variedad_clon__nombre", "localidad", "finca_lote")
    ordering      = ("-fecha_registro",)
    date_hierarchy = "fecha_registro"
    list_per_page  = 20
    readonly_fields = ("fecha_registro",)

    fieldsets = (
        ("Identificación de la Muestra", {"fields": ("codigo", "tipo_muestra", "observaciones")}),
        ("Clasificación Agrícola", {"fields": ("cultivo", "variedad_clon")}),
        ("Georeferenciación", {"fields": ("localidad", "finca_lote", "altitud")}),
        ("Registro de Sistema", {"fields": ("fecha_registro",), "classes": ("collapse",)}),
    )

    # 🌟 Forzamos la inyección del script de filtrado para Unfold
    class Media:
        js = (
            'admin/js/filtro_cultivos.js',
        )

    @admin.display(description="Altitud (msnm)")
    def altitud_display(self, obj):
        return f"{obj.altitud} m" if obj.altitud is not None else "—"

    @admin.display(description="Fecha de Ingreso", ordering="fecha_registro")
    def fecha_registro_corta(self, obj):
        return obj.fecha_registro.strftime("%d/%m/%Y")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "variedad_clon":
            resolved = request.resolver_match
            if resolved and resolved.kwargs.get('object_id'):
                try:
                    muestra_actual = MuestraSuelo.objects.get(pk=resolved.kwargs['object_id'])
                    kwargs["queryset"] = VariedadClon.objects.filter(cultivo=muestra_actual.cultivo)
                except MuestraSuelo.DoesNotExist:
                    pass
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            messages.info(request, f"Datos de la muestra '{obj.codigo}' modificados.")
        else:
            messages.success(request, f"¡Registro exitoso! Muestra '{obj.codigo}' indexada.")


# =========================================================
# LÓGICA DE ARCHIVOS MOLECULARES
# =========================================================
def _leer_archivo_molecular(archivo_field):
    archivo_field.seek(0)
    nombre = archivo_field.name.lower()
    if nombre.endswith((".xlsx", ".xls")):
        return pd.read_excel(archivo_field)
    raw = archivo_field.read()
    archivo_field.seek(0)
    try:
        return pd.read_csv(io.BytesIO(raw))
    except Exception:
        return pd.read_csv(io.BytesIO(raw), sep="\t")

def _disparar_pipeline(archivo_mol, request):
    ResultadoTaxonomico.objects.filter(archivo=archivo_mol).delete()
    df_raw = _leer_archivo_molecular(archivo_mol.archivo)
    resultado = PipelineProcesamiento.procesar_archivo_df(df_raw)
    
    if not resultado or not resultado.get("data"):
        raise ValueError("El archivo no contiene datos taxonómicos válidos.")
        
    with transaction.atomic():
        ResultadoTaxonomico.objects.bulk_create([
            ResultadoTaxonomico(
                archivo=archivo_mol,
                kingdom=item.get("kingdom", ""), phylum=item.get("phylum", ""),
                tax_class=item.get("tax_class", ""), order=item.get("order", ""),
                family=item.get("family", ""), genus=item.get("genus", ""),
                species=item.get("species", ""), num_hits=item.get("num_hits", 0),
                porcentaje_hits=item.get("%_hits", 0.0),
            ) for item in resultado["data"]
        ])
    return resultado.get("total_registros", len(resultado["data"]))


@admin.register(ArchivoMolecular)
class ArchivoMolecularAdmin(AccionesColumnaMixin, ModelAdmin):
    list_display = ("id", "tipo_badge", "muestra", "archivo_corto", "total_resultados", "fecha_carga_corta", "acciones")
    list_display_links = ("id",)
    list_filter   = ("tipo_analisis", "fecha_carga")
    search_fields = ("muestra__codigo",)
    ordering      = ("-fecha_carga",)
    date_hierarchy = "fecha_carga"
    list_per_page  = 20
    readonly_fields = ("fecha_carga",)

    fieldsets = (
        ("Vinculación con Muestra", {"fields": ("muestra",)}),
        ("Archivo de Secuenciación", {"fields": ("tipo_analisis", "archivo")}),
        ("Registro de Sistema", {"fields": ("fecha_carga",), "classes": ("collapse",)}),
    )

    @admin.display(description="Resultados procesados")
    def total_resultados(self, obj):
        n = ResultadoTaxonomico.objects.filter(archivo=obj).count()
        if n == 0:
            return format_html('<span style="color:#A32D2D;font-weight:500;">{}</span>', "0 — sin procesar")
        return format_html('<span style="color:#085041;font-weight:500;">{} registros</span>', n)

    @admin.display(description="Tipo")
    def tipo_badge(self, obj):
        color, bg = ("#085041", "#E1F5EE") if obj.tipo_analisis == "16S" else ("#5a3a00", "#FAEEDA")
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;border-radius:4px;font-family:monospace;font-size:12px;font-weight:500;">{}</span>',
            bg, color, obj.tipo_analisis
        )

    @admin.display(description="Archivo de Secuenciación (CSV/Excel)")
    def archivo_corto(self, obj):
        if not obj.archivo:
            return "—"
        nombre = obj.archivo.name.rsplit("/", 1)[-1]
        return format_html('<span title="{}">{}</span>', obj.archivo.name, nombre)

    @admin.display(description="Fecha de Subida", ordering="fecha_carga")
    def fecha_carga_corta(self, obj):
        return obj.fecha_carga.strftime("%d/%m/%Y")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        try:
            total = _disparar_pipeline(obj, request)
            if change:
                messages.success(request, f"Archivo [{obj.tipo_analisis}] re-procesado. {total} registros actualizados.")
            else:
                messages.success(request, f"¡Pipeline completado! {total} registros processed.")
        except ValueError as e:
            messages.error(request, f"Error en pipeline: {e}")
        except Exception as e:
            messages.error(request, f"Error inesperado: {e}")


# =========================================================
# RESULTADOS TAXONÓMICOS
# =========================================================
@admin.register(ResultadoTaxonomico)
class ResultadoTaxonomicoAdmin(AccionesColumnaMixin, ModelAdmin):
    list_display  = ("id", "archivo", "genus", "species", "num_hits", "porcentaje_hits", "acciones")
    list_filter   = ("archivo__tipo_analisis",)
    search_fields = ("genus", "species", "phylum", "archivo__muestra__codigo")
    ordering      = ("-porcentaje_hits",)
    list_per_page  = 30

    fieldsets = (
        ("Contexto", {"fields": ("archivo",)}),
        ("Taxonomía", {"fields": ("kingdom", "phylum", "tax_class", "order", "family", "genus", "species")}),
        ("Abundancia", {"fields": ("num_hits", "porcentaje_hits")}),
    )


# =========================================================
# FORMULARIO DE IMPORTACIÓN MASIVA PARA EL ADMIN
# =========================================================
class CatalogoImportAdminForm(forms.Form):
    archivo = forms.FileField(
        label="Archivo CSV / Excel",
        widget=forms.FileInput(attrs={"accept": ".csv,.tsv,.xlsx,.xls"}),
        help_text=(
            "Columnas requeridas: nombre, nivel, marcador (16S o ITS), clasificacion. "
            "Opcionales: descripcion, referencia."
        )
    )


# =========================================================
# CATÁLOGO MICROORGANISMOS
# =========================================================
@admin.register(CatalogoMicroorganismo)
class CatalogoMicroorganismoAdmin(AccionesColumnaMixin, SimpleHistoryAdmin, ModelAdmin):
    change_list_template = "admin/analisis/catalogomicroorganismo/change_list.html"

    list_display  = ("nombre", "nivel", "marcador_badge", "clasificacion_badge", "descripcion_corta", "acciones")
    list_display_links = ("nombre",)
    list_filter   = ("marcador", "clasificacion", "nivel")
    search_fields = ("nombre", "descripcion")
    ordering      = ("nombre",)
    list_per_page  = 20

    fieldsets = (
        ("Identificación Taxonómica", {"fields": ("nombre", "nivel")}),
        ("Tipo de Organismo", {
            "description": "Seleccione el marcador molecular que identifica si es Bacteria (16S) o Hongo (ITS).",
            "fields": ("marcador",),
        }),
        ("Clasificación Funcional", {"fields": ("clasificacion", "descripcion", "referencia")}),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "importar/",
                self.admin_site.admin_view(self.importar_view),
                name="catalogo_importar",
            ),
        ]
        return custom + urls

    def importar_view(self, request):
        """Vista de importación masiva desde CSV/Excel accesible en el admin."""
        from analisis.services.business.catalog_service import CatalogService

        if request.method == "POST":
            form = CatalogoImportAdminForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    creados, actualizados, errores = CatalogService.importar_desde_archivo(
                        form.cleaned_data["archivo"]
                    )
                    resumen = f"{creados} creados, {actualizados} actualizados"
                    if errores:
                        self.message_user(
                            request,
                            f"Importación parcial: {resumen}. {errores} filas omitidas.",
                            messages.WARNING,
                        )
                    else:
                        self.message_user(request, f"Importación exitosa: {resumen}.", messages.SUCCESS)
                except ValueError as exc:
                    self.message_user(request, str(exc), messages.ERROR)
                except Exception as exc:
                    self.message_user(request, f"Error inesperado: {exc}", messages.ERROR)
            else:
                self.message_user(request, "Archivo no válido.", messages.ERROR)
            return HttpResponseRedirect("../")

        # GET → render formulario de importación
        form = CatalogoImportAdminForm()
        context = {
            **self.admin_site.each_context(request),
            "title": "Importar Catálogo de Microorganismos",
            "form": form,
            "opts": self.model._meta,
        }
        return TemplateResponse(
            request,
            "admin/analisis/catalogomicroorganismo/importar.html",
            context,
        )

    @admin.display(description="Tipo")
    def marcador_badge(self, obj):
        if obj.marcador == "16S":
            return mark_safe(
                '<span style="background:#E1F5EE;color:#085041;padding:3px 10px;border-radius:20px;'
                'font-size:12px;font-weight:500;">🦠 Bacteria</span>'
            )
        return mark_safe(
            '<span style="background:#FAEEDA;color:#5a3a00;padding:3px 10px;border-radius:20px;'
            'font-size:12px;font-weight:500;">🍄 Hongo</span>'
        )

    @admin.display(description="Clasificación")
    def clasificacion_badge(self, obj):
        colores = {
            "benefico": ("#E1F5EE", "#085041"), "fitopatogeno": ("#FAEEDA", "#5a3a00"),
            "neutral": ("#F1EFE8", "#5F5E5A"), "sin_clasificar": ("#F1EFE8", "#888780"),
        }
        bg, color = colores.get(obj.clasificacion, ("#F1EFE8", "#5F5E5A"))
        return format_html(
            '<span style="background:{};color:{};padding:3px 10px;border-radius:20px;font-size:12px;font-weight:500;">{}</span>',
            bg, color, obj.get_clasificacion_display()
        )

    @admin.display(description="Descripción")
    def descripcion_corta(self, obj):
        if not obj.descripcion:
            return "—"
        if len(obj.descripcion) <= 80:
            return obj.descripcion
        return format_html('<span title="{}">{}…</span>', obj.descripcion, obj.descripcion[:80])


# =========================================================
# FORMULARIOS PARA LA CREACIÓN DE USUARIO
# =========================================================
class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ("username",)

class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = Usuario
        fields = "__all__"


# =========================================================
# USUARIOS
# =========================================================
@admin.register(Usuario)
class UsuarioAdmin(AccionesColumnaMixin, SimpleHistoryAdmin, BaseUserAdmin, ModelAdmin):
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display  = ("email", "nombre_completo", "rol_badge", "is_active", "is_staff", "date_joined_corta", "acciones")
    list_display_links = ("email",)
    list_filter   = ("rol", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering      = ("username",)
    list_per_page  = 20

    @admin.display(description="Nombre")
    def nombre_completo(self, obj):
        nombre = f"{obj.first_name} {obj.last_name}".strip()
        return nombre if nombre else "—"

    @admin.display(description="Fecha de Registro", ordering="date_joined")
    def date_joined_corta(self, obj):
        return obj.date_joined.strftime("%d/%m/%Y")

    @admin.display(description="Rol")
    def rol_badge(self, obj):
        colores = {
            "admin":      ("#E1F5EE", "#085041"),
            "docente":    ("#E6F1FB", "#0C447C"),
            "estudiante": ("#F1EFE8", "#5F5E5A"),
        }
        bg, color = colores.get(obj.rol, ("#F1EFE8", "#5F5E5A"))
        return format_html(
            '<span style="background:{};color:{};padding:3px 10px;border-radius:20px;font-size:12px;font-weight:500;">{}</span>',
            bg, color, dict(obj.ROLES).get(obj.rol, obj.rol)
        )

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj) or [])
        fieldsets.append((
            "Rol en BioMicro UTC",
            {"fields": ("rol",), "description": "Asigne el rol para determinar los permisos de visualización."}
        ))
        return fieldsets

    def save_model(self, request, obj, form, change):
        # Sincronizar is_staff con el rol de BioMicro para que el acceso
        # al panel /admin/ quede consistente con el rol asignado.
        if obj.rol == "admin":
            obj.is_staff = True
            obj.is_superuser = True
        else:
            obj.is_staff = False
            obj.is_superuser = False
        super().save_model(request, obj, form, change)
        if obj.rol == "admin":
            messages.success(
                request,
                f"✔ {obj.email} tiene ahora acceso al panel de administración (/admin/)."
            )
        elif change:
            messages.info(
                request,
                f"Acceso al panel de administración actualizado para {obj.email}."
            )


# =========================================================
# BADGES PARA LA BARRA LATERAL
# =========================================================
def badge_archivos_sin_procesar(request):
    archivos_con = ResultadoTaxonomico.objects.values("archivo_id").distinct()
    n = ArchivoMolecular.objects.exclude(id__in=archivos_con).count()
    return n if n > 0 else None


def badge_usuarios_nuevos(request):
    from django.utils import timezone
    from datetime import timedelta
    n = Usuario.objects.filter(
        date_joined__gte=timezone.now() - timedelta(days=7)
    ).count()
    return n if n > 0 else None


# =========================================================
# CALLBACK DEL DASHBOARD
# =========================================================
STORAGE_WARNING_PCT = 70
STORAGE_DANGER_PCT = 85


def _nivel_por_umbral(valor, umbral_warning, umbral_danger):
    """'ok' / 'warning' / 'danger' según en qué franja cae el valor — un
    solo lugar para esta lógica, en vez de repetir el mismo {% if/elif %}
    tanto en Python como en la plantilla."""
    if valor >= umbral_danger:
        return "danger"
    if valor >= umbral_warning:
        return "warning"
    return "ok"


def dashboard_callback(request, context):
    import shutil
    import json
    from django.conf import settings as django_settings
    from django.db.models import Count
    from django.utils import timezone
    from datetime import timedelta

    # Almacenamiento del servidor
    try:
        uso = shutil.disk_usage(django_settings.BASE_DIR)
        total_gb = round(uso.total / 1024 ** 3, 1)
        usado_gb = round(uso.used  / 1024 ** 3, 1)
        libre_gb = round(uso.free  / 1024 ** 3, 1)
        pct      = round(uso.used / uso.total * 100, 1)
    except Exception:
        total_gb = usado_gb = libre_gb = pct = 0

    context["storage"] = {
        "total": total_gb,
        "usado": usado_gb,
        "libre": libre_gb,
        "pct":   pct,
        "nivel": _nivel_por_umbral(pct, STORAGE_WARNING_PCT, STORAGE_DANGER_PCT),
    }

    # Estadísticas rápidas
    archivos_con = ResultadoTaxonomico.objects.values("archivo_id").distinct()
    sin_procesar = ArchivoMolecular.objects.exclude(id__in=archivos_con).count()

    context["stats"] = {
        "muestras":     MuestraSuelo.objects.count(),
        "archivos":     ArchivoMolecular.objects.count(),
        "catalogo":     CatalogoMicroorganismo.objects.count(),
        "usuarios":     Usuario.objects.count(),
        "sin_procesar": sin_procesar,
    }

    # ── Gráfico: distribución del catálogo por rol funcional ──
    conteos_cat = {
        row["clasificacion"]: row["total"]
        for row in CatalogoMicroorganismo.objects.values("clasificacion").annotate(total=Count("id"))
    }
    fig_catalogo, context["catalogo_legend"] = _figura_catalogo_distribucion(conteos_cat)
    context["chart_catalogo_json"] = json.dumps(fig_catalogo, default=str)

    # ── Top 3 cultivos con más muestras registradas ──
    colores_rango = ["#1D9E75", "#0F6E56", "#BA7517"]
    top_cultivos_qs = Cultivo.objects.annotate(
        total_muestras=Count("muestras")
    ).filter(total_muestras__gt=0).order_by("-total_muestras")[:3]
    context["top_cultivos"] = [
        {"cultivo": c, "rango": i + 1, "color": colores_rango[i]}
        for i, c in enumerate(top_cultivos_qs)
    ]

    # Notificaciones automáticas
    notifs = []
    if sin_procesar > 0:
        notifs.append({
            "tipo": "warning",
            "icono": "warning",
            "msg": f"{sin_procesar} archivo(s) molecular(es) pendiente(s) de procesar",
        })

    nuevos = Usuario.objects.filter(
        date_joined__gte=timezone.now() - timedelta(days=7)
    ).count()
    if nuevos > 0:
        notifs.append({
            "tipo": "info",
            "icono": "person_add",
            "msg": f"{nuevos} usuario(s) registrado(s) en los últimos 7 días",
        })

    if pct >= STORAGE_DANGER_PCT:
        notifs.append({
            "tipo": "error",
            "icono": "storage",
            "msg": f"Almacenamiento crítico: {pct}% utilizado",
        })
    elif pct >= STORAGE_WARNING_PCT:
        notifs.append({
            "tipo": "warning",
            "icono": "storage",
            "msg": f"Almacenamiento alto: {pct}% utilizado",
        })

    # Auditoría: intentos de acceso fallidos en las últimas 24h
    fallidos_24h = EventoAcceso.objects.filter(
        tipo="login_fallido", fecha__gte=timezone.now() - timedelta(hours=24)
    ).count()
    if fallidos_24h >= 10:
        notifs.append({
            "tipo": "error",
            "icono": "gpp_maybe",
            "msg": f"{fallidos_24h} intentos de acceso fallidos en las últimas 24h — revisar Auditoría › Eventos de Acceso",
        })
    elif fallidos_24h >= 5:
        notifs.append({
            "tipo": "warning",
            "icono": "gpp_maybe",
            "msg": f"{fallidos_24h} intentos de acceso fallidos en las últimas 24h",
        })

    if not notifs:
        notifs.append({
            "tipo": "success",
            "icono": "check_circle",
            "msg": "Sistema funcionando con normalidad",
        })

    context["notifications"] = notifs
    return context


# =========================================================
# AUDITORÍA — Datos compartidos entre el dashboard y las exportaciones
# =========================================================
def _calcular_auditoria(qs):
    """A partir del queryset ya filtrado por el changelist, arma las
    estadísticas + las dos series de datos (eventos por día, fallidos por
    usuario) que usan tanto el dashboard del admin como Excel/PDF — un solo
    lugar donde tocar la lógica en vez de tenerla repetida tres veces."""
    from datetime import timedelta
    from django.db.models import Count
    from django.db.models.functions import TruncDate
    from django.utils import timezone

    stats = {
        "total":            qs.count(),
        "exitosos":         qs.filter(tipo="login_ok").count(),
        "fallidos":         qs.filter(tipo="login_fallido").count(),
        "usuarios_activos": qs.filter(tipo="login_ok").exclude(usuario__isnull=True)
                                .values("usuario").distinct().count(),
    }

    desde = timezone.now() - timedelta(days=14)
    por_dia = list(
        qs.filter(fecha__gte=desde)
          .annotate(dia=TruncDate("fecha"))
          .values("dia", "tipo")
          .annotate(total=Count("id"))
          .order_by("dia")
    )

    fallidos_por_usuario = list(
        qs.filter(tipo="login_fallido")
          .values("username_intentado")
          .annotate(total=Count("id"))
          .order_by("-total")[:10]
    )

    return stats, por_dia, fallidos_por_usuario


# =========================================================
# AUDITORÍA — Gráficos (funciones libres para poder probarlas solas)
# =========================================================
# Paleta de estado (no categórica arbitraria): verde=éxito, rojo=crítico,
# gris=neutral — las mismas tres que ya usan tipo_badge/KPIs/Excel/PDF, así
# que se validan como escala de estado fija (WCAG por color, no CVD/chroma
# de paleta categórica: swapping el orden SÍ cambiaría el significado).
# El rojo y el gris de modo claro no alcanzan 3:1 sobre una tarjeta oscura
# (2.46:1 y 2.68:1 medidos con el validador de la skill dataviz), así que
# el modo oscuro usa variantes más claras de la misma familia — el verde
# no necesitó ajuste (ya da 5.14:1 en ambos fondos).
_AUD_COLOR = {
    "light": {"login_ok": "#1D9E75", "login_fallido": "#A32D2D", "logout": "#5F5E5A",
              "bg": "#ffffff", "grid": "#EEF0EC", "text": "#5F5E5A", "line": "#ffffff",
              "hover_bg": "#ffffff", "hover_text": "#1a1a18", "hover_border": "#D3D1C7"},
    "dark":  {"login_ok": "#1D9E75", "login_fallido": "#D64545", "logout": "#8A8880",
              "bg": "#1a1a19", "grid": "rgba(255,255,255,0.08)", "text": "#A0A09A", "line": "#1a1a19",
              "hover_bg": "#1e1e1c", "hover_text": "#e5e5e0", "hover_border": "#333330"},
}
_MESES_ES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
             7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}


def _fecha_corta_es(iso):
    """'2026-07-16' -> '16 jul' (evita depender del locale del servidor)."""
    y, m, d = (int(p) for p in iso.split("-"))
    return f"{d} {_MESES_ES[m]}"


def _figura_eventos_por_dia(filas):
    """filas: [{'dia': date, 'tipo': str, 'total': int}, ...] ->
    {"light": <figura Plotly>, "dark": <figura Plotly>}."""
    import plotly.graph_objects as go
    from collections import defaultdict

    dias = sorted({str(f["dia"]) for f in filas})
    por_tipo = defaultdict(lambda: {d: 0 for d in dias})
    for f in filas:
        por_tipo[f["tipo"]][str(f["dia"])] = f["total"]

    nombres = {"login_ok": "Exitosos", "login_fallido": "Fallidos", "logout": "Cierres de sesión"}
    etiquetas_x = [_fecha_corta_es(d) for d in dias]

    figuras = {}
    for modo, C in _AUD_COLOR.items():
        fig = go.Figure()
        tipos = ("login_ok", "login_fallido", "logout")
        for i, tipo in enumerate(tipos):
            valores = [por_tipo[tipo][d] for d in dias]
            fig.add_trace(go.Bar(
                name=nombres[tipo], x=etiquetas_x, y=valores,
                marker=dict(
                    color=C[tipo],
                    line=dict(color=C["line"], width=2),  # separa visualmente los segmentos apilados
                    # Solo el segmento de arriba (logout, el último en dibujarse)
                    # lleva esquinas redondeadas: es el único "extremo libre"
                    # de la barra apilada; los de abajo quedan rectos.
                    cornerradius=4 if tipo == "logout" else 0,
                ),
                hovertemplate=f"<b>{nombres[tipo]}</b>: %{{y}}<extra></extra>",
            ))
        fig.update_layout(
            autosize=True,
            barmode="stack", bargap=0.35, height=300, margin=dict(t=30, b=10, l=36, r=10),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Outfit, sans-serif", size=11, color=C["text"]),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5,
                font=dict(color=C["text"]),
            ),
            xaxis=dict(showgrid=False, zeroline=False, linecolor=C["grid"], tickfont=dict(color=C["text"])),
            yaxis=dict(showgrid=True, gridcolor=C["grid"], zeroline=False, tickfont=dict(color=C["text"])),
            hoverlabel=dict(bgcolor=C["hover_bg"], font=dict(color=C["hover_text"]), bordercolor=C["hover_border"]),
            hovermode="x unified",
        )
        figuras[modo] = fig.to_dict()
    return figuras


def _figura_fallidos_por_usuario(filas):
    """filas: [{'username_intentado': str, 'total': int}, ...] ->
    {"light": <figura Plotly>, "dark": <figura Plotly>}."""
    import plotly.graph_objects as go

    if not filas:
        vacio = {"data": [], "layout": {"height": 220}}
        return {"light": vacio, "dark": vacio}

    nombres = [f["username_intentado"] or "(vacío)" for f in filas]
    valores = [f["total"] for f in filas]

    figuras = {}
    for modo, C in _AUD_COLOR.items():
        fig = go.Figure(go.Bar(
            x=valores, y=nombres, orientation="h",
            marker=dict(color=C["login_fallido"], cornerradius=4),
            text=valores, texttemplate="%{x}", textposition="outside",
            textfont=dict(color=C["text"], size=11),
            cliponaxis=False,  # que la etiqueta del valor más alto no se corte contra el borde
            hovertemplate="<b>%{y}</b>: %{x} intento(s) fallido(s)<extra></extra>",
        ))
        fig.update_layout(
            autosize=True,
            bargap=0.35,
            height=max(220, len(nombres) * 32 + 60),
            margin=dict(t=10, b=30, l=140, r=30),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Outfit, sans-serif", size=11, color=C["text"]),
            yaxis=dict(autorange="reversed", showgrid=False, tickfont=dict(color=C["text"])),
            xaxis=dict(dtick=1, showgrid=True, gridcolor=C["grid"], zeroline=False, tickfont=dict(color=C["text"])),
            hoverlabel=dict(bgcolor=C["hover_bg"], font=dict(color=C["hover_text"]), bordercolor=C["hover_border"]),
        )
        figuras[modo] = fig.to_dict()
    return figuras


def _figura_catalogo_distribucion(conteos):
    """conteos: {'benefico': N, 'fitopatogeno': N, ...} -> (dict de figura Plotly, leyenda HTML).

    La leyenda nativa de Plotly (horizontal) no envuelve a varias líneas
    cuando las 4 etiquetas no entran en una sola fila: se superponen en vez
    de acomodarse. Por eso el gráfico se dibuja sin leyenda (showlegend=False)
    y la leyenda se arma aparte como datos simples para un `flex-wrap` en
    HTML/CSS, que sí envuelve correctamente sin importar el ancho.
    """
    import plotly.graph_objects as go

    etiquetas = {
        "benefico": "Benéfico", "fitopatogeno": "Fitopatógeno",
        "neutral": "Neutral", "sin_clasificar": "Sin clasificación",
    }
    colores = {
        "benefico": "#1D9E75", "fitopatogeno": "#BA7517",
        "neutral": "#185FA5", "sin_clasificar": "#94a3b8",
    }
    claves = [c for c in ("benefico", "fitopatogeno", "neutral", "sin_clasificar") if conteos.get(c)]
    if not claves:
        return {"data": [], "layout": {"height": 260}}, []

    total = sum(conteos[c] for c in claves)
    leyenda = [
        {
            "label": etiquetas[c],
            "color": colores[c],
            "valor": conteos[c],
            "pct": round(conteos[c] / total * 100, 1) if total else 0,
        }
        for c in claves
    ]

    fig = go.Figure(go.Pie(
        labels=[etiquetas[c] for c in claves],
        values=[conteos[c] for c in claves],
        marker=dict(colors=[colores[c] for c in claves]),
        hole=0.62,
        textinfo="percent",
        textfont=dict(size=12),
    ))
    fig.update_layout(
        autosize=True,
        height=260,
        margin=dict(t=10, b=10, l=10, r=10),
        paper_bgcolor="white",
        font=dict(family="Outfit, sans-serif", size=12),
        showlegend=False,
    )
    return fig.to_dict(), leyenda


# =========================================================
# AUDITORÍA — Eventos de Acceso (login / logout / fallidos)
# =========================================================
@admin.register(EventoAcceso)
class EventoAccesoAdmin(AccionesColumnaMixin, ModelAdmin):
    """
    Bitácora de solo lectura. No se puede crear, editar ni borrar desde el
    admin: los registros de auditoría solo tienen valor si son inmutables —
    si cualquiera con sesión abierta pudiera editarlos o borrarlos, dejarían
    de servir como evidencia ante un incidente. Se llenan solos vía señales
    (ver AnalisisConfig.ready() en apps.py).
    """
    list_display   = ("tipo_badge", "usuario_o_intento", "ip_address", "dispositivo", "fecha_relativa", "acciones")
    list_filter    = ("tipo", "usuario", "fecha")
    search_fields  = ("usuario__username", "usuario__email", "username_intentado", "ip_address")
    date_hierarchy = "fecha"
    ordering       = ("-fecha",)
    list_per_page  = 30
    list_fullwidth = True

    # Inyecta las tarjetas de estadísticas + gráficos justo antes de la
    # tabla — gancho nativo de Unfold, no requiere sobrescribir todo el
    # template del changelist (ver ChangeListView/get_urls más abajo).
    list_before_template = "admin/analisis/eventoacceso/dashboard_stats.html"

    # Vista de detalle: de solo lectura (has_change_permission=False ya lo
    # fuerza), pero con fieldsets propios para que se lea bien en vez de
    # mostrar los campos en el orden crudo del modelo.
    readonly_fields = (
        "tipo", "usuario", "username_intentado", "ip_address",
        "user_agent", "navegador", "sistema_operativo", "fecha",
    )
    fieldsets = (
        ("Evento", {"fields": ("tipo", "fecha")}),
        ("Usuario", {"fields": ("usuario", "username_intentado")}),
        ("Origen de la conexión", {"fields": ("ip_address", "navegador", "sistema_operativo", "user_agent")}),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # ── URLs propias: exportación ──────────────────────────────────────
    def get_urls(self):
        urls = super().get_urls()
        propias = [
            path("exportar/excel/", self.admin_site.admin_view(self.exportar_excel),
                 name="analisis_eventoacceso_exportar_excel"),
            path("exportar/pdf/", self.admin_site.admin_view(self.exportar_pdf),
                 name="analisis_eventoacceso_exportar_pdf"),
        ]
        return propias + urls

    # ── Dashboard: estadísticas + datos de gráficos ─────────────────────
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        try:
            qs = response.context_data["cl"].queryset
        except (AttributeError, KeyError, TypeError):
            return response

        import json

        stats, por_dia, fallidos_por_usuario = _calcular_auditoria(qs)
        response.context_data["auditoria_stats"] = stats
        response.context_data["grafico_eventos_json"] = json.dumps(
            _figura_eventos_por_dia(por_dia), default=str
        )
        response.context_data["grafico_fallidos_json"] = json.dumps(
            _figura_fallidos_por_usuario(fallidos_por_usuario), default=str
        )
        return response

    # ── Exportación ──────────────────────────────────────────────────
    # Paleta institucional (misma que dashboard_stats.html y admin_personalizado.css
    # --tb-*, y el motor de reportes de export_service.py) para que ambos
    # archivos se vean como parte del mismo sistema, no como algo aparte.
    _KPI_ESTILO = (
        # clave,               etiqueta,             bg claro,  texto oscuro
        ("total",             "Total de eventos",    "E3F2FD", "0D3E8C"),
        ("exitosos",          "Inicios exitosos",     "E1F5EE", "085041"),
        ("fallidos",          "Intentos fallidos",    "FCEBEB", "6b1212"),
        ("usuarios_activos",  "Usuarios activos",     "EEE8F5", "4A3369"),
    )
    _TIPO_BADGE_XLSX = {
        "login_ok":      ("E1F5EE", "085041"),
        "login_fallido": ("FCEBEB", "A32D2D"),
        "logout":        ("F1EFE8", "5F5E5A"),
    }

    def exportar_excel(self, request):
        from django.http import HttpResponse
        from django.utils import timezone
        from typing import cast
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.worksheet import Worksheet
        from openpyxl.worksheet.table import Table as XLTable, TableStyleInfo
        from openpyxl.chart import BarChart, Reference
        from openpyxl.chart.series import DataPoint

        cl = self.get_changelist_instance(request)
        qs = cl.queryset
        stats, por_dia, fallidos_por_usuario = _calcular_auditoria(qs)
        ahora = timezone.now()

        CV_OSC, CV = "0F6E56", "1D9E75"
        _side = Side(style="thin", color="D9D9D9")
        BORDE = Border(left=_side, right=_side, top=_side, bottom=_side)
        al_c  = Alignment(horizontal="center", vertical="center", wrap_text=True)
        al_l  = Alignment(horizontal="left", vertical="center", wrap_text=True)

        wb = Workbook()

        # ── Hoja 1: Resumen ──────────────────────────────────────────
        # Workbook.active está tipado Worksheet | None en los stubs de
        # openpyxl (una hoja de cálculo podría técnicamente no tener
        # ninguna) pero un Workbook() recién creado siempre trae una hoja
        # activa por defecto — el cast no cambia nada en runtime.
        ws = cast(Worksheet, wb.active)
        ws.title = "Resumen"
        ws.sheet_view.showGridLines = False

        ws.merge_cells("A1:H1")
        c = ws["A1"]; c.value = "BioMicro — Auditoría de Accesos"
        c.font = Font(bold=True, size=16, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=CV_OSC)
        c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.row_dimensions[1].height = 32

        ws.merge_cells("A2:H2")
        c = ws["A2"]
        filtro_txt = " (con filtros aplicados)" if request.GET else " (todos los eventos)"
        c.value = f"Generado el {ahora:%d/%m/%Y %H:%M} — {stats['total']} registro(s){filtro_txt}"
        c.font = Font(italic=True, size=10, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=CV)
        c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.row_dimensions[2].height = 20

        # Tarjetas KPI: 4 tarjetas de 2 columnas cada una (A-B, C-D, E-F, G-H)
        fila_kpi_val, fila_kpi_lbl = 4, 5
        for i, (clave, etiqueta, bg, fg) in enumerate(self._KPI_ESTILO):
            col_ini = get_column_letter(i * 2 + 1)
            col_fin = get_column_letter(i * 2 + 2)
            for fila, val, tam, negrita in (
                (fila_kpi_val, stats[clave], 22, True),
                (fila_kpi_lbl, etiqueta.upper(), 8.5, False),
            ):
                ws.merge_cells(f"{col_ini}{fila}:{col_fin}{fila}")
                cc = ws[f"{col_ini}{fila}"]
                cc.value = val
                cc.font = Font(bold=negrita, size=tam, color=fg)
                cc.fill = PatternFill("solid", fgColor=bg)
                cc.alignment = al_c
            ws.row_dimensions[fila_kpi_val].height = 34
            ws.row_dimensions[fila_kpi_lbl].height = 16

        for col in "ABCDEFGH":
            ws.column_dimensions[col].width = 13

        # ── Serie: eventos por día (últimos 14 días) + gráfico nativo ──
        fila = 8
        ws.cell(row=fila, column=1, value="Eventos por día (últimos 14 días)").font = Font(bold=True, size=12, color=CV_OSC)
        fila += 1
        cab_dia = fila
        for j, txt in enumerate(("Día", "Exitosos", "Fallidos", "Cierres de sesión"), start=1):
            cc = ws.cell(row=cab_dia, column=j, value=txt)
            cc.font = Font(bold=True, color="FFFFFF")
            cc.fill = PatternFill("solid", fgColor=CV_OSC)
            cc.alignment = al_c
            cc.border = BORDE

        dias = sorted({str(f["dia"]) for f in por_dia})
        from collections import defaultdict
        por_tipo = defaultdict(lambda: {d: 0 for d in dias})
        for f in por_dia:
            por_tipo[f["tipo"]][str(f["dia"])] = f["total"]
        for i, d in enumerate(dias):
            r = cab_dia + 1 + i
            valores = [d, por_tipo["login_ok"][d], por_tipo["login_fallido"][d], por_tipo["logout"][d]]
            for j, v in enumerate(valores, start=1):
                cc = ws.cell(row=r, column=j, value=v)
                cc.border = BORDE
                cc.alignment = al_c if j > 1 else al_l
        fila_fin_dia = cab_dia + len(dias)

        if dias:
            ch = BarChart()
            ch.type, ch.grouping, ch.overlap = "col", "stacked", 100
            ch.title, ch.style = "Eventos por día", 10
            ch.width, ch.height = 22, 9
            ch.y_axis.title = "Eventos"
            for j, color in ((2, "085041"), (3, "A32D2D"), (4, "5F5E5A")):
                dat = Reference(ws, min_col=j, max_col=j, min_row=cab_dia, max_row=fila_fin_dia)
                ch.add_data(dat, titles_from_data=True)
                ch.series[-1].graphicalProperties.solidFill = color
            cat = Reference(ws, min_col=1, min_row=cab_dia + 1, max_row=fila_fin_dia)
            ch.set_categories(cat)
            ws.add_chart(ch, f"A{fila_fin_dia + 3}")
        else:
            ws.cell(row=cab_dia + 1, column=1, value="Sin eventos en los últimos 14 días.").font = Font(italic=True, color="888888")
            fila_fin_dia = cab_dia + 1

        # ── Serie: top 10 fallidos por usuario + gráfico nativo ─────────
        fila_top = max(fila_fin_dia + 22, cab_dia + 2)
        ws.cell(row=fila_top, column=1, value="Intentos fallidos por usuario (top 10)").font = Font(bold=True, size=12, color=CV_OSC)
        fila_top += 1
        cab_top = fila_top
        for j, txt in enumerate(("Usuario / correo intentado", "Intentos fallidos"), start=1):
            cc = ws.cell(row=cab_top, column=j, value=txt)
            cc.font = Font(bold=True, color="FFFFFF")
            cc.fill = PatternFill("solid", fgColor="A32D2D")
            cc.alignment = al_c
            cc.border = BORDE

        for i, f in enumerate(fallidos_por_usuario):
            r = cab_top + 1 + i
            ws.cell(row=r, column=1, value=f["username_intentado"] or "(vacío)").border = BORDE
            ws.cell(row=r, column=1).alignment = al_l
            ws.cell(row=r, column=2, value=f["total"]).border = BORDE
            ws.cell(row=r, column=2).alignment = al_c
        fila_fin_top = cab_top + len(fallidos_por_usuario)

        if fallidos_por_usuario:
            ch2 = BarChart()
            ch2.type, ch2.grouping = "bar", "clustered"
            ch2.title, ch2.style, ch2.legend = "Top 10 intentos fallidos", 10, None
            ch2.width, ch2.height = 22, max(7, len(fallidos_por_usuario) * 0.8)
            dat = Reference(ws, min_col=2, min_row=cab_top, max_row=fila_fin_top)
            ch2.add_data(dat, titles_from_data=True)
            cat = Reference(ws, min_col=1, min_row=cab_top + 1, max_row=fila_fin_top)
            ch2.set_categories(cat)
            for i in range(len(fallidos_por_usuario)):
                dp = DataPoint(idx=i)
                dp.graphicalProperties.solidFill = "A32D2D"
                ch2.series[0].dPt.append(dp)
            ws.add_chart(ch2, f"A{fila_fin_top + 3}")
        else:
            ws.cell(row=cab_top + 1, column=1, value="Sin intentos fallidos registrados.").font = Font(italic=True, color="888888")

        # ── Hoja 2: detalle completo de eventos ─────────────────────────
        ws2 = wb.create_sheet("Eventos de Acceso")
        columnas = ["Tipo", "Usuario", "Intento", "IP", "Navegador", "Sistema operativo", "Fecha"]
        for j, txt in enumerate(columnas, start=1):
            cc = ws2.cell(row=1, column=j, value=txt)
            cc.font = Font(bold=True, color="FFFFFF")
            cc.fill = PatternFill("solid", fgColor=CV_OSC)
            cc.alignment = al_c
            cc.border = BORDE

        for i, e in enumerate(qs):
            r = i + 2
            valores = [
                e.get_tipo_display(),
                e.usuario.username if e.usuario_id else "",
                e.username_intentado,
                e.ip_address or "—",
                e.navegador,
                e.sistema_operativo,
                e.fecha.strftime("%Y-%m-%d %H:%M:%S"),
            ]
            for j, v in enumerate(valores, start=1):
                cc = ws2.cell(row=r, column=j, value=v)
                cc.border = BORDE
                cc.alignment = al_l
            bg, fg = self._TIPO_BADGE_XLSX.get(e.tipo, ("F1EFE8", "5F5E5A"))
            cc_tipo = ws2.cell(row=r, column=1)
            cc_tipo.fill = PatternFill("solid", fgColor=bg)
            cc_tipo.font = Font(bold=True, color=fg)

        n = qs.count()
        if n:
            ref = f"A1:{get_column_letter(len(columnas))}{n + 1}"
            tabla = XLTable(displayName="TablaEventosAcceso", ref=ref)
            tabla.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium7", showFirstColumn=False, showLastColumn=False,
                showRowStripes=True, showColumnStripes=False,
            )
            ws2.add_table(tabla)
        ws2.freeze_panes = "A2"
        anchos = {"A": 20, "B": 18, "C": 26, "D": 16, "E": 26, "F": 20, "G": 20}
        for col, w in anchos.items():
            ws2.column_dimensions[col].width = w

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        resp = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        nombre = ahora.strftime("auditoria_accesos_%Y%m%d_%H%M%S.xlsx")
        resp["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return resp

    def exportar_pdf(self, request):
        from django.http import HttpResponse
        from django.utils import timezone
        from xml.sax.saxutils import escape as _xml_escape
        from reportlab.lib import colors as rl_colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from analisis.services.business.export_service import (
            _get_styles, _pdf_footer, _seccion_hdr, _kpi_tiles, _C_PRIMARY, _C_SECONDARY,
        )

        cl = self.get_changelist_instance(request)
        qs = cl.queryset
        stats, _por_dia, _fallidos = _calcular_auditoria(qs)
        ahora = timezone.now()
        S = _get_styles()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=landscape(A4),
            topMargin=30, bottomMargin=40, leftMargin=30, rightMargin=30,
        )
        ancho_util = landscape(A4)[0] - 60
        contenido = []

        # ── Banner de portada (mismo lenguaje visual que el resto de reportes) ──
        t_banner = Table(
            [[Paragraph("<b>BioMicro — Auditoría de Accesos</b>", S["titulo"])],
             [Paragraph("Bitácora de inicios de sesión, cierres y accesos fallidos", S["subtitle"])]],
            colWidths=[ancho_util],
        )
        t_banner.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), _C_PRIMARY),
            ("TOPPADDING",    (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (0, 0), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 16),
        ]))
        contenido.append(t_banner)

        filtro_txt = "con filtros aplicados" if request.GET else "todos los eventos registrados"
        t_meta = Table(
            [[Paragraph(f"  Generado: {ahora:%d/%m/%Y %H:%M} · {stats['total']} registro(s) · {filtro_txt}", S["body_sm"])]],
            colWidths=[ancho_util],
        )
        t_meta.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), _C_SECONDARY),
            ("TEXTCOLOR",     (0, 0), (-1, -1), rl_colors.white),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        contenido.append(t_meta)
        contenido.append(Spacer(1, 14))

        contenido.append(_kpi_tiles([
            {"val": stats["total"],             "lbl": "TOTAL DE EVENTOS"},
            {"val": stats["exitosos"],          "lbl": "INICIOS EXITOSOS"},
            {"val": stats["fallidos"],          "lbl": "INTENTOS FALLIDOS"},
            {"val": stats["usuarios_activos"],  "lbl": "USUARIOS ACTIVOS"},
        ], ancho_util, S))
        contenido.append(Spacer(1, 14))

        contenido.append(_seccion_hdr("Detalle de eventos", ancho_util, S))
        contenido.append(Spacer(1, 6))

        LIMITE = 3000  # límite razonable: un PDF con más filas deja de ser legible
        TIPO_COLOR = {"login_ok": "#085041", "login_fallido": "#A32D2D", "logout": "#5F5E5A"}
        cabecera = ["Tipo", "Usuario", "IP", "Navegador", "S.O.", "Fecha"]
        filas = [[Paragraph(t, S["th_dark"]) for t in cabecera]]
        for e in qs[:LIMITE]:
            # username_intentado es texto libre escrito por quien sea que
            # intentó loguearse (válido también para anónimos que fallan el
            # login) — a diferencia de navegador/sistema_operativo (que
            # _parsear_user_agent() en models.py reduce a una whitelist fija
            # de valores como "Chrome"/"Windows"/"Otro"), esto llega tal cual
            # se escribió. Paragraph() de reportlab SÍ interpreta markup
            # (<font>, <a href>, hasta <img src> con fetch remoto), así que
            # sin escapar, cualquiera podía inyectar HTML/XML en el PDF de
            # auditoría que después abre un admin: texto oculto, enlaces de
            # phishing embebidos o SSRF ciego vía <img src="http://...">.
            usuario_txt = (
                e.usuario.username if e.usuario_id
                else _xml_escape(e.username_intentado or "—")
            )
            filas.append([
                Paragraph(f'<font color="{TIPO_COLOR.get(e.tipo, "#5F5E5A")}"><b>{e.get_tipo_display()}</b></font>', S["body_sm"]),
                Paragraph(usuario_txt, S["body_sm"]),
                Paragraph(e.ip_address or "—", S["body_sm"]),
                Paragraph(e.navegador or "—", S["body_sm"]),
                Paragraph(e.sistema_operativo or "—", S["body_sm"]),
                Paragraph(e.fecha.strftime("%d/%m/%Y %H:%M"), S["body_sm"]),
            ])
        if qs.count() > LIMITE:
            contenido.append(Paragraph(
                f"Mostrando los primeros {LIMITE} registros de {qs.count()}. "
                "Usa los filtros del listado antes de exportar para acotar el rango.",
                S["italic"],
            ))
            contenido.append(Spacer(1, 6))

        tabla = Table(filas, repeatRows=1, colWidths=[ancho_util * w for w in (0.14, 0.20, 0.14, 0.22, 0.16, 0.14)])
        tabla.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0), _C_PRIMARY),
            ("GRID",           (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#e2e8f0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#f8fafc")]),
            ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",     (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
            ("LEFTPADDING",    (0, 0), (-1, -1), 6),
        ]))
        contenido.append(tabla)
        doc.build(contenido, onFirstPage=_pdf_footer, onLaterPages=_pdf_footer)
        buffer.seek(0)

        resp = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        nombre = ahora.strftime("auditoria_accesos_%Y%m%d_%H%M%S.pdf")
        resp["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return resp

    # ── Columnas de la lista ─────────────────────────────────────────
    @admin.display(description="Evento")
    def tipo_badge(self, obj):
        estilos = {
            "login_ok":      ("#E1F5EE", "#085041", "check_circle"),
            "login_fallido": ("#FCEBEB", "#A32D2D", "cancel"),
            "logout":        ("#F1EFE8", "#5F5E5A", "logout"),
        }
        bg, color, icono = estilos.get(obj.tipo, ("#F1EFE8", "#5F5E5A", "help"))
        return format_html(
            '<span style="background:{};color:{};padding:3px 10px 3px 6px;border-radius:20px;'
            'font-size:12px;font-weight:500;display:inline-flex;align-items:center;gap:3px;">'
            '<span class="material-symbols-outlined" style="font-size:14px;">{}</span>{}</span>',
            bg, color, icono, obj.get_tipo_display()
        )

    @admin.display(description="Usuario")
    def usuario_o_intento(self, obj):
        if obj.usuario_id:
            return obj.usuario.username
        return format_html('<em style="color:#A32D2D;">{}</em>', obj.username_intentado or "—")

    @admin.display(description="Dispositivo")
    def dispositivo(self, obj):
        if not obj.user_agent:
            return "—"
        return f"{obj.navegador} · {obj.sistema_operativo}"

    @admin.display(description="Fecha", ordering="fecha")
    def fecha_relativa(self, obj):
        from django.utils.timesince import timesince
        return format_html(
            '<span title="{}">Hace {}</span>',
            obj.fecha.strftime("%d/%m/%Y %H:%M:%S"), timesince(obj.fecha)
        )


# =========================================================
# REGISTRO DE ACCIONES — Datos + gráficos compartidos (dashboard/exports)
# =========================================================
def _calcular_logs_stats(qs):
    """A partir del queryset ya filtrado por el changelist: estadísticas +
    eventos por día (14 días) + los 10 campos que más se editan. Este último
    es el dato que de verdad sirve para decidir qué mejorar: si un campo
    aparece constantemente en "cambió X", probablemente su formulario/
    validación de origen necesita ajuste (mal defecto, difícil de acertar
    a la primera, etc.)."""
    from datetime import timedelta
    from django.db.models import Count
    from django.db.models.functions import TruncDate
    from django.utils import timezone
    from collections import Counter
    import json

    stats = {
        "total":         qs.count(),
        "creaciones":    qs.filter(action_flag=ADDITION).count(),
        "ediciones":     qs.filter(action_flag=CHANGE).count(),
        "eliminaciones": qs.filter(action_flag=DELETION).count(),
    }

    desde = timezone.now() - timedelta(days=14)
    por_dia = list(
        qs.filter(action_time__gte=desde)
          .annotate(dia=TruncDate("action_time"))
          .values("dia", "action_flag")
          .annotate(total=Count("id"))
          .order_by("dia")
    )

    # change_message es texto (Django serializa el JSON a mano ahí, no es
    # un JSONField) — no se puede agregar en la BD, se cuenta en Python
    # sobre el queryset ya filtrado por el changelist.
    contador = Counter()
    for msg in qs.filter(action_flag=CHANGE).values_list("change_message", flat=True):
        if not msg or not msg.startswith("["):
            continue
        try:
            partes = json.loads(msg)
        except (ValueError, TypeError):
            continue
        for parte in partes:
            campos = (parte.get("changed") or {}).get("fields")
            if campos:
                contador.update(campos)
    campos_top = [{"campo": c, "total": n} for c, n in contador.most_common(10)]

    return stats, por_dia, campos_top


# Mismo criterio que _AUD_COLOR (auditoría de accesos): verde/azul/rojo son
# semántica de estado (creó/editó/eliminó, igual que accion_badge más abajo),
# no una paleta categórica arbitraria — y el rojo/azul de modo claro no
# llegan a 3:1 sobre una tarjeta oscura, así que el modo oscuro usa
# variantes más claras de la misma familia (medido con el validador de la
# skill dataviz: azul 3.03→4.08, rojo 2.46→3.98; el verde no necesitó ajuste).
_LOG_COLOR = {
    "light": {ADDITION: "#1D9E75", CHANGE: "#1565C0", DELETION: "#A32D2D",
              "bg": "#ffffff", "grid": "#EEF0EC", "text": "#5F5E5A", "line": "#ffffff",
              "hover_bg": "#ffffff", "hover_text": "#1a1a18", "hover_border": "#D3D1C7"},
    "dark":  {ADDITION: "#1D9E75", CHANGE: "#2E7BD6", DELETION: "#D64545",
              "bg": "#1a1a19", "grid": "rgba(255,255,255,0.08)", "text": "#A0A09A", "line": "#1a1a19",
              "hover_bg": "#1e1e1c", "hover_text": "#e5e5e0", "hover_border": "#333330"},
}


def _figura_acciones_por_dia(filas):
    """filas: [{'dia': date, 'action_flag': int, 'total': int}, ...] ->
    {"light": <figura Plotly>, "dark": <figura Plotly>}."""
    import plotly.graph_objects as go
    from collections import defaultdict

    dias = sorted({str(f["dia"]) for f in filas})
    por_tipo = defaultdict(lambda: {d: 0 for d in dias})
    for f in filas:
        por_tipo[f["action_flag"]][str(f["dia"])] = f["total"]

    nombres = {ADDITION: "Creaciones", CHANGE: "Ediciones", DELETION: "Eliminaciones"}
    etiquetas_x = [_fecha_corta_es(d) for d in dias]

    figuras = {}
    for modo, C in _LOG_COLOR.items():
        fig = go.Figure()
        for tipo in (ADDITION, CHANGE, DELETION):
            valores = [por_tipo[tipo][d] for d in dias]
            fig.add_trace(go.Bar(
                name=nombres[tipo], x=etiquetas_x, y=valores,
                marker=dict(
                    color=C[tipo],
                    line=dict(color=C["line"], width=2),
                    cornerradius=4 if tipo == DELETION else 0,
                ),
                hovertemplate=f"<b>{nombres[tipo]}</b>: %{{y}}<extra></extra>",
            ))
        fig.update_layout(
            autosize=True,
            barmode="stack", bargap=0.35, height=300, margin=dict(t=30, b=10, l=36, r=10),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Outfit, sans-serif", size=11, color=C["text"]),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5,
                font=dict(color=C["text"]),
            ),
            xaxis=dict(showgrid=False, zeroline=False, linecolor=C["grid"], tickfont=dict(color=C["text"])),
            yaxis=dict(showgrid=True, gridcolor=C["grid"], zeroline=False, tickfont=dict(color=C["text"])),
            hoverlabel=dict(bgcolor=C["hover_bg"], font=dict(color=C["hover_text"]), bordercolor=C["hover_border"]),
            hovermode="x unified",
        )
        figuras[modo] = fig.to_dict()
    return figuras


def _figura_campos_modificados(filas):
    """filas: [{'campo': str, 'total': int}, ...] ->
    {"light": <figura Plotly>, "dark": <figura Plotly>}."""
    import plotly.graph_objects as go

    if not filas:
        vacio = {"data": [], "layout": {"height": 220}}
        return {"light": vacio, "dark": vacio}

    nombres = [f["campo"] for f in filas]
    valores = [f["total"] for f in filas]

    figuras = {}
    for modo, C in _LOG_COLOR.items():
        fig = go.Figure(go.Bar(
            x=valores, y=nombres, orientation="h",
            marker=dict(color=C[CHANGE], cornerradius=4),
            text=valores, texttemplate="%{x}", textposition="outside",
            textfont=dict(color=C["text"], size=11),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b>: %{x} cambio(s)<extra></extra>",
        ))
        fig.update_layout(
            autosize=True,
            bargap=0.35,
            height=max(220, len(nombres) * 32 + 60),
            margin=dict(t=10, b=30, l=170, r=30),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Outfit, sans-serif", size=11, color=C["text"]),
            yaxis=dict(autorange="reversed", showgrid=False, tickfont=dict(color=C["text"])),
            xaxis=dict(dtick=1, showgrid=True, gridcolor=C["grid"], zeroline=False, tickfont=dict(color=C["text"])),
            hoverlabel=dict(bgcolor=C["hover_bg"], font=dict(color=C["hover_text"]), bordercolor=C["hover_border"]),
        )
        figuras[modo] = fig.to_dict()
    return figuras


# =========================================================
# AUDITORÍA — Registro de Acciones del Admin (LogEntry nativo)
# =========================================================
@admin.register(LogEntry)
class LogEntryAdmin(AccionesColumnaMixin, ModelAdmin):
    """
    Django genera un LogEntry cada vez que alguien crea, edita o borra algo
    desde el admin — pero no lo registraba en el admin por defecto, así que
    ese historial existía pero nadie podía verlo. El enlace del sidebar
    (config/settings.py, sección UNFOLD > Auditoría > "Registro de
    Acciones") ya apunta aquí (admin:admin_logentry_changelist).

    Además de lo que el admin llena solo, las acciones hechas desde las
    vistas propias de la app (fuera de /admin/ — subir muestra, reclasificar
    catálogo, generar reporte, ensayos de bioquímica…) también caen aquí:
    ver registrar_accion() en analisis/audit.py y sus llamadas en cada vista.

    Igual que EventoAcceso, es de solo lectura.
    """
    list_display  = ("accion_badge", "user", "content_type", "object_repr", "detalle_legible", "action_time_corta", "acciones")
    list_filter   = ("action_flag", "user", "content_type", "action_time")
    search_fields = ("object_repr", "change_message", "user__username")
    date_hierarchy = "action_time"
    ordering       = ("-action_time",)
    list_per_page  = 30
    list_fullwidth = True

    # Inyecta tarjetas de estadísticas + gráficos antes de la tabla, mismo
    # gancho que usa EventoAcceso (ver changelist_view/get_urls debajo).
    list_before_template = "admin/admin/logentry/dashboard_stats.html"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Fecha", ordering="action_time")
    def action_time_corta(self, obj):
        return obj.action_time.strftime("%d/%m/%Y %H:%M")

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Acción")
    def accion_badge(self, obj):
        # action_flag: 1=alta, 2=cambio, 3=baja
        mapa = {
            1: ("Creó", "#E1F5EE", "#085041"),
            2: ("Editó", "#E6F1FB", "#0C447C"),
            3: ("Eliminó", "#FCEBEB", "#A32D2D"),
        }
        texto, bg, color = mapa.get(obj.action_flag, ("—", "#F1EFE8", "#5F5E5A"))
        return format_html(
            '<span style="background:{};color:{};padding:3px 10px;border-radius:20px;font-size:12px;font-weight:500;">{}</span>',
            bg, color, texto
        )

    @admin.display(description="Detalle")
    def detalle_legible(self, obj):
        # change_message crudo es el JSON que arma Django internamente
        # (p.ej. [{"changed": {"fields": ["Altitud (msnm)"]}}]) — nunca
        # pensado para mostrarse tal cual. get_change_message() lo traduce
        # a texto legible ("Modificado Altitud (msnm)."), ya en español
        # porque LANGUAGE_CODE='es' usa las traducciones que Django trae
        # incluidas; si no es JSON (los mensajes propios de registrar_accion
        # en audit.py, que ya son texto plano) lo devuelve tal cual.
        try:
            return obj.get_change_message() or "—"
        except Exception:
            return obj.change_message or "—"

    # ── URLs propias: exportación ──────────────────────────────────────
    def get_urls(self):
        urls = super().get_urls()
        propias = [
            path("exportar/excel/", self.admin_site.admin_view(self.exportar_excel),
                 name="admin_logentry_exportar_excel"),
            path("exportar/pdf/", self.admin_site.admin_view(self.exportar_pdf),
                 name="admin_logentry_exportar_pdf"),
        ]
        return propias + urls

    # ── Dashboard: estadísticas + datos de gráficos ─────────────────────
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        try:
            qs = response.context_data["cl"].queryset
        except (AttributeError, KeyError, TypeError):
            return response

        import json

        stats, por_dia, campos_top = _calcular_logs_stats(qs)
        response.context_data["logs_stats"] = stats
        response.context_data["grafico_dias_json"] = json.dumps(
            _figura_acciones_por_dia(por_dia), default=str
        )
        response.context_data["grafico_campos_json"] = json.dumps(
            _figura_campos_modificados(campos_top), default=str
        )
        return response

    # ── Exportación ──────────────────────────────────────────────────
    _KPI_ESTILO = (
        # clave,           etiqueta,          bg claro,  texto oscuro
        ("total",          "Total de acciones",   "EEE8F5", "4A3369"),
        ("creaciones",     "Creaciones",           "E1F5EE", "085041"),
        ("ediciones",      "Ediciones",            "E3F2FD", "0D3E8C"),
        ("eliminaciones",  "Eliminaciones",        "FCEBEB", "6b1212"),
    )
    _ACCION_BADGE_XLSX = {
        ADDITION: ("Creó", "E1F5EE", "085041"),
        CHANGE:   ("Editó", "E6F1FB", "0C447C"),
        DELETION: ("Eliminó", "FCEBEB", "A32D2D"),
    }

    def exportar_excel(self, request):
        from django.http import HttpResponse
        from django.utils import timezone
        from typing import cast
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.worksheet import Worksheet
        from openpyxl.worksheet.table import Table as XLTable, TableStyleInfo
        from openpyxl.chart import BarChart, Reference
        from openpyxl.chart.series import DataPoint

        cl = self.get_changelist_instance(request)
        qs = cl.queryset
        stats, por_dia, campos_top = _calcular_logs_stats(qs)
        ahora = timezone.now()

        CV_OSC, CV = "0F6E56", "1D9E75"
        _side = Side(style="thin", color="D9D9D9")
        BORDE = Border(left=_side, right=_side, top=_side, bottom=_side)
        al_c  = Alignment(horizontal="center", vertical="center", wrap_text=True)
        al_l  = Alignment(horizontal="left", vertical="center", wrap_text=True)

        wb = Workbook()

        # ── Hoja 1: Resumen ──────────────────────────────────────────
        # Workbook.active está tipado Worksheet | None en los stubs de
        # openpyxl (una hoja de cálculo podría técnicamente no tener
        # ninguna) pero un Workbook() recién creado siempre trae una hoja
        # activa por defecto — el cast no cambia nada en runtime.
        ws = cast(Worksheet, wb.active)
        ws.title = "Resumen"
        ws.sheet_view.showGridLines = False

        ws.merge_cells("A1:H1")
        c = ws["A1"]; c.value = "BioMicro — Registro de Acciones"
        c.font = Font(bold=True, size=16, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=CV_OSC)
        c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.row_dimensions[1].height = 32

        ws.merge_cells("A2:H2")
        c = ws["A2"]
        filtro_txt = " (con filtros aplicados)" if request.GET else " (todas las acciones)"
        c.value = f"Generado el {ahora:%d/%m/%Y %H:%M} — {stats['total']} registro(s){filtro_txt}"
        c.font = Font(italic=True, size=10, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=CV)
        c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.row_dimensions[2].height = 20

        fila_kpi_val, fila_kpi_lbl = 4, 5
        for i, (clave, etiqueta, bg, fg) in enumerate(self._KPI_ESTILO):
            col_ini = get_column_letter(i * 2 + 1)
            col_fin = get_column_letter(i * 2 + 2)
            for fila, val, tam, negrita in (
                (fila_kpi_val, stats[clave], 22, True),
                (fila_kpi_lbl, etiqueta.upper(), 8.5, False),
            ):
                ws.merge_cells(f"{col_ini}{fila}:{col_fin}{fila}")
                cc = ws[f"{col_ini}{fila}"]
                cc.value = val
                cc.font = Font(bold=negrita, size=tam, color=fg)
                cc.fill = PatternFill("solid", fgColor=bg)
                cc.alignment = al_c
            ws.row_dimensions[fila_kpi_val].height = 34
            ws.row_dimensions[fila_kpi_lbl].height = 16

        for col in "ABCDEFGH":
            ws.column_dimensions[col].width = 13

        # ── Serie: acciones por día (últimos 14 días) + gráfico nativo ──
        fila = 8
        ws.cell(row=fila, column=1, value="Acciones por día (últimos 14 días)").font = Font(bold=True, size=12, color=CV_OSC)
        fila += 1
        cab_dia = fila
        for j, txt in enumerate(("Día", "Creaciones", "Ediciones", "Eliminaciones"), start=1):
            cc = ws.cell(row=cab_dia, column=j, value=txt)
            cc.font = Font(bold=True, color="FFFFFF")
            cc.fill = PatternFill("solid", fgColor=CV_OSC)
            cc.alignment = al_c
            cc.border = BORDE

        dias = sorted({str(f["dia"]) for f in por_dia})
        from collections import defaultdict
        por_tipo = defaultdict(lambda: {d: 0 for d in dias})
        for f in por_dia:
            por_tipo[f["action_flag"]][str(f["dia"])] = f["total"]
        for i, d in enumerate(dias):
            r = cab_dia + 1 + i
            valores = [d, por_tipo[ADDITION][d], por_tipo[CHANGE][d], por_tipo[DELETION][d]]
            for j, v in enumerate(valores, start=1):
                cc = ws.cell(row=r, column=j, value=v)
                cc.border = BORDE
                cc.alignment = al_c if j > 1 else al_l
        fila_fin_dia = cab_dia + len(dias)

        if dias:
            ch = BarChart()
            ch.type, ch.grouping, ch.overlap = "col", "stacked", 100
            ch.title, ch.style = "Acciones por día", 10
            ch.width, ch.height = 22, 9
            ch.y_axis.title = "Acciones"
            for j, color in ((2, "085041"), (3, "0C447C"), (4, "A32D2D")):
                dat = Reference(ws, min_col=j, max_col=j, min_row=cab_dia, max_row=fila_fin_dia)
                ch.add_data(dat, titles_from_data=True)
                ch.series[-1].graphicalProperties.solidFill = color
            cat = Reference(ws, min_col=1, min_row=cab_dia + 1, max_row=fila_fin_dia)
            ch.set_categories(cat)
            ws.add_chart(ch, f"A{fila_fin_dia + 3}")
        else:
            ws.cell(row=cab_dia + 1, column=1, value="Sin acciones en los últimos 14 días.").font = Font(italic=True, color="888888")
            fila_fin_dia = cab_dia + 1

        # ── Serie: campos más modificados + gráfico nativo ──────────────
        fila_top = max(fila_fin_dia + 22, cab_dia + 2)
        ws.cell(row=fila_top, column=1, value="Campos más modificados (top 10)").font = Font(bold=True, size=12, color=CV_OSC)
        fila_top += 1
        cab_top = fila_top
        for j, txt in enumerate(("Campo", "Veces modificado"), start=1):
            cc = ws.cell(row=cab_top, column=j, value=txt)
            cc.font = Font(bold=True, color="FFFFFF")
            cc.fill = PatternFill("solid", fgColor="0C447C")
            cc.alignment = al_c
            cc.border = BORDE

        for i, f in enumerate(campos_top):
            r = cab_top + 1 + i
            ws.cell(row=r, column=1, value=f["campo"]).border = BORDE
            ws.cell(row=r, column=1).alignment = al_l
            ws.cell(row=r, column=2, value=f["total"]).border = BORDE
            ws.cell(row=r, column=2).alignment = al_c
        fila_fin_top = cab_top + len(campos_top)

        if campos_top:
            ch2 = BarChart()
            ch2.type, ch2.grouping = "bar", "clustered"
            ch2.title, ch2.style, ch2.legend = "Campos más modificados", 10, None
            ch2.width, ch2.height = 22, max(7, len(campos_top) * 0.8)
            dat = Reference(ws, min_col=2, min_row=cab_top, max_row=fila_fin_top)
            ch2.add_data(dat, titles_from_data=True)
            cat = Reference(ws, min_col=1, min_row=cab_top + 1, max_row=fila_fin_top)
            ch2.set_categories(cat)
            for i in range(len(campos_top)):
                dp = DataPoint(idx=i)
                dp.graphicalProperties.solidFill = "0C447C"
                ch2.series[0].dPt.append(dp)
            ws.add_chart(ch2, f"A{fila_fin_top + 3}")
        else:
            ws.cell(row=cab_top + 1, column=1, value="Sin ediciones registradas.").font = Font(italic=True, color="888888")

        # ── Hoja 2: detalle completo de acciones ─────────────────────────
        ws2 = wb.create_sheet("Registro de Acciones")
        columnas = ["Acción", "Usuario", "Modelo", "Objeto", "Detalle", "Fecha"]
        for j, txt in enumerate(columnas, start=1):
            cc = ws2.cell(row=1, column=j, value=txt)
            cc.font = Font(bold=True, color="FFFFFF")
            cc.fill = PatternFill("solid", fgColor=CV_OSC)
            cc.alignment = al_c
            cc.border = BORDE

        qs_detalle = qs.select_related("user", "content_type")
        for i, e in enumerate(qs_detalle):
            r = i + 2
            try:
                detalle = e.get_change_message() or "—"
            except Exception:
                detalle = e.change_message or "—"
            valores = [
                self._ACCION_BADGE_XLSX.get(e.action_flag, ("—", "", ""))[0],
                e.user.username if e.user_id else "—",
                str(e.content_type) if e.content_type_id else "—",
                e.object_repr,
                detalle,
                e.action_time.strftime("%Y-%m-%d %H:%M:%S"),
            ]
            for j, v in enumerate(valores, start=1):
                cc = ws2.cell(row=r, column=j, value=v)
                cc.border = BORDE
                cc.alignment = al_l
            bg, fg = self._ACCION_BADGE_XLSX.get(e.action_flag, ("—", "F1EFE8", "5F5E5A"))[1:]
            cc_accion = ws2.cell(row=r, column=1)
            cc_accion.fill = PatternFill("solid", fgColor=bg)
            cc_accion.font = Font(bold=True, color=fg)

        n = qs.count()
        if n:
            ref = f"A1:{get_column_letter(len(columnas))}{n + 1}"
            tabla = XLTable(displayName="TablaRegistroAcciones", ref=ref)
            tabla.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium7", showFirstColumn=False, showLastColumn=False,
                showRowStripes=True, showColumnStripes=False,
            )
            ws2.add_table(tabla)
        ws2.freeze_panes = "A2"
        anchos = {"A": 14, "B": 16, "C": 22, "D": 26, "E": 40, "F": 20}
        for col, w in anchos.items():
            ws2.column_dimensions[col].width = w

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        resp = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        nombre = ahora.strftime("registro_acciones_%Y%m%d_%H%M%S.xlsx")
        resp["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return resp

    def exportar_pdf(self, request):
        from django.http import HttpResponse
        from django.utils import timezone
        from xml.sax.saxutils import escape as _xml_escape
        from reportlab.lib import colors as rl_colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from analisis.services.business.export_service import (
            _get_styles, _pdf_footer, _seccion_hdr, _kpi_tiles, _C_PRIMARY, _C_SECONDARY,
        )

        cl = self.get_changelist_instance(request)
        qs = cl.queryset
        stats, _por_dia, _campos = _calcular_logs_stats(qs)
        ahora = timezone.now()
        S = _get_styles()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=landscape(A4),
            topMargin=30, bottomMargin=40, leftMargin=30, rightMargin=30,
        )
        ancho_util = landscape(A4)[0] - 60
        contenido = []

        t_banner = Table(
            [[Paragraph("<b>BioMicro — Registro de Acciones</b>", S["titulo"])],
             [Paragraph("Bitácora de altas, ediciones y bajas hechas desde el sistema", S["subtitle"])]],
            colWidths=[ancho_util],
        )
        t_banner.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), _C_PRIMARY),
            ("TOPPADDING",    (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (0, 0), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 16),
        ]))
        contenido.append(t_banner)

        filtro_txt = "con filtros aplicados" if request.GET else "todas las acciones registradas"
        t_meta = Table(
            [[Paragraph(f"  Generado: {ahora:%d/%m/%Y %H:%M} · {stats['total']} registro(s) · {filtro_txt}", S["body_sm"])]],
            colWidths=[ancho_util],
        )
        t_meta.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), _C_SECONDARY),
            ("TEXTCOLOR",     (0, 0), (-1, -1), rl_colors.white),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        contenido.append(t_meta)
        contenido.append(Spacer(1, 14))

        contenido.append(_kpi_tiles([
            {"val": stats["total"],         "lbl": "TOTAL DE ACCIONES"},
            {"val": stats["creaciones"],    "lbl": "CREACIONES"},
            {"val": stats["ediciones"],     "lbl": "EDICIONES"},
            {"val": stats["eliminaciones"], "lbl": "ELIMINACIONES"},
        ], ancho_util, S))
        contenido.append(Spacer(1, 14))

        contenido.append(_seccion_hdr("Detalle de acciones", ancho_util, S))
        contenido.append(Spacer(1, 6))

        LIMITE = 3000  # límite razonable: un PDF con más filas deja de ser legible
        ACCION_COLOR = {ADDITION: "#085041", CHANGE: "#0C447C", DELETION: "#A32D2D"}
        ACCION_TXT   = {ADDITION: "Creó", CHANGE: "Editó", DELETION: "Eliminó"}
        cabecera = ["Acción", "Usuario", "Modelo", "Objeto", "Detalle", "Fecha"]
        filas = [[Paragraph(t, S["th_dark"]) for t in cabecera]]
        qs_detalle = qs.select_related("user", "content_type")[:LIMITE]
        for e in qs_detalle:
            try:
                detalle = e.get_change_message() or "—"
            except Exception:
                detalle = e.change_message or "—"
            color = ACCION_COLOR.get(e.action_flag, "#5F5E5A")
            texto_accion = ACCION_TXT.get(e.action_flag, "—")
            filas.append([
                Paragraph(f'<font color="{color}"><b>{texto_accion}</b></font>', S["body_sm"]),
                Paragraph(_xml_escape(e.user.username) if e.user_id else "—", S["body_sm"]),
                Paragraph(_xml_escape(str(e.content_type)) if e.content_type_id else "—", S["body_sm"]),
                # object_repr y el detalle (get_change_message) pueden llevar
                # texto libre que alguien escribió en un formulario (p. ej. el
                # nombre de un Cultivo) — se escapan antes de Paragraph() para
                # que no se interprete como markup de reportlab (mismo motivo
                # que username_intentado en EventoAccesoAdmin.exportar_pdf).
                Paragraph(_xml_escape(e.object_repr or "—"), S["body_sm"]),
                Paragraph(_xml_escape(detalle), S["body_sm"]),
                Paragraph(e.action_time.strftime("%d/%m/%Y %H:%M"), S["body_sm"]),
            ])
        if qs.count() > LIMITE:
            contenido.append(Paragraph(
                f"Mostrando los primeros {LIMITE} registros de {qs.count()}. "
                "Usa los filtros del listado antes de exportar para acotar el rango.",
                S["italic"],
            ))
            contenido.append(Spacer(1, 6))

        tabla = Table(filas, repeatRows=1, colWidths=[ancho_util * w for w in (0.09, 0.13, 0.15, 0.17, 0.32, 0.14)])
        tabla.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0), _C_PRIMARY),
            ("GRID",           (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#e2e8f0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#f8fafc")]),
            ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",     (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
            ("LEFTPADDING",    (0, 0), (-1, -1), 6),
        ]))
        contenido.append(tabla)
        doc.build(contenido, onFirstPage=_pdf_footer, onLaterPages=_pdf_footer)
        buffer.seek(0)

        resp = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        nombre = ahora.strftime("registro_acciones_%Y%m%d_%H%M%S.pdf")
        resp["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return resp
