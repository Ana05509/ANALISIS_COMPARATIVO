from django import template

register = template.Library()

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