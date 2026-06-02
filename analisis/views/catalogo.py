from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from ..services.business.catalog_service import (
    obtener_catalogo_microorganismos,
    buscar_microorganismos,
    obtener_detalle_microorganismo,
    obtener_estadisticas_catalogo,
)
from ..services.interpretation.microorganism_classifier import reclasificar_microorganismo

CLASIFICACIONES_VALIDAS = {"benefico", "fitopatogeno", "neutral", "sin_clasificar"}

@login_required
def catalogo_microorganismos(request):
    """Muestra el catálogo con clasificaciones funcionales de microorganismos."""
    tipo_marcador  = request.GET.get("marcador", "")
    clasificacion  = request.GET.get("clasificacion", "")
    nivel          = request.GET.get("nivel", "")
    busqueda       = request.GET.get("q", "").strip()

    if busqueda:
        microorganismos = buscar_microorganismos(
            termino=busqueda, marcador=tipo_marcador, clasificacion=clasificacion,
        )
    else:
        microorganismos = obtener_catalogo_microorganismos(
            marcador=tipo_marcador, clasificacion=clasificacion, nivel=nivel,
        )

    estadisticas = obtener_estadisticas_catalogo()

    return render(request, "analisis/catalogo_microorganismos.html", {
        "microorganismos":       microorganismos,
        "total_beneficos":       estadisticas.get("benefico", 0),
        "total_fitopatogenos":   estadisticas.get("fitopatogeno", 0),
        "total_neutrales":       estadisticas.get("neutral", 0),
        "total_sin_clasificar":  estadisticas.get("sin_clasificar", 0),
        "filtros": {
            "marcador":       tipo_marcador,
            "clasificacion":  clasificacion,
            "nivel":          nivel,
            "q":              busqueda,
        },
        "marcadores_disponibles": ["16S", "ITS"],
        "roles_permitidos_edicion": request.user.rol in ['admin', 'tecnico'],
    })

@login_required
def detalle_microorganismo(request, pk):
    microorganismo = obtener_detalle_microorganismo(pk)
    if microorganismo is None:
        messages.error(request, "Microorganismo no localizado en la base del catálogo.")
        return redirect("analisis:catalogo")

    return render(request, "analisis/catalogo_microorganismos.html", {
        "microorganismo": microorganismo,
    })

@login_required
@require_POST
def actualizar_clasificacion(request, pk):
    """SEGURIDAD: Solo Administradores o Técnicos modifican la taxonomía funcional."""
    if request.user.rol not in ['admin', 'tecnico']:
        return JsonResponse({"ok": False, "error": "Su nivel de usuario no dispone de credenciales de modificación."}, status=403)

    nueva_clasificacion = request.POST.get("clasificacion", "").strip()
    justificacion       = request.POST.get("justificacion", "").strip()

    if nueva_clasificacion not in CLASIFICACIONES_VALIDAS:
        return JsonResponse({"ok": False, "error": "Clasificación inválida."}, status=400)

    resultado = reclasificar_microorganismo(
        pk=pk,
        nueva_clasificacion=nueva_clasificacion,
        usuario=request.user,
        justificacion=justificacion,
    )
    return JsonResponse({"ok": True, "resultado": resultado})