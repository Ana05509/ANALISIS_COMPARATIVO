"""
Registra en LogEntry ("Registro de Acciones") las acciones hechas desde las
vistas propias de la app, fuera de /admin/.
"""
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType


def registrar_accion(request, obj, mensaje, accion=CHANGE):
    """
    obj: instancia del modelo afectado.
    mensaje: descripción legible de la acción.
    accion: ADDITION, CHANGE o DELETION.
    Sin usuario autenticado no se registra nada.
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return

    LogEntry.objects.create(
        user_id=user.pk,
        content_type_id=ContentType.objects.get_for_model(obj).pk,
        object_id=obj.pk,
        object_repr=str(obj)[:200],
        action_flag=accion,
        change_message=mensaje,
    )
