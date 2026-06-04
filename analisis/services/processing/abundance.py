# services/processing/abundance.py
# Motor bioinformático para el cálculo, normalización y análisis diferencial de abundancias microbianas.

import pandas as pd
from typing import List

NIVELES_VALIDOS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
CATEGORIAS_CONTROL = {"others", "unclassified", "unknown", "others sp"}


class AbundanceService:
    """Servicio encargado de la calibración matemática y comparativa de abundancias relativas."""

    @staticmethod
    def calcular_abundancia_relativa(df: pd.DataFrame) -> pd.DataFrame:
        """
        Recalcula %_hits como porcentaje real sobre el total de num_hits.
        Garantiza la consistencia si el archivo de origen carece de la métrica porcentual.
        """
        df_copy = df.copy()
        if "num_hits" not in df_copy.columns:
            return df_copy

        total_hits = df_copy["num_hits"].sum()
        if total_hits == 0:
            df_copy["%_hits"] = 0.0
        else:
            df_copy["%_hits"] = (df_copy["num_hits"] / total_hits * 100).round(5)
        return df_copy

    @staticmethod
    def normalizar_abundancias(df: pd.DataFrame) -> pd.DataFrame:
        """Normaliza %_hits a escala 0-1."""
        df_copy = df.copy()
        if "%_hits" not in df_copy.columns or df_copy["%_hits"].max() == df_copy["%_hits"].min():
            return df_copy
        
        max_val = df_copy["%_hits"].max()
        min_val = df_copy["%_hits"].min()
        df_copy["%_hits_normalizado"] = (df_copy["%_hits"] - min_val) / (max_val - min_val)
        return df_copy

    @staticmethod
    def identificar_dominantes(df: pd.DataFrame, umbral=1.0, nivel="genus") -> pd.DataFrame:
        """Filtra biomarcadores dominantes excluyendo categorías de control analítico."""
        if df.empty or "%_hits" not in df.columns:
            return df.copy()

        df_copy = df.copy()
        campo = nivel if nivel in NIVELES_VALIDOS else "genus"

        if campo in df_copy.columns:
            mask = (
                (df_copy["%_hits"] >= umbral) & 
                (~df_copy[campo].astype(str).str.lower().isin(CATEGORIAS_CONTROL))
            )
            return df_copy[mask].copy()
            
        return df_copy[df_copy["%_hits"] >= umbral].copy()

    @staticmethod
    def identificar_raros(df: pd.DataFrame, umbral=0.1, nivel="genus") -> pd.DataFrame:
        """Filtra el microbioma raro u oculto del suelo (presencia < 0.1%)."""
        if df.empty or "%_hits" not in df.columns:
            return df.copy()

        df_copy = df.copy()
        campo = nivel if nivel in NIVELES_VALIDOS else "genus"

        if campo in df_copy.columns:
            mask = (
                (df_copy["%_hits"] < umbral) & (df_copy["%_hits"] > 0) &
                (~df_copy[campo].astype(str).str.lower().isin(CATEGORIAS_CONTROL))
            )
            return df_copy[mask].copy()
            
        return df_copy[(df_copy["%_hits"] < umbral) & (df_copy["%_hits"] > 0)].copy()


# =====================================================================
# FUNCIÓN SOLUCIÓN ENLACE: Requerida por analysis_service.py
# =====================================================================
def comparar_abundancias(df_a: pd.DataFrame, df_b: pd.DataFrame, nivel: str = "genus") -> List[dict]:
    """
    Realiza un análisis diferencial entre dos muestras (A y B) para un nivel taxonómico dado.
    Calcula la diferencia de abundancia (%_hits) para cada microorganismo presente.
    """
    campo = nivel if nivel in NIVELES_VALIDOS else "genus"
    
    if df_a.empty or campo not in df_a.columns or "%_hits" not in df_a.columns:
        df_a = pd.DataFrame(columns=[campo, "%_hits"])
    if df_b.empty or campo not in df_b.columns or "%_hits" not in df_b.columns:
        df_b = pd.DataFrame(columns=[campo, "%_hits"])

    df_a_limpio = df_a[~df_a[campo].astype(str).str.lower().isin(CATEGORIAS_CONTROL)]
    df_b_limpio = df_b[~df_b[campo].astype(str).str.lower().isin(CATEGORIAS_CONTROL)]

    serie_a = df_a_limpio.groupby(campo)["%_hits"].mean()
    serie_b = df_b_limpio.groupby(campo)["%_hits"].mean()

    # Pylance Fix: Convertimos a diccionarios nativos para evitar el choque de tipos en .map()
    mapa_a = serie_a.to_dict()
    mapa_b = serie_b.to_dict()

    df_comparativo = pd.DataFrame(index=serie_a.index.union(serie_b.index))
    df_comparativo["abundancia_a"] = df_comparativo.index.map(mapa_a).fillna(0.0)
    df_comparativo["abundancia_b"] = df_comparativo.index.map(mapa_b).fillna(0.0)
    
    df_comparativo["diferencia"] = df_comparativo["abundancia_a"] - df_comparativo["abundancia_b"]
    df_comparativo = df_comparativo.sort_values(by="diferencia", ascending=False).reset_index()

    resultado = []
    for _, fila in df_comparativo.iterrows():
        resultado.append({
            "taxon": str(fila[campo]),
            "abundancia_a": round(float(fila["abundancia_a"]), 4),
            "abundancia_b": round(float(fila["abundancia_b"]), 4),
            "diferencia": round(float(fila["diferencia"]), 4)
        })
        
    return resultado