# analisis/views/catalogo.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from analisis.models import ResultadoTaxonomico, CatalogoMicroorganismo
from analisis.services.business.catalog_service import CatalogService

def catalogo_microorganismos(request):
    """
    Vista principal del catálogo con filtros persistentes y 
    matching taxonómico jerárquico.
    """
    # 1. Captura de parámetros desde el formulario HTML
    busqueda = request.GET.get('busqueda', '').strip()
    filtro_marcador = request.GET.get('filtro_marcador', '')
    filtro_clasificacion = request.GET.get('filtro_clasificacion', '')
    filtro_nivel = request.GET.get('filtro_nivel', '')

    # 2. QuerySet Base optimizado
    resultados_qs = ResultadoTaxonomico.objects.select_related('archivo__muestra').all()
    
    # 3. Aplicación de filtros dinámicos independientes
    if busqueda:
        resultados_qs = resultados_qs.filter(genus__icontains=busqueda)
    if filtro_marcador:
        resultados_qs = resultados_qs.filter(archivo__tipo_analisis=filtro_marcador)

    # 4. Consumo del nuevo servicio con Matching Jerárquico pasándole los filtros requeridos
    # Esto elimina el error 'reportArgumentType' de Pylance al coincidir con la firma del Service
    microorganismos, estadisticas = CatalogService.obtener_catalogo_procesado(
        resultados_qs,
        clasificacion=filtro_clasificacion,
        nivel=filtro_nivel
    )

    # 5. Listas estáticas para los selectores del formulario HTML
    marcadores_disponibles = ["16S", "ITS"]
    clasificaciones_disponibles = [
        ("benefico", "Benéfico"),
        ("fitopatogeno", "Fitopatógeno"),
        ("neutral", "Neutral"),
        ("sin_clasificar", "Sin Clasificar")
    ]
    niveles_taxonomicos = ["genus", "species"]

    # 6. Contexto completo para asegurar la persistencia visual en la UI
    context = {
        "microorganismos": microorganismos,
        "estadisticas": estadisticas,
        "busqueda": busqueda,
        "filtro_marcador": filtro_marcador,
        "filtro_clasificacion": filtro_clasificacion,
        "filtro_nivel": filtro_nivel,
        "marcadores_disponibles": marcadores_disponibles,
        "clasificaciones_disponibles": clasificaciones_disponibles,
        "niveles_taxonomicos": niveles_taxonomicos,
    }

    return render(request, "analisis/catalogo_microorganismos.html", context)


# =========================================================================
# FUNCIONES REQUERIDAS POR EL __init__.py (No eliminar para evitar ImportError)
# =========================================================================

def detalle_microorganismo(request, pk):
    """
    Vista para el desglose detallado de un microorganismo específico.
    """
    microorganismo = get_object_or_404(ResultadoTaxonomico, pk=pk)
    context = {
        "microorganismo": microorganismo
    }
    return render(request, "analisis/detalle_producto.html", context)


def actualizar_clasificacion(request, pk):
    """
    Vista para reescribir o corregir manualmente un rol en el catálogo.
    """
    if request.method == "POST":
        nueva_clasificacion = request.POST.get("clasificacion")
        microorganismo = get_object_or_404(CatalogoMicroorganismo, pk=pk)
        
        if nueva_clasificacion in ['benefico', 'fitopatogeno', 'neutral', 'sin_clasificar']:
            microorganismo.clasificacion = nueva_clasificacion
            microorganismo.save()
            messages.success(request, "Clasificación actualizada correctamente.")
            
    return redirect('catalogo_microorganismos')