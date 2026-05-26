# services/processing/taxonomy.py
# Agrupamiento jerárquico y clasificación taxonómica multinivel
# README: "Agrupamiento Multinivel: clasificación jerárquica desde Reino hasta Especie"

import pandas as pd

NIVELES_VALIDOS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

# Jerarquía completa para agrupamiento acumulativo
JERARQUIA = {
    "kingdom": ["kingdom"],
    "phylum":  ["kingdom", "phylum"],
    "class":   ["kingdom", "phylum", "class"],
    "order":   ["kingdom", "phylum", "class", "order"],
    "family":  ["kingdom", "phylum", "class", "order", "family"],
    "genus":   ["kingdom", "phylum", "class", "order", "family", "genus"],
    "species": ["kingdom", "phylum", "class", "order", "family", "genus", "species"],
}


def agrupar_por_nivel(df, nivel="genus"):
    """
    Agrupa el DataFrame por el nivel taxonómico solicitado,
    sumando num_hits y %_hits.
    README: "Motor de Agregación: agrupa por cualquier nivel jerárquico solicitado"
    """
    if nivel not in NIVELES_VALIDOS:
        nivel = "genus"

    columnas_grupo = JERARQUIA[nivel]
    columnas_grupo = [c for c in columnas_grupo if c in df.columns]

    df_grouped = (
        df.groupby(columnas_grupo, as_index=False)
          .agg({
              "num_hits": "sum",
              "%_hits":   "sum",
          })
    )

    # Columna unificada "taxonomia" para el nivel solicitado (usada en comparativas)
    df_grouped["taxonomia"] = df_grouped[nivel]

    return df_grouped


def obtener_jerarquia_completa(df):
    """
    Retorna un dict con el DataFrame agrupado para cada nivel taxonómico.
    Útil para el análisis avanzado y los reportes multinivel del README.
    """
    return {nivel: agrupar_por_nivel(df, nivel) for nivel in NIVELES_VALIDOS}


def filtrar_por_taxa(df, nivel, valor):
    """
    Filtra el DataFrame por un taxón específico en cualquier nivel.
    Ejemplo: filtrar_por_taxa(df, "phylum", "Firmicutes")
    """
    if nivel not in df.columns:
        raise ValueError(f"Nivel taxonómico '{nivel}' no encontrado en el DataFrame.")
    return df[df[nivel].str.lower() == valor.lower()].copy()


def obtener_top_n(df, nivel="genus", top_n=10):
    """
    Agrupa por nivel y retorna el Top N por abundancia relativa.
    README: "Cálculo de Top N: filtra y ordena microorganismos por abundancia relativa"
    """
    opciones_validas = [5, 10, 25, 50]
    if top_n not in opciones_validas:
        top_n = 10

    df_agrupado = agrupar_por_nivel(df, nivel)

    return (
        df_agrupado
        .sort_values(by="%_hits", ascending=False)
        .head(top_n)
        .copy()
    )