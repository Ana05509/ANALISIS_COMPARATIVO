import json
import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

# Un reporte normal pesa menos de 2 KB; se descarta lo que sea mucho mayor
# para que nadie pueda llenar los logs enviando cuerpos enormes.
_MAX_BYTES = 10_000
_CAMPOS = ("document-uri", "violated-directive", "effective-directive", "blocked-uri",
           "source-file", "line-number", "disposition")


@csrf_exempt  # el navegador lo envía solo, sin token CSRF ni cookies
@require_POST
def reporte_csp(request):
    """
    Recibe los avisos de la Content Security Policy (directiva report-uri) y
    los escribe en el log del servidor. Con CSP_MODO=reporte (valor por
    defecto) sirve para ver qué se bloquearía antes de pasar a CSP_MODO=bloquear.
    """
    if len(request.body) <= _MAX_BYTES:
        try:
            reporte = json.loads(request.body).get("csp-report", {})
            if isinstance(reporte, dict):
                logger.warning("CSP %s", json.dumps(
                    {k: reporte.get(k) for k in _CAMPOS if reporte.get(k) is not None},
                    ensure_ascii=False))
        except (ValueError, AttributeError):
            pass
    return HttpResponse(status=204)
