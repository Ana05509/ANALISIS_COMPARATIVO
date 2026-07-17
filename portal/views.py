from django.shortcuts import redirect, render


def inicio(request):
    """Portal público: landing institucional con acceso al login del sistema."""
    if request.user.is_authenticated:
        return redirect('analisis:dashboard')
    return render(request, 'portal/inicio.html')
