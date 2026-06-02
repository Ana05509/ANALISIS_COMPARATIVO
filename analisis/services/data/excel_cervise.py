# services/data/excel_cervise.py
# Archivo de redirección histórica para preservar la compatibilidad y mitigar typos de importación.

from typing import NoReturn

def _notificar_renombramiento() -> NoReturn:
    """Lanza una excepción de importación explicando de forma estricta el cambio de nombre del módulo."""
    raise ImportError(
        "Este archivo (excel_cervise.py) ha sido renombrado a 'excel_service.py'. "
        "Por favor, actualiza tus referencias de código e importa desde "
        "'analisis.services.data.excel_service' para asegurar el correcto funcionamiento del pipeline."
    )

# Disparar la excepción inmediatamente si el módulo es invocado por error en el ecosistema
_notificar_renombramiento()