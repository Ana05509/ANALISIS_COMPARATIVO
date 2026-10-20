"""
Seguridad de acceso y aceptación de condiciones legales.

1. Bloqueo temporal del login tras intentos fallidos
   ------------------------------------------------
   Tras INTENTOS_MAXIMOS fallos con un mismo correo dentro de VENTANA_MINUTOS,
   el acceso con ese correo queda bloqueado MINUTOS_BLOQUEO minutos. Durante el
   bloqueo se rechaza cualquier intento, incluso con la contraseña correcta:
   si no, un atacante podría seguir probando contraseñas y entrar en cuanto
   acertara, que es justo lo que el bloqueo debe impedir.

   El contador se guarda por correo escrito (normalizado), exista o no la
   cuenta: el mensaje es idéntico en ambos casos, así que no revela qué
   correos están registrados.

   Usa el caché de Django (LocMemCache por defecto: vive en la memoria del
   proceso). Con un solo worker de gunicorn —la configuración actual— es
   exacto; un reinicio del servidor borra los bloqueos vigentes.

2. Aceptación de Términos de uso y Política de privacidad
   -----------------------------------------------------
   La constancia se guarda en el registro de acciones de Django (LogEntry,
   visible en Auditoría › Registro de Acciones) con fecha, usuario, versión
   e IP: no requiere cambios en la base de datos. Al publicar una nueva
   versión de los textos basta con subir TERMINOS_VERSION para que todos
   vuelvan a aceptarlos.
"""
import hashlib
import math
import time

from django.core.cache import cache

INTENTOS_MAXIMOS = 3
VENTANA_MINUTOS = 15
MINUTOS_BLOQUEO = 15

TERMINOS_VERSION = "1.0"
TERMINOS_FECHA = "20 de octubre de 2026"
_SESION_TERMINOS = "terminos_aceptados_version"


# ---------------------------------------------------------------------------
# 1. Bloqueo de login
# ---------------------------------------------------------------------------

def _claves(correo: str):
    h = hashlib.sha256(correo.strip().lower().encode("utf-8")).hexdigest()
    return f"biomicro:login:fallos:{h}", f"biomicro:login:bloqueo:{h}"


def minutos_bloqueo_restantes(correo: str) -> int:
    """Minutos que faltan para poder volver a intentar (0 = no bloqueado)."""
    if not correo.strip():
        return 0
    _, clave_bloqueo = _claves(correo)
    hasta = cache.get(clave_bloqueo)
    if not hasta or hasta <= time.time():
        return 0
    return max(1, math.ceil((hasta - time.time()) / 60))


def registrar_fallo(correo: str) -> int:
    """
    Registra un intento fallido y devuelve cuántos intentos quedan antes del
    bloqueo. Si devuelve 0, el bloqueo acaba de activarse.
    """
    if not correo.strip():
        return INTENTOS_MAXIMOS
    clave_fallos, clave_bloqueo = _claves(correo)
    ahora = time.time()
    fallos = [t for t in cache.get(clave_fallos, []) if t > ahora - VENTANA_MINUTOS * 60]
    fallos.append(ahora)

    if len(fallos) >= INTENTOS_MAXIMOS:
        cache.set(clave_bloqueo, ahora + MINUTOS_BLOQUEO * 60, MINUTOS_BLOQUEO * 60)
        cache.delete(clave_fallos)
        return 0
    cache.set(clave_fallos, fallos, VENTANA_MINUTOS * 60)
    return INTENTOS_MAXIMOS - len(fallos)


def limpiar_fallos(correo: str) -> None:
    """Tras un inicio de sesión correcto el contador vuelve a cero."""
    clave_fallos, _ = _claves(correo)
    cache.delete(clave_fallos)


# ---------------------------------------------------------------------------
# 2. Aceptación de términos
# ---------------------------------------------------------------------------

def _marca_aceptacion() -> str:
    return f"Aceptación de Términos y Política de privacidad v{TERMINOS_VERSION}"


def acepto_terminos(request) -> bool:
    """¿El usuario autenticado ya aceptó la versión vigente? (cacheado en sesión)"""
    if request.session.get(_SESION_TERMINOS) == TERMINOS_VERSION:
        return True
    from django.contrib.admin.models import LogEntry
    ya = LogEntry.objects.filter(
        user_id=request.user.pk, object_repr=_marca_aceptacion()
    ).exists()
    if ya:
        request.session[_SESION_TERMINOS] = TERMINOS_VERSION
    return ya


def registrar_aceptacion(request, usuario) -> None:
    """Deja constancia (fecha, versión, IP) en Auditoría › Registro de Acciones."""
    from django.contrib.admin.models import LogEntry, ADDITION
    from django.contrib.contenttypes.models import ContentType
    from analisis.apps import _ip_cliente

    ip = _ip_cliente(request) or "desconocida"

    LogEntry.objects.create(
        user_id=usuario.pk,
        content_type_id=ContentType.objects.get_for_model(usuario.__class__).pk,
        object_id=str(usuario.pk),
        object_repr=_marca_aceptacion(),
        action_flag=ADDITION,
        change_message=(
            f"{usuario.get_username()} aceptó los Términos de uso y la Política de privacidad "
            f"(versión {TERMINOS_VERSION} del {TERMINOS_FECHA}) desde la IP {ip}."
        ),
    )
    request.session[_SESION_TERMINOS] = TERMINOS_VERSION
