from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from ..services.business.catalog_service import CatalogService

@login_required
def catalogo_microorganismos(request):
    """Muestra el catálogo con clasificaciones funcionales."""
    tipo_marcador = request.GET.get("marcador", "")
    clasificacion = request.GET.get("clasificacion", "")
    nivel = request.GET.get("nivel", "")
    busqueda = request.GET.get("q", "").strip()

    resultados, estadisticas = CatalogService.obtener_catalogo_procesado(
        marcador=tipo_marcador, clasificacion=clasificacion, busqueda=busqueda
    )

    return render(request, "analisis/catalogo_microorganismos.html", {
        "microorganismos": resultados,
        "estadisticas": estadisticas,
    })

@login_required
def detalle_microorganismo(request, pk):
    """Recupera el perfil funcional completo de un taxón."""
    # Aquí puedes añadir la lógica para buscar el detalle si es necesario
    return render(request, "analisis/detalle_microorganismo.html", {"pk": pk})

@login_required
@require_POST
def actualizar_clasificacion(request, pk):
    """Actualiza la clasificación funcional mediante AJAX."""
    nueva_clas = request.POST.get("clasificacion", "").strip()
    just = request.POST.get("justificacion", "").strip()
    
    if CatalogService.reclasificar_microorganismo(pk, nueva_clas, just):
        return JsonResponse({"ok": True})
    return JsonResponse({"ok": False, "error": "No se pudo actualizar."}, status=400)