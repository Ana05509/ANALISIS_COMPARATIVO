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


_NIVEL_SALUD_SLUGS = {
    "ÓPTIMO":    "optimo",
    "FAVORABLE": "favorable",
    "MODERADO":  "moderado",
    "EN RIESGO": "riesgo",
    "CRÍTICO":   "critico",
}


@register.filter(name="nivel_slug")
def nivel_slug(nivel_salud):
    """
    Traduce un nivel de salud del suelo ('ÓPTIMO', 'FAVORABLE', ...) al sufijo
    de clase CSS correspondiente (.card-optimo, .text-optimo, .fill-optimo,
    definidas en templates_base.html) — evita repetir la misma cadena de
    if/elif en cada plantilla que muestra el índice de salud.
    """
    return _NIVEL_SALUD_SLUGS.get(nivel_salud, "critico")

_CULTIVOS_MAP = {
    'cacao':     ('🍫', '#7B3F00', '#F7EDE2'),
    'banano':    ('🍌', '#854D0E', '#FEF9C3'),
    'banana':    ('🍌', '#854D0E', '#FEF9C3'),
    'maracuya':  ('🟡', '#92400E', '#FFFBEB'),
    'maracuyá':  ('🟡', '#92400E', '#FFFBEB'),
    'maiz':      ('🌽', '#854D0E', '#FEF9C3'),
    'maíz':      ('🌽', '#854D0E', '#FEF9C3'),
    'palma':     ('🌴', '#166534', '#DCFCE7'),
    'papa':      ('🥔', '#713F12', '#FEF3C7'),
    'tomate':    ('🍅', '#991B1B', '#FEF2F2'),
    'frutilla':  ('🍓', '#9D174D', '#FDF2F8'),
    'mora':      ('🫐', '#4C1D95', '#F5F3FF'),
    'brocoli':   ('🥦', '#14532D', '#F0FDF4'),
    'brócoli':   ('🥦', '#14532D', '#F0FDF4'),
    'pimiento':  ('🫑', '#14532D', '#F0FDF4'),
    'aguacate':  ('🥑', '#14532D', '#F0FDF4'),
    'naranja':   ('🍊', '#9A3412', '#FFF7ED'),
    'limon':     ('🍋', '#713F12', '#FEFCE8'),
    'limón':     ('🍋', '#713F12', '#FEFCE8'),
    'mango':     ('🥭', '#92400E', '#FFFBEB'),
    'piña':      ('🍍', '#713F12', '#FEFCE8'),
    'pina':      ('🍍', '#713F12', '#FEFCE8'),
    'yuca':      ('🌿', '#14532D', '#F0FDF4'),
    'arroz':     ('🌾', '#713F12', '#FEFCE8'),
    'quinua':    ('🌾', '#713F12', '#FEFCE8'),
    'caña':      ('🌿', '#14532D', '#F0FDF4'),
    'cabuya':    ('🌵', '#166534', '#DCFCE7'),
    'uvilla':    ('🍇', '#4C1D95', '#F5F3FF'),
    'café':      ('☕', '#7B3F00', '#F7EDE2'),
    'cafe':      ('☕', '#7B3F00', '#F7EDE2'),
    'pasto':     ('🌿', '#166534', '#DCFCE7'),
    'hierba':    ('🌿', '#166534', '#DCFCE7'),
}
_CULTIVO_DEFAULT = ('🌱', '#166534', '#DCFCE7')

def _cultivo_lookup(nombre):
    if not nombre:
        return _CULTIVO_DEFAULT
    key = nombre.lower().strip()
    for k, v in _CULTIVOS_MAP.items():
        if k in key:
            return v
    return _CULTIVO_DEFAULT

@register.filter
def cultivo_emoji(nombre):
    return _cultivo_lookup(nombre)[0]

@register.filter
def cultivo_color(nombre):
    return _cultivo_lookup(nombre)[1]

@register.filter
def cultivo_bg(nombre):
    return _cultivo_lookup(nombre)[2]


@register.filter
def as_media_url(path):
    """Convierte una ruta relativa de media en URL absoluta."""
    if not path:
        return ''
    return settings.MEDIA_URL + str(path)


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


@register.filter(name='taxon_legible')
def taxon_legible(valor):
    """
    Traduce SOLO para mostrar en pantalla el valor de relleno "Unclassified"
    que el pipeline escribe en genus/species/taxonomia cuando el laboratorio
    no identificó ese nivel taxonómico — en inglés tiene sentido para quien
    ya conoce el pipeline, pero no para un estudiante que apenas ve la
    palabra en una tabla de resultados.

    No toca el dato real: la fila en la base de datos sigue guardando
    literalmente "Unclassified" (así lo esperan los filtros de exclusión de
    abundance.py/diversity.py/catalog_service.py, que hacen match exacto
    contra ese string) — este filtro solo cambia lo que se pinta en el
    HTML, nunca lo que se calcula ni lo que se compara.
    """
    if not valor:
        return valor
    if str(valor).strip().lower() == 'unclassified':
        return 'Sin identificar'
    return valor