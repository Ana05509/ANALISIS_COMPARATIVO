import os
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from PIL import Image, UnidentifiedImageError

_TIPOS_PERMITIDOS = {'image/jpeg', 'image/png', 'image/webp'}
_FORMATOS_PERMITIDOS = {'JPEG', 'PNG', 'WEBP'}
_MAX_MB = 2


def _es_imagen_valida(archivo):
    """Verifica el contenido real del archivo; el Content-Type lo declara el navegador y es falsificable."""
    try:
        archivo.seek(0)
        with Image.open(archivo) as img:
            img.verify()
            formato_ok = img.format in _FORMATOS_PERMITIDOS
    except (UnidentifiedImageError, OSError):
        formato_ok = False
    finally:
        archivo.seek(0)
    return formato_ok


@login_required
def perfil_usuario(request):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'upload_avatar':
            archivo = request.FILES.get('avatar')
            if not archivo:
                messages.error(request, 'No se seleccionó ningún archivo.')
            elif archivo.content_type not in _TIPOS_PERMITIDOS:
                messages.error(request, 'Solo se aceptan imágenes JPG, PNG o WEBP.')
            elif archivo.size > _MAX_MB * 1024 * 1024:
                messages.error(request, f'La imagen no debe superar {_MAX_MB} MB.')
            elif not _es_imagen_valida(archivo):
                messages.error(request, 'El archivo no es una imagen válida.')
            else:
                user = request.user
                if user.avatar:
                    try:
                        if os.path.isfile(user.avatar.path):
                            os.remove(user.avatar.path)
                    except Exception:
                        pass
                user.avatar = archivo
                user.save()
                messages.success(request, 'Foto de perfil actualizada.')
            return redirect('analisis:perfil')

        elif action == 'remove_avatar':
            user = request.user
            if user.avatar:
                try:
                    if os.path.isfile(user.avatar.path):
                        os.remove(user.avatar.path)
                except Exception:
                    pass
                user.avatar = None
                user.save()
                messages.success(request, 'Foto de perfil eliminada.')
            return redirect('analisis:perfil')

    return render(request, 'analisis/perfil.html')
