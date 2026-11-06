"""
Permisos por rol, en un solo lugar.

Lista blanca: solo los roles de ROLES_CON_CARGA (o una cuenta de staff) pueden
cargar datos y descargar los archivos originales de laboratorio. Un rol nuevo
o desconocido queda sin permiso hasta que se agregue aquí.
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

ROLES_CON_CARGA = frozenset({"admin", "docente"})

MENSAJE_SIN_PERMISO = (
    "Su nivel de cuenta no dispone de permisos para cargar datos. "
    "Si es docente o investigador, contacte al administrador del sistema para actualizar su rol."
)


def puede_cargar_datos(user) -> bool:
    """Subir archivos moleculares, PDFs o ensayos manuales y ver los originales."""
    if not (user and user.is_authenticated and user.is_active):
        return False
    return bool(user.is_staff or getattr(user, "rol", None) in ROLES_CON_CARGA)


def requiere_permiso_carga(destino):
    """Decorador de vista: sin permiso, avisa y redirige a `destino` (nombre de URL)."""
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not puede_cargar_datos(request.user):
                messages.error(request, MENSAJE_SIN_PERMISO)
                return redirect(destino(request, *args, **kwargs) if callable(destino) else destino)
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador


def contexto_permisos(request):
    """Procesador de contexto: expone `puede_cargar` a todas las plantillas."""
    return {"puede_cargar": puede_cargar_datos(getattr(request, "user", None))}
