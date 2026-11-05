from django import template
from django.utils.safestring import mark_safe
from django.conf import settings

register = template.Library()

# Mismo mapeo que usa internamente django.utils.html.json_script().
_JSON_SCRIPT_ESCAPES = {
    ord(">"): "\\u003E",
    ord("<"): "\\u003C",
    ord("&"): "\\u0026",
}


@register.filter(name="json_embed")
def json_embed(json_str):
    """JSON seguro para incrustar en <script> (escapa </script>; usar en lugar de |safe)."""
    if not isinstance(json_str, str):
        return json_str
    return mark_safe(json_str.translate(_JSON_SCRIPT_ESCAPES))


_NIVEL_SALUD_SLUGS = {
    "ÓPTIMO":    "optimo",
    "FAVORABLE": "favorable",
    "MODERADO":  "moderado",
    "EN RIESGO": "riesgo",
    "CRÍTICO":   "critico",
}


@register.filter(name="nivel_slug")
def nivel_slug(nivel_salud):
    """Nivel de salud ('ÓPTIMO', 'FAVORABLE', ...) → sufijo de clase CSS (.card-optimo, ...)."""
    return _NIVEL_SALUD_SLUGS.get(nivel_salud, "critico")

@register.filter
def as_media_url(path):
    """Convierte una ruta relativa de media en URL absoluta."""
    if not path:
        return ''
    return settings.MEDIA_URL + str(path)


@register.filter(name='split')
def split(value, arg=","):
    """
    Divide una cadena de texto en una lista utilizando el delimitador proporcionado.
    Si el valor no es una cadena, devuelve el valor original.
    """
    if isinstance(value, str):
        # Usamos .split(arg) y si necesitas limpiar espacios,
        # puedes usar una lista de comprensión:
        return [item.strip() for item in value.split(arg)]
    return value


@register.filter(name='taxon_legible')
def taxon_legible(valor):
    """Muestra "Unclassified" en español (solo en pantalla, el dato guardado no cambia)."""
    if not valor:
        return valor
    if str(valor).strip().lower() == 'unclassified':
        return 'Sin identificar'
    return valor