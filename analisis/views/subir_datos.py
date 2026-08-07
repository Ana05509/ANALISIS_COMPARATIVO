from typing import cast
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, QueryDict
from django.urls import reverse
from analisis.services.business.upload_service import procesar_upload, MuestraDuplicadaError
from analisis.services.processing.pipeline import ColumnasInvalidasError
from analisis.forms import SubirDatosForm
from analisis.models import VariedadClon, Cultivo, MuestraSuelo
from analisis.constants import MARCADORES_VALIDOS
from analisis.audit import registrar_accion
from django.contrib.admin.models import ADDITION

def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'

@login_required
def subir_datos(request):
    if request.user.rol == 'estudiante':
        messages.error(
            request,
            "Su nivel de cuenta no dispone de permisos para cargar datos moleculares. "
            "Si es docente o investigador, contacte al administrador del sistema para actualizar su rol."
        )
        return redirect("analisis:dashboard")

    if request.method == "POST":
        cultivo_id = request.POST.get('cultivo')
        cultivo_manual = request.POST.get('cultivo_manual', '').strip()
        variedad_manual = request.POST.get('variedad_manual', '').strip()
        form = SubirDatosForm(request.POST, request.FILES)
        upload_error = None

        # Cuando el cultivo se ingresa a mano el dropdown queda vacío;
        # desactivamos su validación para que el form no lo rechace.
        # procesar_upload maneja cultivo_manual directamente en el servicio.
        if cultivo_manual:
            form.fields['cultivo'].required = False

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
                    # form.data está tipado como el genérico _DataT de
                    # BaseForm (Pylance no sabe que en runtime es un
                    # QueryDict mutable tras .copy()) — el cast no cambia
                    # nada en runtime, solo le dice al chequeador de tipos
                    # qué es realmente este objeto.
                    datos_mutables = cast(QueryDict, form.data.copy())
                    datos_mutables['variedad_clon'] = variedad.id
                    form.data = datos_mutables
                if created:
                    messages.info(request, f"Variedad '{variedad_manual}' creada automáticamente.")
            except Cultivo.DoesNotExist:
                messages.error(request, "El cultivo seleccionado no existe.")
                return redirect("analisis:subir_datos")

        if form.is_valid():
            try:
                localidad_limpia = form.cleaned_data.get("localidad")
                resultado = procesar_upload(request)
                muestra = MuestraSuelo.objects.filter(pk=resultado.get("muestra_id")).first()
                if muestra:
                    registrar_accion(
                        request, muestra,
                        f"Archivo molecular subido ({resultado.get('total_registros', 0)} registros, "
                        f"localidad {localidad_limpia}).",
                        accion=ADDITION,
                    )
                if _is_ajax(request):
                    return JsonResponse({
                        "ok": True,
                        "redirect": reverse("analisis:dashboard"),
                        "mensaje": f"Archivo de {localidad_limpia} procesado. {resultado.get('total_registros', 0)} registros importados.",
                    })
                messages.success(
                    request,
                    f"Archivo de {localidad_limpia} procesado. {resultado.get('total_registros', 0)} registros importados."
                )
                return redirect("analisis:dashboard")
            except ColumnasInvalidasError as e:
                if _is_ajax(request):
                    return JsonResponse({
                        "ok": False,
                        "tipo": "columnas",
                        "faltantes": e.faltantes,
                        "recibidas": e.recibidas,
                        "requeridas": e.requeridas,
                    }, status=400)
                upload_error = str(e)
            except MuestraDuplicadaError as e:
                if _is_ajax(request):
                    return JsonResponse({
                        "ok": False,
                        "tipo": "duplicado",
                        "codigo": e.codigo,
                        "marcador": e.tipo,
                        "fecha_carga": e.fecha_carga.strftime("%d/%m/%Y %H:%M") if e.fecha_carga else None,
                        "total_taxones": e.total_taxones,
                    }, status=409)
                upload_error = str(e)
            except ValueError as e:
                upload_error = str(e)
            except Exception as e:
                upload_error = f"Error inesperado al procesar el archivo: {str(e)}"
        else:
            primer_error = next(
                (err for errs in form.errors.values() for err in errs), None
            )
            upload_error = primer_error or "Revisa los campos del formulario."

        if _is_ajax(request):
            return JsonResponse({"ok": False, "error": upload_error}, status=400)

        cultivos = Cultivo.objects.all()
        return render(request, "analisis/subir_datos.html", {
            "form": form,
            "marcadores_disponibles": MARCADORES_VALIDOS,
            "cultivos": cultivos,
            "upload_error": upload_error,
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