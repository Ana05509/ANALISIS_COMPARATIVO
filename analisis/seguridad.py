"""
Seguridad de acceso y aceptación de condiciones legales.

1. Bloqueo del login: tras INTENTOS_MAXIMOS fallos con un mismo correo en
   VENTANA_MINUTOS, ese correo queda bloqueado MINUTOS_BLOQUEO minutos
   (incluso con la contraseña correcta). Se guarda en la tabla BloqueoLogin,
   compartida por todos los procesos; cada fallo se registra con una sola
   sentencia atómica de PostgreSQL.

2. Aceptación de Términos y Política de privacidad: se registra en LogEntry.
   Para pedir una nueva aceptación basta con subir TERMINOS_VERSION.
"""
import hashlib
import math
import time
from datetime import datetime, timedelta, timezone

from django.db import connection, transaction

INTENTOS_MAXIMOS = 3
VENTANA_MINUTOS = 15
MINUTOS_BLOQUEO = 15

TERMINOS_VERSION = "1.1"
TERMINOS_FECHA = "4 de noviembre de 2026"
_SESION_TERMINOS = "terminos_aceptados_version"


# 1. Bloqueo de login

def _clave(correo: str) -> str:
    return hashlib.sha256(correo.strip().lower().encode("utf-8")).hexdigest()


def _ahora() -> datetime:
    # time.time() (y no timezone.now()) para poder simular el paso del tiempo en las pruebas.
    return datetime.fromtimestamp(time.time(), tz=timezone.utc)


def _modelo():
    from analisis.models import BloqueoLogin
    return BloqueoLogin


def minutos_bloqueo_restantes(correo: str) -> int:
    """Minutos que faltan para poder volver a intentar (0 = no bloqueado)."""
    if not correo.strip():
        return 0
    hasta = (_modelo().objects.filter(clave=_clave(correo))
             .values_list("bloqueado_hasta", flat=True).first())
    ahora = _ahora()
    if not hasta or hasta <= ahora:
        return 0
    return max(1, math.ceil((hasta - ahora).total_seconds() / 60))


def registrar_fallo(correo: str) -> int:
    """
    Registra un intento fallido y devuelve cuántos intentos quedan antes del
    bloqueo. Si devuelve 0, el bloqueo acaba de activarse.
    """
    if not correo.strip():
        return INTENTOS_MAXIMOS
    clave, ahora = _clave(correo), _ahora()
    tabla = connection.ops.quote_name(_modelo()._meta.db_table)
    with transaction.atomic(), connection.cursor() as cursor:
        # Inserta o actualiza en una sola sentencia: la fila queda bloqueada hasta
        # el commit, así dos fallos simultáneos nunca leen el mismo contador.
        cursor.execute(
            f"""
            INSERT INTO {tabla} (clave, intentos, bloqueado_hasta)
            VALUES (%(clave)s, ARRAY[%(ahora)s::timestamptz], NULL)
            ON CONFLICT (clave) DO UPDATE SET intentos =
                ARRAY(SELECT t FROM unnest({tabla}.intentos) AS t
                      WHERE t > %(limite)s ORDER BY t) || %(ahora)s::timestamptz
            RETURNING cardinality(intentos)
            """,
            {"clave": clave, "ahora": ahora, "limite": ahora - timedelta(minutes=VENTANA_MINUTOS)},
        )
        fallos = cursor.fetchone()[0]
        if fallos >= INTENTOS_MAXIMOS:
            _modelo().objects.filter(clave=clave).update(
                intentos=[], bloqueado_hasta=ahora + timedelta(minutes=MINUTOS_BLOQUEO)
            )
            return 0
    return INTENTOS_MAXIMOS - fallos


def limpiar_fallos(correo: str) -> None:
    """Tras un inicio de sesión correcto el contador vuelve a cero."""
    _modelo().objects.filter(clave=_clave(correo)).update(intentos=[])


# 2. Aceptación de términos

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
