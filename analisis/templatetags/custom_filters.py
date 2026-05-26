from django import template

register = template.Library()


@register.filter
def get_item(diccionario, clave):
    """Accede a un valor de diccionario por clave."""
    return diccionario.get(clave, 0)


@register.filter(name='split')
def split(value, delimiter=","):
    """
    Divide un string por el delimitador indicado.
    Uso: {{ "a,b,c"|split:"," }}
    """
    return [item.strip() for item in str(value).split(delimiter)]