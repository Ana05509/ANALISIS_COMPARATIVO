from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Mismo mapeo que usa internamente django.utils.html.json_script().
_JSON_SCRIPT_ESCAPES = {
    ord(">"): "\\u003E",
    ord("<"): "\\u003C",
    ord("&"): "\\u0026",
}


@register.filter(name="json_embed")
def json_embed(json_str):
    """
    Marca como segura una cadena ya serializada con json.dumps() para
    incrustarla dentro de un <script>...</script> como literal JS
    (ej. `var data = {{ mi_json|json_embed }};`).

    Reemplaza a `|safe` a secas: json.dumps() no escapa `</script>`, así que
    un valor con ese texto (p. ej. un género/especie subido en un CSV)
    cerraría el <script> antes de tiempo e inyectaría HTML/JS arbitrario
    en el navegador de cualquiera que vea esa página (XSS almacenado).
    """
    if not isinstance(json_str, str):
        return json_str
    return mark_safe(json_str.translate(_JSON_SCRIPT_ESCAPES))

@register.filter
def get_item(diccionario, clave):
    """Accede a un valor de diccionario por clave."""
    return diccionario.get(clave, 0)

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