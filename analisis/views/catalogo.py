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
    """README: Catálogo con clasificación funcional ✅ ⚠️ ⚪"""
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
        "microorganismos":    microorganismos,
        "estadisticas":       estadisticas,
        "filtro_marcador":    tipo_marcador,
        "filtro_clasificacion": clasificacion,
        "filtro_nivel":       nivel,
        "busqueda":           busqueda,
        "marcadores_disponibles": ["16S", "ITS"],
        "clasificaciones_disponibles": [
            ("benefico",      "✅ Benéfico"),
            ("fitopatogeno",  "⚠️ Potencialmente Fitopatógeno"),
            ("neutral",       "Neutral"),
            ("sin_clasificar","⚪ Sin Clasificación"),
        ],
        "niveles_taxonomicos": ["Kingdom","Phylum","Class","Order","Family","Genus","Species"],
    })


@login_required
def detalle_microorganismo(request, pk):
    microorganismo = obtener_detalle_microorganismo(pk)
    if microorganismo is None:
        messages.error(request, "Microorganismo no encontrado en el catálogo.")
        return redirect("analisis:catalogo")

    return render(request, "analisis/catalogo_microorganismos.html", {
        "microorganismo": microorganismo,
    })


@login_required
@require_POST
def actualizar_clasificacion(request, pk):
    """README: Rol Analista Especialista — edita clasificación según literatura."""
    if not request.user.is_staff:
        return JsonResponse({"ok": False, "error": "Sin permisos."}, status=403)

    nueva_clasificacion = request.POST.get("clasificacion", "").strip()
    justificacion       = request.POST.get("justificacion", "").strip()

    if nueva_clasificacion not in CLASIFICACIONES_VALIDAS:
        return JsonResponse({"ok": False, "error": f"Clasificación inválida."}, status=400)

    resultado = reclasificar_microorganismo(
        pk=pk,
        nueva_clasificacion=nueva_clasificacion,
        usuario=request.user,
        justificacion=justificacion,
    )

    if resultado.get("ok"):
        return JsonResponse({"ok": True, "mensaje": "Clasificación actualizada."})
    return JsonResponse({"ok": False, "error": resultado.get("error")}, status=500)