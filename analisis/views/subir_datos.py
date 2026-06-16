import os
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from analisis.services.business.upload_service import procesar_upload
from analisis.forms import SubirDatosForm
from analisis.models import MuestraSuelo, VariedadClon, Cultivo

MARCADORES_VALIDOS = ("16S", "ITS")

@login_required
def subir_datos(request):
    if request.user.rol in ['estudiante', 'agricultor']:
        messages.error(request, "Su nivel de cuenta no dispone de permisos para inyectar datos al pipeline molecular.")
        return redirect("analisis:dashboard")

    if request.method == "POST":
        # Obtener el cultivo seleccionado para filtrar variedades
        cultivo_id = request.POST.get('cultivo')
        # Crear formulario con los datos recibidos
        form = SubirDatosForm(request.POST, request.FILES)
        
        # Actualizar el queryset del campo variedad_clon según el cultivo seleccionado
        if cultivo_id:
            try:
                cultivo = Cultivo.objects.get(id=cultivo_id)
                form.fields['variedad_clon'].queryset = VariedadClon.objects.filter(cultivo=cultivo)
            except Cultivo.DoesNotExist:
                form.fields['variedad_clon'].queryset = VariedadClon.objects.none()
        else:
            form.fields['variedad_clon'].queryset = VariedadClon.objects.none()

        if form.is_valid():
            try:
                localidad_limpia = form.cleaned_data.get("localidad")
                resultado = procesar_upload(request)
                messages.success(
                    request,
                    f"Archivo de la localidad de {localidad_limpia} procesado correctamente. {resultado.get('total_registros', 0)} registros importados al sistema."
                )
                return redirect("analisis:dashboard")
            except ValueError as e:
                messages.error(request, f"Error de validación en la estructura de la data: {str(e)}")
            except Exception as e:
                messages.error(request, f"Error al procesar el archivo secuencial: {str(e)}")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.warning(request, f"Revisa el campo '{field}': {error}")

        # En caso de error, volver a mostrar el formulario con los cultivos y marcadores
        cultivos = Cultivo.objects.all()
        return render(request, "analisis/subir_datos.html", {
            "form": form,
            "marcadores_disponibles": MARCADORES_VALIDOS,
            "cultivos": cultivos,
        })

    # Método GET
    form = SubirDatosForm()
    # Inicializar el queryset de variedad_clon vacío (el JavaScript lo llenará)
    form.fields['variedad_clon'].queryset = VariedadClon.objects.none()
    cultivos = Cultivo.objects.all()
    return render(request, "analisis/subir_datos.html", {
        "form": form,
        "marcadores_disponibles": MARCADORES_VALIDOS,
        "cultivos": cultivos,
    })

def cargar_variedades(request):
    cultivo_id = request.GET.get('cultivo_id')
    if cultivo_id:
        variedades = VariedadClon.objects.filter(cultivo_id=cultivo_id).values('id', 'nombre')
        return JsonResponse({'variedades': list(variedades)})
    return JsonResponse({'variedades': []})