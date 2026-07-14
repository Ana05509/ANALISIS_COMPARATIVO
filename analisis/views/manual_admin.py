from django.contrib import admin
from django.template.response import TemplateResponse


def manual_admin_view(request):
    context = {
        **admin.site.each_context(request),
        "title": "Manual del Administrador",
    }
    return TemplateResponse(request, "admin/manual_admin.html", context)
