# services/processing/diversity.py
# Cálculo de índices de diversidad microbiana
# README: "Análisis Comparativo: biodiversidad microbiana en cultivos específicos"
#         "Comparativa entre muestras de una misma especie (ej. Cacao CCN51 vs otros clones)"

import math
import pandas as pd


# ---------------------------
# DIVERSIDAD ALFA
# Diversidad dentro de una muestra
# ---------------------------

def calcular_riqueza(df):
    """
    Número total de taxa únicos presentes en la muestra (S).
    Es el índice más básico de diversidad alfa.
    """
    return int(df["%_hits"].gt(0).sum())


def calcular_shannon(df):
    """
    Índice de Shannon (H'): mide diversidad considerando riqueza y equitatividad.
    H' = -Σ(pi * ln(pi)) donde pi = abundancia relativa de cada taxón.
    Valores altos → mayor diversidad microbiana.
    """
    proporciones = df["%_hits"] / 100  # %_hits → proporción
    proporciones = proporciones[proporciones > 0]

    h = -sum(p * math.log(p) for p in proporciones)
    return round(h, 4)


def calcular_simpson(df):
    """
    Índice de Simpson (D): probabilidad de que dos individuos elegidos al azar
    pertenezcan a taxa diferentes. Rango: 0 (sin diversidad) a 1 (máxima diversidad).
    """
    proporciones = df["%_hits"] / 100
    proporciones = proporciones[proporciones > 0]

    d = 1 - sum(p ** 2 for p in proporciones)
    return round(d, 4)


def calcular_equitatividad(df):
    """
    Equitatividad de Pielou (J'): H' / ln(S).
    Mide qué tan uniformemente están distribuidas las abundancias.
    J' = 1 → todas las especies igualmente abundantes.
    """
    s = calcular_riqueza(df)
    if s <= 1:
        return 0.0
    h = calcular_shannon(df)
    return round(h / math.log(s), 4)


def calcular_diversidad_alfa(df):
    """
    Retorna todos los índices de diversidad alfa para una muestra.
    Relacionado con el README: análisis de biodiversidad microbiana por cultivo/variedad.
    """
    return {
        "riqueza":       calcular_riqueza(df),
        "shannon":       calcular_shannon(df),
        "simpson":       calcular_simpson(df),
        "equitatividad": calcular_equitatividad(df),
    }


# ---------------------------
# DIVERSIDAD BETA
# Diversidad entre muestras (Dominantes / Compartidos / Exclusivos)
# README: "Identificación de microorganismos Dominantes, Compartidos y Exclusivos"
# ---------------------------

def identificar_compartidos(df_a, df_b, nivel="genus"):
    """
    Taxa presentes en ambas muestras (Core microbiome).
    README: "Compartidos (Core)"
    """
    set_a = set(df_a[nivel].str.lower())
    set_b = set(df_b[nivel].str.lower())
    compartidos = set_a & set_b
    return sorted(compartidos)


def identificar_exclusivos(df_a, df_b, nivel="genus"):
    """
    Taxa exclusivos de cada muestra.
    README: "Exclusivos"
    Retorna dict con exclusivos de A y exclusivos de B.
    """
    set_a = set(df_a[nivel].str.lower())
    set_b = set(df_b[nivel].str.lower())
    return {
        "exclusivos_a": sorted(set_a - set_b),
        "exclusivos_b": sorted(set_b - set_a),
    }


def calcular_similitud_jaccard(df_a, df_b, nivel="genus"):
    """
    Índice de Jaccard: similitud entre dos comunidades microbianas.
    J = |A ∩ B| / |A ∪ B|. Rango: 0 (sin similitud) a 1 (idénticas).
    Útil para comparar CCN51 vs otros clones de cacao (README).
    """
    set_a = set(df_a[nivel].str.lower())
    set_b = set(df_b[nivel].str.lower())
    interseccion = len(set_a & set_b)
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    return round(interseccion / union, 4)


def calcular_diversidad_beta(df_a, df_b, nivel="genus"):
    """
    Retorna análisis completo de diversidad beta entre dos muestras.
    README: "Análisis Diferencial: comparativa entre muestras de una misma especie"
    """
    return {
        "compartidos":      identificar_compartidos(df_a, df_b, nivel),
        "exclusivos":       identificar_exclusivos(df_a, df_b, nivel),
        "jaccard":          calcular_similitud_jaccard(df_a, df_b, nivel),
        "total_taxa_a":     calcular_riqueza(df_a),
        "total_taxa_b":     calcular_riqueza(df_b),
    }