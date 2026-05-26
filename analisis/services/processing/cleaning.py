# services/processing/cleaning.py
# Limpieza y normalización de datos taxonómicos
# README: "Curación de Datos: Limpieza, normalización y cálculo de abundancias"

import pandas as pd

NIVELES_TAXONOMICOS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]


def limpiar_strings(df):
    """Elimina espacios, nulos y valores vacíos en columnas de texto."""
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
    df.replace(["", "nan", "None", "NaN"], "Unclassified", inplace=True)
    df.fillna("Unclassified", inplace=True)
    return df


def limpiar_species(df):
    """
    Normaliza la columna species eliminando anotaciones entre paréntesis,
    guiones bajos y abreviaturas inconsistentes de 'sp.'.
    """
    if "species" not in df.columns:
        return df

    df["species"] = (
        df["species"]
        .str.replace(r"\(.*?\)", "", regex=True)
        .str.replace("_", " ")
        .str.replace(r"\bsp\.?\b", "sp", regex=True)
        .str.strip()
    )
    return df


def limpiar_numericos(df):
    """
    Convierte num_hits y %_hits a tipos numéricos.
    Corrige el separador decimal coma → punto.
    README: "cálculo de abundancias: num_hits y %_hits"
    """
    if "num_hits" in df.columns:
        df["num_hits"] = pd.to_numeric(df["num_hits"], errors="coerce").fillna(0).astype(int)

    if "%_hits" in df.columns:
        df["%_hits"] = (
            df["%_hits"]
            .astype(str)
            .str.replace(",", ".", regex=False)
        )
        df["%_hits"] = pd.to_numeric(df["%_hits"], errors="coerce").fillna(0)

    return df


def normalizar_taxonomia(df):
    """
    Estandariza mayúsculas en columnas taxonómicas:
    Kingdom, Phylum... → title case para consistencia inter-muestra.
    README: "Normalización: en proceso de optimización para comparativas inter-muestra"
    """
    for col in NIVELES_TAXONOMICOS:
        if col in df.columns:
            df[col] = df[col].str.title()
    return df


def limpiar_datos(df):
    """
    Pipeline de limpieza completo. Orden:
    1. Strings → 2. Numéricos → 3. Species → 4. Taxonomía normalizada
    """
    df = df.copy()
    df = limpiar_strings(df)
    df = limpiar_numericos(df)
    df = limpiar_species(df)
    df = normalizar_taxonomia(df)
    return df