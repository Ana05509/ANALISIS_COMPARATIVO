from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from analisis import seguridad


def _contexto():
    return {"version": seguridad.TERMINOS_VERSION, "fecha": seguridad.TERMINOS_FECHA}


def terminos(request):
    """Términos de uso (pública: debe poder leerse antes de crear la cuenta)."""
    return render(request, "legal/terminos.html", _contexto())


def privacidad(request):
    """Política de privacidad (pública)."""
    return render(request, "legal/privacidad.html", _contexto())


@login_required
def aceptar_terminos(request):
    """
    Pantalla única para quien aún no aceptó la versión vigente (cuentas
    previas o altas con Google). Al aceptar queda constancia en Auditoría.
    """
    destino = request.POST.get("next") or request.GET.get("next") or ""
    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()},
                                           require_https=request.is_secure()):
        destino = ""

    if seguridad.acepto_terminos(request):
        return redirect(destino or "analisis:dashboard")

    error = None
    if request.method == "POST":
        if request.POST.get("acepto") == "on":
            seguridad.registrar_aceptacion(request, request.user)
            return redirect(destino or "analisis:dashboard")
        error = "Para continuar debes marcar la casilla de aceptación."

    return render(request, "legal/aceptar_terminos.html", {**_contexto(), "next": destino, "error": error})
