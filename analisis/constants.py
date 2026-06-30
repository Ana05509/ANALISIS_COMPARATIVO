"""
Constantes compartidas para el módulo analisis.
Fuente única de verdad para parámetros de validación de la plataforma TerraBioLab UTC.
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
