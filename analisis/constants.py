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

# Nombres que indican lecturas SIN asignación al nivel taxonómico (no son un taxón).
# Se reportan como fracción ("% sin asignar"), pero no cuentan en riqueza, Shannon,
# Simpson, Bray-Curtis, Jaccard, PCoA, PERMANOVA ni en compartidos/exclusivos.
# Un epíteto sin identificar dentro de un género conocido ("Bacillus Unclassified",
# equivalente a "Bacillus sp.") SÍ es un taxón y no se excluye.
TAXONES_NO_ASIGNADOS = frozenset({"unclassified", "unknown", "others", "others sp", "nan", "none", ""})


def es_taxon_asignado(nombre) -> bool:
    """True si `nombre` es un taxón real y no una etiqueta de lecturas sin asignar."""
    if nombre is None:
        return False
    return str(nombre).strip().lower() not in TAXONES_NO_ASIGNADOS

# Etiquetas en español para la interfaz de usuario. El orden de este dict
# define el orden en que aparecen las opciones en los desplegables de "Nivel
# Taxonómico" (NIVELES_CHOICES más abajo) — Género y Especie van primero por
# ser los niveles que realmente se usan en los análisis; Reino/Filo/Clase/
# Orden/Familia quedan disponibles pero al final de la lista.
NIVELES_ES: dict[str, str] = {
    "genus":   "Género",
    "species": "Especie",
    "kingdom": "Reino",
    "phylum":  "Filo",
    "class":   "Clase",
    "order":   "Orden",
    "family":  "Familia",
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
    No se infiere una especie a partir de un epíteto aislado ni de la función de su género.
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
        if len(parts) >= 3 and parts[0] == parts[1]:
            clas = catalogo_map.get(" ".join(parts[1:]))
            if clas:
                return clas
    return "sin_clasificar"


def buscar_en_catalogo(nombre: str, catalogo: dict, nivel: str):
    """
    Busca una coincidencia al mismo nivel, normalizando solo un género duplicado.
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
        if len(parts) >= 3 and parts[0] == parts[1]:
            obj = catalogo.get(" ".join(parts[1:]))
            if obj:
                return obj
    return None
