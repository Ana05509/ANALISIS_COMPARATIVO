# services/data/excel_service.py
# Componente de Normalización, Validación de Esquemas y Mapeo de Matrices Taxonómicas.

import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Tuple, Union, Sequence, Hashable

COLUMNAS_TAXONOMICAS = ["Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species"]
COLUMNAS_ABUNDANCIA  = ["num_hits", "%_hits"]
COLUMNAS_REQUERIDAS  = COLUMNAS_TAXONOMICAS + COLUMNAS_ABUNDANCIA

ALIAS_COLUMNAS = {
    "kingdom"       : "Kingdom",
    "phylum"        : "Phylum",
    "class"         : "Class",
    "tax_class"     : "Class",
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


def leer_archivo(ruta: Union[str, Path]) -> pd.DataFrame:
    """Lee un archivo .xlsx, .xls o .csv y devuelve un DataFrame crudo."""
    path_obj = Path(ruta)
    sufijo = path_obj.suffix.lower()

    if sufijo in (".xlsx", ".xls"):
        return pd.read_excel(path_obj, dtype=str)
    elif sufijo == ".csv":
        for sep in (",", ";", "\t"):
            try:
                df = pd.read_csv(path_obj, dtype=str, sep=sep)
                if df.shape[1] > 1:
                    return df
            except Exception:
                continue
        raise ValueError(f"No se pudo leer el CSV con separadores estándar: {path_obj}")
    else:
        raise ValueError(f"Formato de archivo no soportado: {sufijo}. Use .xlsx, .xls o .csv")


def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Renombra las columnas del DataFrame mapeándolas de forma flexible mediante ALIAS_COLUMNAS."""
    df.columns = df.columns.str.strip()
    nuevo_nombre: Dict[str, str] = {}
    for col in df.columns:
        clave = str(col).lower().replace(" ", "_")
        if clave in ALIAS_COLUMNAS:
            nuevo_nombre[col] = ALIAS_COLUMNAS[clave]
    return df.rename(columns=nuevo_nombre)


def validar_esquema(df: pd.DataFrame) -> Dict[str, Any]:
    """Verifica que el DataFrame contenga la matriz mínima viable de información taxonómica."""
    presentes = set(df.columns.tolist())
    requeridas = set(COLUMNAS_REQUERIDAS)
    faltantes  = sorted(requeridas - presentes)

    return {
        "valido": len(faltantes) == 0,
        "columnas_faltantes": faltantes,
        "columnas_presentes": sorted(presentes & requeridas),
    }


def limpiar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Sanea, sanitiza strings y castea numéricamente las columnas del DataFrame."""
    df_clean = df.dropna(how="all").copy()

    for col in COLUMNAS_TAXONOMICAS:
        if col in df_clean.columns:
            df_clean[col] = df_clean[col].fillna("").astype(str).str.strip()

    if "num_hits" in df_clean.columns:
        df_clean["num_hits"] = pd.to_numeric(df_clean["num_hits"], errors="coerce").fillna(0).astype(int)
        
    if "%_hits" in df_clean.columns:
        df_clean["%_hits"] = pd.to_numeric(df_clean["%_hits"], errors="coerce").fillna(0.0).astype(float)

    return df_clean.reset_index(drop=True)


def procesar_archivo_excel(ruta: Union[str, Path]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Pipeline monolítico de ingesta: Lectura -> Normalización -> Validación -> Limpieza."""
    df = leer_archivo(ruta)
    df = normalizar_columnas(df)
    reporte = validar_esquema(df)

    if reporte["valido"]:
        df = limpiar_dataframe(df)

    return df, reporte


def df_a_resultados(df: pd.DataFrame, archivo_molecular_id: int) -> Sequence[Dict[Hashable, Any]]:
    """
    RESOLUCIÓN DE RENDIMIENTO Y TIPADO: Transforma la matriz de Pandas a diccionarios de forma 
    vectorizada en C sin usar el antipadrón iterrows(), preparando los datos para bulk_create.
    Usa Sequence[Dict[Hashable, Any]] para cumplir de forma estricta con las reglas de Pylance.
    """
    if df.empty:
        return []

    # Crear una copia de trabajo limpia para evitar SettingWithCopyWarning
    df_work = df.copy()

    # Mapear de golpe todas las columnas requeridas asegurando su existencia
    target_columns = {
        "Kingdom": "kingdom", "Phylum": "phylum", "Class": "tax_class",
        "Order": "order", "Family": "family", "Genus": "genus", "Species": "species"
    }

    # Asegurar compatibilidad estricta de nombres y rellenar nulos residuales
    for col_excel, col_model in target_columns.items():
        if col_excel not in df_work.columns:
            df_work[col_model] = ""
        else:
            df_work[col_model] = df_work[col_excel].fillna("").astype(str)

    # Castear de forma vectorizada las métricas numéricas al tipo exacto del modelo ORM
    df_work["num_hits"] = pd.to_numeric(df_work.get("num_hits", 0), errors="coerce").fillna(0).astype(int)
    df_work["porcentaje_hits"] = pd.to_numeric(df_work.get("%_hits", 0), errors="coerce").fillna(0.0).astype(float)
    
    # Inyectar la llave foránea de manera masiva
    df_work["archivo_id"] = archivo_molecular_id

    # Columnas finales exactas que espera el modelo de Django
    columnas_finales = ["archivo_id", "kingdom", "phylum", "tax_class", "order", "family", "genus", "species", "num_hits", "porcentaje_hits"]
    
    # Exportación instantánea vectorizada compatible con el tipado de los stubs de Pandas
    resultados_raw = df_work[columnas_finales].to_dict(orient="records")
    return resultados_raw