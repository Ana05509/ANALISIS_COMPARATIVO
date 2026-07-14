from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html, mark_safe
from django.db import transaction
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import path
from django.template.response import TemplateResponse
from django import forms
import pandas as pd
import io

# Importaciones de Unfold
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

# Auditoría: agrega la pestaña "Historial" (quién cambió qué y cuándo)
from simple_history.admin import SimpleHistoryAdmin

# Importaciones de tu app
from .models import (
    Cultivo, VariedadClon, MuestraSuelo, ArchivoMolecular,
    ResultadoTaxonomico, CatalogoMicroorganismo, Usuario,
)
from analisis.services.processing.pipeline import PipelineProcesamiento

# Configuración de cabeceras
admin.site.site_header = "BioSuelo"
admin.site.site_title  = "Administración BioSuelo"
admin.site.index_title = "Panel de Control Microbiológico"


# =========================================================
# OPTIMIZACIÓN: MIXIN GLOBAL PARA BOTONES AZULES
# =========================================================
class BotonEditarMixin:
    """
    Agrega automáticamente la columna con el botón azul '✏️ Editar' a cualquier modelo.
    Esto evita repetir código HTML en cada tabla.
    """
    @admin.display(description="Acciones")
    def acciones_columna(self, obj):
        url = f"./{obj.pk}/change/"
        return format_html(
            '<a href="{}" style="background-color: #1D9E75; color: white; padding: 5px 14px; '
            'border-radius: 6px; font-size: 12px; font-weight: 600; text-decoration: none; '
            'display: inline-block; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">✏️ Editar</a>',
            url
        )


# =========================================================
# CULTIVOS
# =========================================================
@admin.register(Cultivo)
class CultivoAdmin(SimpleHistoryAdmin, BotonEditarMixin, ModelAdmin):
    list_display  = ("id", "nombre", "descripcion", "acciones_columna")
    list_display_links = ("id", "nombre")
    search_fields = ("nombre", "descripcion")
    ordering      = ("nombre",)
    list_per_page = 15
    list_fullwidth = True

    fieldsets = (
        ("Información del Cultivo", {
            "description": "Registre el cultivo agrícola principal. El nombre debe ser único.",
            "fields": ("nombre", "descripcion"),
        }),
        ("Imagen representativa", {
            "description": "Elige una opción: sube un archivo desde tu computadora O pega un enlace externo. Si hay archivo subido, tiene prioridad sobre la URL.",
            "fields": ("imagen", "imagen_url"),
        }),
    )

    def save_model(self, request, obj, form, change):
        # Si el admin pegó una URL y no hay archivo subido, descargamos la imagen
        # al servidor para que todos los usuarios la reciban desde aquí mismo.
        if obj.imagen_url and not obj.imagen:
            import urllib.request as _ur
            from django.core.files.base import ContentFile
            from urllib.parse import urlparse
            import os
            try:
                with _ur.urlopen(obj.imagen_url, timeout=10) as resp:
                    content = resp.read()
                raw_name = os.path.basename(urlparse(obj.imagen_url).path)
                filename = raw_name if raw_name else f"cultivo_{obj.nombre}.jpg"
                obj.imagen.save(filename, ContentFile(content), save=False)
                obj.imagen_url = None   # ya no necesitamos la URL externa
                messages.success(request, f"Imagen de '{obj.nombre}' descargada y guardada en el servidor.")
            except Exception as e:
                messages.warning(request, f"No se pudo descargar la imagen desde la URL: {e}. Se guardará sólo el enlace.")

        super().save_model(request, obj, form, change)
        if change:
            messages.info(request, f"Cultivo '{obj.nombre}' actualizado correctamente.")
        else:
            messages.success(request, f"¡Éxito! Cultivo '{obj.nombre}' registrado. Ahora puede crear sus variedades o clones.")


# =========================================================
# VARIEDADES / CLONES
# =========================================================
@admin.register(VariedadClon)
class VariedadClonAdmin(BotonEditarMixin, ModelAdmin):
    list_display  = ("id", "nombre", "cultivo", "acciones_columna")
    list_display_links = ("id", "nombre")
    list_filter   = ("cultivo",)
    search_fields = ("nombre", "cultivo__nombre")
    ordering      = ("cultivo__nombre", "nombre")
    list_per_page = 20
    list_fullwidth = True

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
class MuestraSueloAdmin(SimpleHistoryAdmin, BotonEditarMixin, ModelAdmin):
    form = MuestraSueloForm  # 🌟 Acoplamos el formulario con guías de texto
    
    list_display = ("codigo", "cultivo", "variedad_clon", "localidad", "altitud_display", "tipo_muestra", "fecha_registro", "acciones_columna")
    list_display_links = ("codigo",)
    list_filter   = ("cultivo", "variedad_clon", "tipo_muestra", "fecha_registro")
    search_fields = ("codigo", "cultivo__nombre", "variedad_clon__nombre", "localidad", "finca_lote")
    ordering      = ("-fecha_registro",)
    date_hierarchy = "fecha_registro"
    list_per_page  = 20
    list_fullwidth = True
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
class ArchivoMolecularAdmin(BotonEditarMixin, ModelAdmin):
    list_display = ("id", "tipo_badge", "muestra", "archivo", "total_resultados", "fecha_carga", "acciones_columna")
    list_display_links = ("id",)
    list_filter   = ("tipo_analisis", "fecha_carga")
    search_fields = ("muestra__codigo",)
    ordering      = ("-fecha_carga",)
    date_hierarchy = "fecha_carga"
    list_per_page  = 20
    list_fullwidth = True
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
class ResultadoTaxonomicoAdmin(ModelAdmin):
    list_display  = ("id", "archivo", "genus", "species", "num_hits", "porcentaje_hits")
    list_filter   = ("archivo__tipo_analisis",)
    search_fields = ("genus", "species", "phylum", "archivo__muestra__codigo")
    ordering      = ("-porcentaje_hits",)
    list_per_page  = 30
    list_fullwidth = True

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
class CatalogoMicroorganismoAdmin(SimpleHistoryAdmin, BotonEditarMixin, ModelAdmin):
    change_list_template = "admin/analisis/catalogomicroorganismo/change_list.html"

    list_display  = ("nombre", "nivel", "marcador_badge", "clasificacion_badge", "descripcion_corta", "acciones_columna")
    list_display_links = ("nombre",)
    list_filter   = ("marcador", "clasificacion", "nivel")
    search_fields = ("nombre", "descripcion")
    ordering      = ("nombre",)
    list_per_page  = 20
    list_fullwidth = True

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
        return obj.descripcion[:80] + ("…" if len(obj.descripcion) > 80 else "") if obj.descripcion else "—"


# =========================================================
# FORMULARIOS PARA LA CREACIÓN DE USUARIO
# =========================================================
class CustomUserCreationForm(UserCreationForm):
    """Formulario de creación de usuario en admin: pide email y genera username automáticamente."""
    class Meta:
        model = Usuario
        fields = ("email",)

    def save(self, commit=True):
        user = super().save(commit=False)
        # username = email (mismo criterio que el adapter de allauth)
        user.username = (user.email or "")[:150]
        if commit:
            user.save()
        return user

class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = Usuario
        fields = "__all__"


# =========================================================
# USUARIOS
# =========================================================
@admin.register(Usuario)
class UsuarioAdmin(SimpleHistoryAdmin, BaseUserAdmin, BotonEditarMixin, ModelAdmin):
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display  = ("email", "nombre_completo", "rol_badge", "is_active", "is_staff", "date_joined", "acciones_columna")
    list_display_links = ("email",)
    list_filter   = ("rol", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering      = ("email",)
    list_per_page  = 20
    list_fullwidth = True

    @admin.display(description="Nombre")
    def nombre_completo(self, obj):
        nombre = f"{obj.first_name} {obj.last_name}".strip()
        return nombre if nombre else "—"

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
            "Rol en BioSuelo",
            {"fields": ("rol",), "description": "Asigne el rol para determinar los permisos de visualización."}
        ))
        return fieldsets


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
def dashboard_callback(request, context):
    import shutil
    from django.conf import settings as django_settings
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

    # Notificaciones automáticas
    notifs = []
    if sin_procesar > 0:
        notifs.append({
            "tipo": "warning",
            "icono": "alert-triangle",
            "msg": f"{sin_procesar} archivo(s) molecular(es) pendiente(s) de procesar",
        })

    nuevos = Usuario.objects.filter(
        date_joined__gte=timezone.now() - timedelta(days=7)
    ).count()
    if nuevos > 0:
        notifs.append({
            "tipo": "info",
            "icono": "user-plus",
            "msg": f"{nuevos} usuario(s) registrado(s) en los últimos 7 días",
        })

    if pct >= 85:
        notifs.append({
            "tipo": "error",
            "icono": "server-2",
            "msg": f"Almacenamiento crítico: {pct}% utilizado",
        })
    elif pct >= 70:
        notifs.append({
            "tipo": "warning",
            "icono": "server-2",
            "msg": f"Almacenamiento alto: {pct}% utilizado",
        })

    if not notifs:
        notifs.append({
            "tipo": "success",
            "icono": "circle-check",
            "msg": "Sistema funcionando con normalidad",
        })

    context["notifications"] = notifs
    return context