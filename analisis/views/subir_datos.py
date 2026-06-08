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

        # 1. SI EL FORMULARIO FALLA: Extraemos y mostramos por qué falló
        if not form.is_valid():
            for field, errors in form.errors.items():
                for error in errors:
                    # Esto disparará una alerta roja/amarilla en tu HTML para que no sea un fallo silencioso
                    messages.warning(request, f"Revisa el campo '{field}': {error}")
            
            return render(request, "analisis/subir_datos.html", {
                "form": form,
                "marcadores_disponibles": MARCADORES_VALIDOS,
            })

        # 2. SI EL FORMULARIO ES VÁLIDO: Entra al motor de procesamiento
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

        # 3. SI OCURRE UN ERROR EN EL PIPELINE: Recarga la página y muestra el error
        return render(request, "analisis/subir_datos.html", {
            "form": form,
            "marcadores_disponibles": MARCADORES_VALIDOS,
        })

    # METODO GET: Carga inicial de la página
    muestras = MuestraSuelo.objects.all().order_by("-id")

    return render(request, "analisis/subir_datos.html", {
        "form": SubirDatosForm(),
        "marcadores_disponibles": MARCADORES_VALIDOS,
        "muestras": muestras,
    })