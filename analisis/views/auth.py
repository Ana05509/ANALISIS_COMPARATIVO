from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy

class CustomLoginView(LoginView):
    """Vista de login personalizada usando el template en templates/registration/login.html"""
    template_name = 'registration/login.html'

class CustomLogoutView(LogoutView):
    """Vista de logout personalizada"""
    next_page = reverse_lazy('analisis:login')
