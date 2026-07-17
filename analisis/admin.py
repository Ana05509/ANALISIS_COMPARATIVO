from django.contrib import admin
from django.contrib.admin.models import LogEntry
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
admin.site.site_header = "TerraBioLab UTC"
admin.site.site_title  = "Administración TerraBioLab"
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
    resultado = PipelineProcesamiento.procesar_archivo_df(df_raw, nivel="genus")
    
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
            "Rol en TerraBioLab UTC",
            {"fields": ("rol",), "description": "Asigne el rol para determinar los permisos de visualización."}
        ))
        return fieldsets

    def save_model(self, request, obj, form, change):
        # Sincronizar is_staff con el rol de BioSuelo para que el acceso
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
# AUDITORÍA — Gráficos (funciones libres para poder probarlas solas)
# =========================================================
def _figura_eventos_por_dia(filas):
    """filas: [{'dia': date, 'tipo': str, 'total': int}, ...] -> dict de figura Plotly."""
    import plotly.graph_objects as go
    from collections import defaultdict

    dias = sorted({str(f["dia"]) for f in filas})
    por_tipo = defaultdict(lambda: {d: 0 for d in dias})
    for f in filas:
        por_tipo[f["tipo"]][str(f["dia"])] = f["total"]

    nombres = {"login_ok": "Exitosos", "login_fallido": "Fallidos", "logout": "Cierres de sesión"}
    colores = {"login_ok": "#1D9E75", "login_fallido": "#A32D2D", "logout": "#5F5E5A"}

    fig = go.Figure()
    for tipo in ("login_ok", "login_fallido", "logout"):
        fig.add_trace(go.Bar(
            name=nombres[tipo], x=dias, y=[por_tipo[tipo][d] for d in dias],
            marker_color=colores[tipo],
        ))
    fig.update_layout(
        autosize=True,
        barmode="stack", height=300, margin=dict(t=30, b=10, l=40, r=10),
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family="Outfit, sans-serif", size=11),
        # Centrada arriba (no anclada a la derecha): con poco ancho, un
        # legend "right-anchored" empuja el primer ítem fuera del panel
        # por la izquierda en vez de envolver.
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
    )
    return fig.to_dict()


def _figura_fallidos_por_usuario(filas):
    """filas: [{'username_intentado': str, 'total': int}, ...] -> dict de figura Plotly."""
    import plotly.graph_objects as go

    if not filas:
        return {"data": [], "layout": {"height": 220}}
    nombres = [f["username_intentado"] or "(vacío)" for f in filas]
    valores = [f["total"] for f in filas]
    fig = go.Figure(go.Bar(x=valores, y=nombres, orientation="h", marker_color="#A32D2D"))
    fig.update_layout(
        autosize=True,
        height=max(220, len(nombres) * 32 + 60),
        margin=dict(t=10, b=30, l=140, r=10),
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family="Outfit, sans-serif", size=11),
        yaxis=dict(autorange="reversed"),
        xaxis=dict(dtick=1),
    )
    return fig.to_dict()


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
        "neutral": "Neutral", "sin_clasificar": "Sin clasificar",
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
        from datetime import timedelta
        from django.db.models import Count
        from django.db.models.functions import TruncDate
        from django.utils import timezone

        response.context_data["auditoria_stats"] = {
            "total":             qs.count(),
            "exitosos":          qs.filter(tipo="login_ok").count(),
            "fallidos":          qs.filter(tipo="login_fallido").count(),
            "usuarios_activos":  qs.filter(tipo="login_ok").exclude(usuario__isnull=True)
                                    .values("usuario").distinct().count(),
        }

        # Gráfico 1: eventos por día (últimos 14 días del conjunto ya filtrado)
        desde = timezone.now() - timedelta(days=14)
        por_dia = list(
            qs.filter(fecha__gte=desde)
              .annotate(dia=TruncDate("fecha"))
              .values("dia", "tipo")
              .annotate(total=Count("id"))
              .order_by("dia")
        )
        response.context_data["grafico_eventos_json"] = json.dumps(
            _figura_eventos_por_dia(por_dia), default=str
        )

        # Gráfico 2: intentos fallidos por usuario/correo intentado (top 10)
        fallidos_por_usuario = list(
            qs.filter(tipo="login_fallido")
              .values("username_intentado")
              .annotate(total=Count("id"))
              .order_by("-total")[:10]
        )
        response.context_data["grafico_fallidos_json"] = json.dumps(
            _figura_fallidos_por_usuario(fallidos_por_usuario), default=str
        )
        return response

    # ── Exportación ──────────────────────────────────────────────────
    def exportar_excel(self, request):
        from django.http import HttpResponse
        from django.utils import timezone

        qs = self.get_changelist_instance(request).queryset
        filas = [{
            "Tipo":       e.get_tipo_display(),
            "Usuario":    e.usuario.username if e.usuario_id else "",
            "Intento":    e.username_intentado,
            "IP":         e.ip_address or "",
            "Navegador":  e.navegador,
            "Sistema operativo": e.sistema_operativo,
            "Fecha":      e.fecha.strftime("%Y-%m-%d %H:%M:%S"),
        } for e in qs]
        df = pd.DataFrame(filas, columns=[
            "Tipo", "Usuario", "Intento", "IP", "Navegador", "Sistema operativo", "Fecha",
        ])

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Eventos de Acceso")
        buffer.seek(0)

        resp = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        nombre = timezone.now().strftime("eventos_acceso_%Y%m%d_%H%M%S.xlsx")
        resp["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return resp

    def exportar_pdf(self, request):
        from django.http import HttpResponse
        from django.utils import timezone
        from reportlab.lib import colors as rl_colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

        qs = self.get_changelist_instance(request).queryset
        styles = getSampleStyleSheet()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=landscape(A4),
            topMargin=30, bottomMargin=30, leftMargin=30, rightMargin=30,
        )
        contenido = [
            Paragraph("BioSuelo — Bitácora de Eventos de Acceso", styles["Title"]),
            Paragraph(
                f"Generado: {timezone.now():%d/%m/%Y %H:%M} — {qs.count()} registro(s)",
                styles["Normal"],
            ),
            Spacer(1, 14),
        ]

        LIMITE = 3000  # límite razonable: un PDF con más filas deja de ser legible
        filas = [["Tipo", "Usuario", "IP", "Navegador", "S.O.", "Fecha"]]
        for e in qs[:LIMITE]:
            filas.append([
                e.get_tipo_display(),
                e.usuario.username if e.usuario_id else (e.username_intentado or "—"),
                e.ip_address or "—",
                e.navegador,
                e.sistema_operativo,
                e.fecha.strftime("%d/%m/%Y %H:%M"),
            ])
        if qs.count() > LIMITE:
            contenido.append(Paragraph(
                f"Mostrando los primeros {LIMITE} registros de {qs.count()}. "
                "Usa los filtros para acotar el rango antes de exportar el resto.",
                styles["Italic"],
            ))
            contenido.append(Spacer(1, 8))

        tabla = Table(filas, repeatRows=1)
        tabla.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0), rl_colors.HexColor("#1D9E75")),
            ("TEXTCOLOR",      (0, 0), (-1, 0), rl_colors.white),
            ("FONTSIZE",       (0, 0), (-1, -1), 8),
            ("GRID",           (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#D3D1C7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#F7F6F2")]),
            ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",     (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ]))
        contenido.append(tabla)
        doc.build(contenido)
        buffer.seek(0)

        resp = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        nombre = timezone.now().strftime("eventos_acceso_%Y%m%d_%H%M%S.pdf")
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
# AUDITORÍA — Registro de Acciones del Admin (LogEntry nativo)
# =========================================================
@admin.register(LogEntry)
class LogEntryAdmin(AccionesColumnaMixin, ModelAdmin):
    """
    Django genera un LogEntry cada vez que alguien crea, edita o borra algo
    desde el admin — pero no lo registra en el admin por defecto, así que
    ese historial existía pero nadie podía verlo. Igual que EventoAcceso,
    es de solo lectura.
    """
    list_display  = ("accion_badge", "user", "content_type", "object_repr", "change_message", "action_time_corta", "acciones")
    list_filter   = ("action_flag", "content_type", "action_time")
    search_fields = ("object_repr", "change_message", "user__username")
    date_hierarchy = "action_time"
    ordering       = ("-action_time",)
    list_per_page  = 30
    list_fullwidth = True

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
