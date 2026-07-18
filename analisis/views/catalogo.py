# analisis/views/catalogo.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from analisis.models import CatalogoMicroorganismo
from analisis.services.business.catalog_service import CatalogService
from analisis.forms import CatalogoImportarForm

@login_required
def catalogo_microorganismos(request):
    """
    Muestra directamente las entradas de CatalogoMicroorganismo con sus
    clasificaciones guardadas (equivalente a lo que ve el admin).
    """
    from django.db.models import Count

    busqueda             = request.GET.get('busqueda', '').strip()
    filtro_marcador      = request.GET.get('filtro_marcador', '')
    filtro_clasificacion = request.GET.get('filtro_clasificacion', '')
    filtro_nivel         = request.GET.get('filtro_nivel', '')

    qs = CatalogoMicroorganismo.objects.all()

    if busqueda:
        qs = qs.filter(nombre__icontains=busqueda)
    if filtro_marcador:
        qs = qs.filter(marcador=filtro_marcador)
    if filtro_clasificacion:
        qs = qs.filter(clasificacion=filtro_clasificacion)
    if filtro_nivel:
        qs = qs.filter(nivel__iexact=filtro_nivel)

    qs = qs.order_by('nombre')

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
        ("sin_clasificar","Sin Clasificar"),
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
            microorganismo.clasificacion = nueva_clasificacion
            microorganismo.save()
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