# services/processing/abundance.py
# Motor bioinformático para el cálculo, normalización y análisis diferencial de abundancias microbianas.

import pandas as pd
from typing import List

from analisis.constants import NIVELES_VALIDOS

CATEGORIAS_CONTROL = {"others", "unclassified", "unknown", "others sp"}


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

    serie_a = df_a_limpio.groupby(campo)["%_hits"].sum()
    serie_b = df_b_limpio.groupby(campo)["%_hits"].sum()

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