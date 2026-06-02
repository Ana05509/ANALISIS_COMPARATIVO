import os
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from analisis.services.business.upload_service import procesar_upload
from analisis.forms import SubirDatosForm
from analisis.models import MuestraSuelo

MARCADORES_VALIDOS = ("16S", "ITS")

@login_required
def subir_datos(request):
    """
    Vista para cargar archivos moleculares raw (16S / ITS).
    SEGURIDAD: Rol 'Técnico' o 'Admin' ejecutan el pipeline. El estudiante es rebotado.
    """
    if request.user.rol in ['estudiante', 'agricultor']:
        messages.error(request, "Su nivel de cuenta no dispone de permisos para inyectar datos al pipeline molecular.")
        return redirect("analisis:dashboard")

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
                f"Archivo procesado correctamente. {resultado.get('total_registros', 0)} registros importados al sistema."
            )
            return redirect("analisis:dashboard")

        except ValueError as e:
            messages.error(request, f"Error de validación en la estructura de la data: {str(e)}")
        except Exception as e:
            messages.error(request, f"Error al procesar el archivo secuencial: {str(e)}")

        return render(request, "analisis/subir_datos.html", {
            "form":                   form,
            "marcadores_disponibles": MARCADORES_VALIDOS,
        })

    muestras = MuestraSuelo.objects.all().order_by("-id")

    return render(request, "analisis/subir_datos.html", {
        "form":                   SubirDatosForm(),
        "marcadores_disponibles": MARCADORES_VALIDOS,
        "muestras":               muestras,
    })