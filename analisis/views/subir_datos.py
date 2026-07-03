from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from analisis.services.business.upload_service import procesar_upload
from analisis.forms import SubirDatosForm
from analisis.models import VariedadClon, Cultivo
from analisis.constants import MARCADORES_VALIDOS

@login_required
def subir_datos(request):
    if request.user.rol == 'estudiante':
        messages.error(request, "Su nivel de cuenta no dispone de permisos para cargar datos moleculares.")
        return redirect("analisis:dashboard")

    if request.method == "POST":
        cultivo_id = request.POST.get('cultivo')
        variedad_manual = request.POST.get('variedad_manual', '').strip()
        form = SubirDatosForm(request.POST, request.FILES)

        # Actualizar queryset de variedad_clon según cultivo
        if cultivo_id:
            try:
                cultivo = Cultivo.objects.get(id=cultivo_id)
                form.fields['variedad_clon'].queryset = VariedadClon.objects.filter(cultivo=cultivo)
            except Cultivo.DoesNotExist:
                form.fields['variedad_clon'].queryset = VariedadClon.objects.none()
        else:
            form.fields['variedad_clon'].queryset = VariedadClon.objects.none()

        # Manejo de variedad manual
        if variedad_manual and cultivo_id:
            try:
                cultivo = Cultivo.objects.get(id=cultivo_id)
                variedad, created = VariedadClon.objects.get_or_create(
                    nombre=variedad_manual,
                    cultivo=cultivo,
                    defaults={'descripcion': 'Creada manualmente desde la subida'}
                )
                if form.is_valid():
                    form.cleaned_data['variedad_clon'] = variedad
                else:
                    form.data = form.data.copy()
                    form.data['variedad_clon'] = variedad.id
                if created:
                    messages.info(request, f"Variedad '{variedad_manual}' creada automáticamente.")
            except Cultivo.DoesNotExist:
                messages.error(request, "El cultivo seleccionado no existe.")
                return redirect("analisis:subir_datos")

        if form.is_valid():
            try:
                localidad_limpia = form.cleaned_data.get("localidad")
                resultado = procesar_upload(request)
                messages.success(
                    request,
                    f"Archivo de {localidad_limpia} procesado. {resultado.get('total_registros', 0)} registros importados."
                )
                return redirect("analisis:dashboard")
            except ValueError as e:
                messages.error(request, f"Error de validación: {str(e)}")
            except Exception as e:
                messages.error(request, f"Error al procesar: {str(e)}")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.warning(request, f"Revisa el campo '{field}': {error}")

        cultivos = Cultivo.objects.all()
        return render(request, "analisis/subir_datos.html", {
            "form": form,
            "marcadores_disponibles": MARCADORES_VALIDOS,
            "cultivos": cultivos,
        })

    # GET
    form = SubirDatosForm()
    form.fields['variedad_clon'].queryset = VariedadClon.objects.none()
    cultivos = Cultivo.objects.all()
    return render(request, "analisis/subir_datos.html", {
        "form": form,
        "marcadores_disponibles": MARCADORES_VALIDOS,
        "cultivos": cultivos,
    })

@login_required
def cargar_variedades(request):
    cultivo_id = request.GET.get('cultivo_id')
    if cultivo_id:
        variedades = VariedadClon.objects.filter(cultivo_id=cultivo_id).values('id', 'nombre')
        return JsonResponse({'variedades': list(variedades)})
    return JsonResponse({'variedades': []})