"""
excel_service.py
----------------
Responsabilidad: Leer, validar y normalizar archivos Excel o CSV que contienen
resultados taxonómicos (16S e ITS) antes de que el pipeline los procese.

Relación con README:
  - Cubre la etapa "Ingesta de Datos" y "Validación Automática" del pipeline.
  - Verifica las columnas taxonómicas: Kingdom, Phylum, Class, Order, Family, Genus, Species.
  - Verifica las columnas de abundancia: num_hits y %_hits.

Relación con models.py:
  - El DataFrame resultante alimenta la creación de objetos ResultadoTaxonomico.
  - El archivo origen es un ArchivoMolecular (tipo_analisis: "16S" o "ITS").
"""

import pandas as pd
import numpy as np
from pathlib import Path

# Columnas requeridas según README y ResultadoTaxonomico


COLUMNAS_TAXONOMICAS = ["Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species"]
COLUMNAS_ABUNDANCIA  = ["num_hits", "%_hits"]
COLUMNAS_REQUERIDAS  = COLUMNAS_TAXONOMICAS + COLUMNAS_ABUNDANCIA

# Mapeo flexible: nombres alternativos que pueden venir en el archivo raw
ALIAS_COLUMNAS = {
    "kingdom"       : "Kingdom",
    "phylum"        : "Phylum",
    "class"         : "Class",
    "tax_class"     : "Class",   # nombre interno del modelo
    "order"         : "Order",
    "family"        : "Family",
    "genus"         : "Genus",
    "species"       : "Species",
    "num_hits"      : "num_hits",
    "hits"          : "num_hits",
    "%_hits"        : "%_hits",
    "percent_hits"  : "%_hits",
    "porcentaje_hits": "%_hits",
}

# Lectura

def leer_archivo(ruta: str | Path) -> pd.DataFrame:
    """
    Lee un archivo .xlsx, .xls o .csv y devuelve un DataFrame crudo.
    Lanza ValueError si el formato no es compatible.
    """
    ruta = Path(ruta)
    sufijo = ruta.suffix.lower()

    if sufijo in (".xlsx", ".xls"):
        df = pd.read_excel(ruta, dtype=str)
    elif sufijo == ".csv":
        # Intenta separadores comunes
        for sep in (",", ";", "\t"):
            try:
                df = pd.read_csv(ruta, dtype=str, sep=sep)
                if df.shape[1] > 1:
                    break
            except Exception:
                continue
        else:
            raise ValueError(f"No se pudo leer el CSV con separadores estándar: {ruta}")
    else:
        raise ValueError(f"Formato de archivo no soportado: {sufijo}. Use .xlsx, .xls o .csv")

    return df


# ---------------------------------------------------------------------------
# Normalización de columnas
# ---------------------------------------------------------------------------

def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Renombra las columnas del DataFrame usando ALIAS_COLUMNAS para
    unificar nombres independientemente del origen del archivo.
    """
    df.columns = df.columns.str.strip()
    nuevo_nombre = {}
    for col in df.columns:
        clave = col.lower().replace(" ", "_")
        if clave in ALIAS_COLUMNAS:
            nuevo_nombre[col] = ALIAS_COLUMNAS[clave]
    return df.rename(columns=nuevo_nombre)


# ---------------------------------------------------------------------------
# Validación de esquema (README: "Validación Automática")
# ---------------------------------------------------------------------------

def validar_esquema(df: pd.DataFrame) -> dict:
    """
    Verifica que el DataFrame contenga las columnas requeridas.

    Retorna:
        {
            "valido": bool,
            "columnas_faltantes": list[str],
            "columnas_presentes": list[str],
        }
    """
    presentes = set(df.columns.tolist())
    requeridas = set(COLUMNAS_REQUERIDAS)
    faltantes  = sorted(requeridas - presentes)

    return {
        "valido": len(faltantes) == 0,
        "columnas_faltantes": faltantes,
        "columnas_presentes": sorted(presentes & requeridas),
    }


# ---------------------------------------------------------------------------
# Limpieza básica (README: "Curación de Datos")
# ---------------------------------------------------------------------------

def limpiar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    - Elimina filas completamente vacías.
    - Rellena NaN en columnas taxonómicas con cadena vacía.
    - Convierte num_hits y %_hits a float; filas inválidas se ponen en 0.
    - Elimina espacios en blanco al inicio/fin de texto.
    """
    df = df.dropna(how="all").copy()

    for col in COLUMNAS_TAXONOMICAS:
        if col in df.columns:
            df[col] = df[col].fillna("").str.strip()

    for col in ["num_hits", "%_hits"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Función principal de entrada
# ---------------------------------------------------------------------------

def procesar_archivo_excel(ruta: str | Path) -> tuple[pd.DataFrame, dict]:
    """
    Pipeline completo de lectura → normalización → validación → limpieza.

    Retorna:
        (df_limpio, reporte_validacion)

    Uso típico en upload_service.py / pipeline.py:
        df, reporte = procesar_archivo_excel(archivo_molecular.archivo.path)
        if not reporte["valido"]:
            raise ValueError(f"Columnas faltantes: {reporte['columnas_faltantes']}")
        # Continuar con la creación de ResultadoTaxonomico
    """
    df = leer_archivo(ruta)
    df = normalizar_columnas(df)
    reporte = validar_esquema(df)

    if reporte["valido"]:
        df = limpiar_dataframe(df)

    return df, reporte


# ---------------------------------------------------------------------------
# Utilidad: convertir DataFrame a lista de dicts listos para el modelo
# ---------------------------------------------------------------------------

def df_a_resultados(df: pd.DataFrame, archivo_molecular_id: int) -> list[dict]:
    """
    Convierte cada fila del DataFrame en un dict compatible con
    ResultadoTaxonomico (models.py).

    Parámetro:
        archivo_molecular_id: FK hacia ArchivoMolecular.

    Retorna lista de dicts para bulk_create:
        [
            {
                "archivo_id": ...,
                "kingdom": ..., "phylum": ..., "tax_class": ...,
                "order": ..., "family": ..., "genus": ..., "species": ...,
                "num_hits": ..., "porcentaje_hits": ...,
            },
            ...
        ]
    """
    registros = []
    for _, fila in df.iterrows():
        registros.append({
            "archivo_id"      : archivo_molecular_id,
            "kingdom"         : fila.get("Kingdom", ""),
            "phylum"          : fila.get("Phylum", ""),
            "tax_class"       : fila.get("Class", ""),
            "order"           : fila.get("Order", ""),
            "family"          : fila.get("Family", ""),
            "genus"           : fila.get("Genus", ""),
            "species"         : fila.get("Species", ""),
            "num_hits"        : float(fila.get("num_hits", 0)),
            "porcentaje_hits" : float(fila.get("%_hits", 0)),
        })
    return registros
