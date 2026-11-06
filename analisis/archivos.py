"""Eliminación física después del commit, sin borrar recursos todavía referenciados."""
import logging
from django.db import transaction
logger = logging.getLogger(__name__)

def limpiar_original_eliminado(sender, instance, using, **kwargs):
    campo = "archivo" if sender._meta.model_name in ("archivomolecular", "archivomolecularrevision") else "archivo_pdf"
    archivo = getattr(instance, campo)
    if not archivo or not archivo.name:
        return
    nombre, storage = archivo.name, archivo.storage
    def borrar():
        from analisis.models import ArchivoMolecular, ArchivoMolecularRevision
        if campo == "archivo":
            if (ArchivoMolecular.objects.using(using).filter(archivo=nombre).exists()
                    or ArchivoMolecularRevision.objects.using(using).filter(archivo=nombre).exists()):
                return
        elif sender.objects.using(using).filter(**{campo: nombre}).exists():
            return
        try:
            storage.delete(nombre)
        except Exception:
            logger.exception("No se pudo eliminar un original desvinculado: %s", nombre)
    transaction.on_commit(borrar, using=using)
