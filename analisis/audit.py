"""
Registro de acciones hechas desde las vistas propias de la app (fuera de
/admin/) en la misma bitácora (LogEntry — "Registro de Acciones" en el
sidebar del admin, ver config/settings.py > UNFOLD > Auditoría) que Django
ya llena solo para todo lo hecho desde el panel de administración. Así el
admin ve un único listado con TODAS las acciones significativas del
sistema, sin importar por dónde se hicieron.

Se crea el LogEntry directamente con .objects.create() en vez de usar el
helper de conveniencia del manager (log_action/log_actions): ese helper
cambió de firma entre versiones de Django (log_action -> log_actions en
Django 6), así que construir el registro a mano es más estable y no
depende de qué versión de Django esté instalada.
"""
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.contenttypes.models import ContentType


def registrar_accion(request, obj, mensaje, accion=CHANGE):
    """
    obj: instancia real del modelo afectado (se usa su ContentType + pk).
    mensaje: descripción legible de la acción (se guarda tal cual, sin
             necesidad del formato JSON estructurado que usa el admin).
    accion: ADDITION, CHANGE o DELETION (de django.contrib.admin.models).

    Si no hay usuario autenticado en el request no se registra nada — un
    registro de auditoría sin autor no aporta valor como evidencia.
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
