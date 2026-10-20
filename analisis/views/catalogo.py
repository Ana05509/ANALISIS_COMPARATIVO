# analisis/views/catalogo.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from analisis.models import CatalogoMicroorganismo
from analisis.services.business.catalog_service import CatalogService
from analisis.forms import CatalogoImportarForm
from analisis.audit import registrar_accion
from django.contrib.admin.models import ADDITION, CHANGE

def _filtrar_catalogo(params):
    """
    Aplica los filtros de la página del catálogo (búsqueda, marcador,
    clasificación, nivel). Compartido por el listado y la exportación para
    que el archivo descargado contenga exactamente lo que se ve en pantalla.
    """
    filtros = {
        'busqueda':             params.get('busqueda', '').strip(),
        'filtro_marcador':      params.get('filtro_marcador', ''),
        'filtro_clasificacion': params.get('filtro_clasificacion', ''),
        'filtro_nivel':         params.get('filtro_nivel', ''),
    }
    qs = CatalogoMicroorganismo.objects.all()

    if filtros['busqueda']:
        qs = qs.filter(nombre__icontains=filtros['busqueda'])
    if filtros['filtro_marcador']:
        qs = qs.filter(marcador=filtros['filtro_marcador'])
    if filtros['filtro_clasificacion']:
        qs = qs.filter(clasificacion=filtros['filtro_clasificacion'])
    if filtros['filtro_nivel']:
        qs = qs.filter(nivel__iexact=filtros['filtro_nivel'])

    return qs.order_by('nombre'), filtros


@login_required
def catalogo_microorganismos(request):
    """
    Muestra directamente las entradas de CatalogoMicroorganismo con sus
    clasificaciones guardadas (equivalente a lo que ve el admin).
    """
    from django.db.models import Count

    qs, filtros = _filtrar_catalogo(request.GET)
    busqueda             = filtros['busqueda']
    filtro_marcador      = filtros['filtro_marcador']
    filtro_clasificacion = filtros['filtro_clasificacion']
    filtro_nivel         = filtros['filtro_nivel']

    # Estadísticas sobre el catálogo completo (no sobre el queryset filtrado)
    conteos = {
        row['clasificacion']: row['total']
        for row in CatalogoMicroorganismo.objects.values('clasificacion').annotate(total=Count('id'))
    }
    estadisticas = {
        "total":             CatalogoMicroorganismo.objects.count(),
        "total_beneficos":   conteos.get('benefico', 0),
        "total_fitopatogenos": conteos.get('fitopatogeno', 0),
        "total_neutrales":   conteos.get('neutral', 0),
        "total_sin_clas":    conteos.get('sin_clasificar', 0),
    }

    # Niveles con etiqueta en español — solo los que tienen registros
    niveles_existentes = set(
        CatalogoMicroorganismo.objects.values_list('nivel', flat=True).distinct()
    )
    niveles_taxonomicos = [
        (val, label)
        for val, label in CatalogoMicroorganismo.NIVEL_CHOICES
        if val in niveles_existentes
    ]

    clasificaciones_disponibles = [
        ("benefico",      "Benéfico"),
        ("fitopatogeno",  "Fitopatógeno"),
        ("neutral",       "Neutral"),
        ("sin_clasificar","Sin clasificación"),
    ]

    return render(request, "analisis/catalogo_microorganismos.html", {
        "microorganismos":         qs,
        "estadisticas":            estadisticas,
        "busqueda":                busqueda,
        "filtro_marcador":         filtro_marcador,
        "filtro_clasificacion":    filtro_clasificacion,
        "filtro_nivel":            filtro_nivel,
        "marcadores_disponibles":  ["16S", "ITS"],
        "clasificaciones_disponibles": clasificaciones_disponibles,
        "niveles_taxonomicos":     niveles_taxonomicos,
    })


@login_required
def exportar_catalogo(request, formato):
    """
    Descarga el catálogo (respetando los filtros activos de la página) en
    Excel o CSV. El CSV usa las columnas que acepta «Importar», así que el
    archivo puede volver a importarse.
    """
    from django.http import Http404, HttpResponse
    from django.utils import timezone

    if formato not in ('xlsx', 'csv'):
        raise Http404("Formato no soportado.")

    qs, filtros = _filtrar_catalogo(request.GET)
    filas = qs.values(*CatalogService.COLUMNAS_EXPORTACION)

    if formato == 'xlsx':
        contenido = CatalogService.exportar_excel(filas)
        tipo = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        contenido = CatalogService.exportar_csv(filas)
        tipo = 'text/csv; charset=utf-8'

    sufijo = '_filtrado' if any(filtros.values()) else ''
    nombre = f"catalogo_microorganismos{sufijo}_{timezone.localdate():%Y-%m-%d}.{formato}"
    respuesta = HttpResponse(contenido, content_type=tipo)
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return respuesta


@login_required
def actualizar_clasificacion(request, pk):
    """
    Vista para reescribir o corregir manualmente un rol en el catálogo.
    Solo staff: reclasificar afecta el catálogo compartido que usan todos
    los análisis y reportes del sistema, no solo la muestra que se ve.
    """
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para realizar esta acción.")
        return redirect('analisis:catalogo')

    if request.method == "POST":
        nueva_clasificacion = request.POST.get("clasificacion")
        microorganismo = get_object_or_404(CatalogoMicroorganismo, pk=pk)

        if nueva_clasificacion in ['benefico', 'fitopatogeno', 'neutral', 'sin_clasificar']:
            anterior = microorganismo.get_clasificacion_display()
            microorganismo.clasificacion = nueva_clasificacion
            microorganismo.save()
            registrar_accion(
                request, microorganismo,
                f"Reclasificado de «{anterior}» a «{microorganismo.get_clasificacion_display()}».",
                accion=CHANGE,
            )
            messages.success(request, "Clasificación actualizada correctamente.")

    return redirect('analisis:catalogo')


@login_required
def importar_catalogo(request):
    """
    Procesa la importación masiva de microorganismos desde CSV/Excel.
    Solo disponible para usuarios staff.
    """
    if not request.user.is_staff:
        messages.error(request, "No tiene permisos para realizar esta acción.")
        return redirect('analisis:catalogo')

    if request.method == 'POST':
        form = CatalogoImportarForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                creados, actualizados, errores = CatalogService.importar_desde_archivo(
                    form.cleaned_data['archivo']
                )
                resumen = f"{creados} creados, {actualizados} actualizados"
                if creados or actualizados:
                    # Importación masiva: no hay un único microorganismo al
                    # que atribuirle el registro (LogEntry exige un objeto
                    # puntual), así que se registra un resumen con object_id=0
                    # como ancla — no apunta a una fila real del catálogo,
                    # solo dice "qué modelo" para agruparlo bajo Catálogo de
                    # Microorganismos en el listado de auditoría.
                    from django.contrib.admin.models import LogEntry
                    from django.contrib.contenttypes.models import ContentType
                    LogEntry.objects.create(
                        user_id=request.user.pk,
                        content_type_id=ContentType.objects.get_for_model(CatalogoMicroorganismo).pk,
                        object_id=0,
                        object_repr=f"Importación masiva — {form.cleaned_data['archivo'].name}",
                        action_flag=ADDITION,
                        change_message=f"{resumen}, {errores} fila(s) omitida(s).",
                    )
                if errores:
                    messages.warning(
                        request,
                        f"Importación parcial: {resumen}. {errores} filas omitidas por datos inválidos."
                    )
                else:
                    messages.success(request, f"Importación exitosa: {resumen}.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Error al procesar el archivo: {e}")
        else:
            for field_errors in form.errors.values():
                for error in field_errors:
                    messages.error(request, str(error))

    return redirect('analisis:catalogo')