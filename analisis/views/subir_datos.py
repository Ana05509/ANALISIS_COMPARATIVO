import os
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse

# IMPORTACIONES CORREGIDAS SEGÚN TU ESTRUCTURA DE CARPETAS
from analisis.services.business.upload_service import procesar_upload
from analisis.forms import SubirDatosForm
from analisis.models import MuestraSuelo, VariedadClon

MARCADORES_VALIDOS = ("16S", "ITS")


@login_required
def subir_datos(request):
    """
    Vista para cargar archivos de resultados moleculares (16S / ITS).
    README: "Ingesta de Datos", "Validación Automática", "Curación de Datos"
    Rol "Analista Especialista": único rol que ejecuta el pipeline de carga.
    """
    if request.method == "POST":
        form = SubirDatosForm(request.POST, request.FILES)

        if not form.is_valid():
            return render(request, "analisis/subir_datos.html", {
                "form":                   form,
                "marcadores_disponibles": MARCADORES_VALIDOS,
            })

        try:
            resultado = procesar_upload(request)
            messages.success(
                request,
                f"Archivo procesado correctamente. "
                f"{resultado.get('total_registros', 0)} registros importados."
            )
            return redirect("analisis:dashboard")

        except ValueError as e:
            messages.error(request, f"Error de validación: {str(e)}")
        except Exception as e:
            messages.error(request, f"Error al procesar el archivo: {str(e)}")

        return render(request, "analisis/subir_datos.html", {
            "form":                   form,
            "marcadores_disponibles": MARCADORES_VALIDOS,
        })

    # GET: formulario vacío
    tipo = request.GET.get("tipo", "16S")
    tipo = tipo if tipo in MARCADORES_VALIDOS else "16S"

    muestras = MuestraSuelo.objects.all().order_by("-id")

    return render(request, "analisis/subir_datos.html", {
        "form":                   SubirDatosForm(initial={"tipo": tipo}),
        "productos":              muestras,
        "tipo_actual":            tipo,
        "marcadores_disponibles": MARCADORES_VALIDOS,
    })