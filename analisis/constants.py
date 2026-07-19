"""
Constantes compartidas para el módulo analisis.
Fuente única de verdad para parámetros de validación de la plataforma BioMicro UTC.
"""

MARCADORES_VALIDOS = ("16S", "ITS")

OPCIONES_TOP_N = [5, 10, 25, 50]

NIVELES_VALIDOS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

MAPA_NIVELES = {
    "kingdom": "kingdom",
    "phylum":  "phylum",
    "class":   "tax_class",
    "order":   "order",
    "family":  "family",
    "genus":   "genus",
    "species": "species",
}

CLASIFICACIONES = ("benefico", "fitopatogeno", "neutral", "sin_clasificar")

# Etiquetas en español para la interfaz de usuario
NIVELES_ES: dict[str, str] = {
    "kingdom": "Reino",
    "phylum":  "Filo",
    "class":   "Clase",
    "order":   "Orden",
    "family":  "Familia",
    "genus":   "Género",
    "species": "Especie",
}

MARCADORES_ES: dict[str, str] = {
    "16S": "16S · Bacterias",
    "ITS": "ITS · Hongos",
}

# Listas de tuplas (valor, etiqueta) listas para iterar en templates
NIVELES_CHOICES = list(NIVELES_ES.items())
MARCADORES_CHOICES = list(MARCADORES_ES.items())

# Catálogo puede tener niveles en español o inglés; este mapa unifica ambos.
NIVEL_ALIASES: dict[str, list[str]] = {
    "kingdom": ["kingdom", "reino"],
    "phylum":  ["phylum", "filo"],
    "class":   ["class", "clase", "tax_class"],
    "order":   ["order", "orden"],
    "family":  ["family", "familia"],
    "genus":   ["genus", "género", "genero"],
    "species": ["species", "especie"],
}


def get_taxonomia_annotation(nivel: str):
    """
    Devuelve la expresión ORM para agrupar ResultadoTaxonomico por nivel taxonómico.

    Para 'species' usa CASE WHEN en PostgreSQL: si el campo species ya empieza con
    genus (binomio completo: "Bacillus subtilis") lo usa tal cual; si sólo tiene el
    epíteto ("subtilis") concatena genus + ' ' + species. Cubre los dos formatos que
    produce el pipeline según la fuente del CSV de entrada.
    """
    from django.db.models import CharField
    from django.db.models.expressions import RawSQL

    if nivel == "species":
        return RawSQL(
            "CASE WHEN LOWER(species) LIKE LOWER(genus) || '%%' "
            "THEN species ELSE genus || ' ' || species END",
            [],
            output_field=CharField(),
        )
    from django.db.models import F
    return F(MAPA_NIVELES.get(nivel, "genus"))


def normalizar_nombre_catalogo(nombre: str) -> str:
    """
    Normaliza el nombre de una entrada de catálogo para que coincida con los
    nombres que produce el pipeline al limpiar los CSVs de resultados.
    El catálogo puede contener nombres en formato SILVA/NCBI crudo:
      'Enterobacter_cloacae(AJ251469)' → 'enterobacter cloacae'
    El pipeline aplica las mismas transformaciones al importar datos.
    """
    import re
    s = re.sub(r'\(.*?\)', '', nombre)   # elimina (AJ251469) u otro paréntesis
    s = s.replace('_', ' ')              # guion bajo → espacio
    return s.lower().strip()


def clasificar_taxon(taxon: str, catalogo_map: dict, nivel: str) -> str:
    """
    Lookup con cuatro niveles de fallback para nivel 'species':
    1. Binomio completo → match directo.
    2. Género duplicado (CASE WHEN legacy) → intenta parts[1:].
    3. Catálogo con sólo epíteto → intenta última palabra.
    4. Catálogo sin entradas de especie (solo géneros, p.ej. ITS) → intenta primera palabra.
    """
    if not taxon:
        return "sin_clasificar"
    key = str(taxon).lower().strip()
    clas = catalogo_map.get(key)
    if clas:
        return clas
    if nivel == "species":
        parts = key.split()
        # Caso 2: "Bacillus Bacillus subtilis" → probar "Bacillus subtilis"
        if len(parts) >= 3:
            clas = catalogo_map.get(" ".join(parts[1:]))
            if clas:
                return clas
        # Caso 3: catálogo tiene solo epíteto → última palabra
        if len(parts) >= 2:
            clas = catalogo_map.get(parts[-1])
            if clas:
                return clas
        # Caso 4: catálogo solo tiene géneros (ej: ITS solo tiene "Mortierella")
        # → primera palabra del binomio = género
        if parts:
            clas = catalogo_map.get(parts[0])
            if clas:
                return clas
    return "sin_clasificar"


def buscar_en_catalogo(nombre: str, catalogo: dict, nivel: str):
    """
    Busca un objeto CatalogoMicroorganismo con los mismos fallbacks que clasificar_taxon.
    catalogo es un dict {nombre_normalizado: obj}.
    """
    if not nombre:
        return None
    key = nombre.lower().strip()
    obj = catalogo.get(key)
    if obj:
        return obj
    if nivel == "species":
        parts = key.split()
        if len(parts) >= 3:
            obj = catalogo.get(" ".join(parts[1:]))
            if obj:
                return obj
        if len(parts) >= 2:
            obj = catalogo.get(parts[-1])
            if obj:
                return obj
        if parts:
            obj = catalogo.get(parts[0])
            if obj:
                return obj
    return None
