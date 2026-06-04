# services/processing/taxonomy.py
# Motor bioinformático para el agrupamiento jerárquico multinivel y la filtración de perfiles taxonómicos.

import pandas as pd
from typing import Any, Dict

NIVELES_VALIDOS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
CATEGORIAS_CONTROL = {"others", "unclassified", "unknown", "others sp"}

JERARQUIA = {
    "kingdom": ["kingdom"],
    "phylum":  ["kingdom", "phylum"],
    "class":   ["kingdom", "phylum", "class"],
    "order":   ["kingdom", "phylum", "class", "order"],
    "family":  ["kingdom", "phylum", "class", "order", "family"],
    "genus":   ["kingdom", "phylum", "class", "order", "family", "genus"],
    "species": ["kingdom", "phylum", "class", "order", "family", "genus", "species"],
}


class TaxonomyService:
    """Servicio encargado de la consolidación, segmentación y agrupamiento jerárquico de perfiles metagenómicos."""

    @staticmethod
    def agrupar_por_nivel(df: pd.DataFrame, nivel="genus") -> pd.DataFrame:
        """Agrupa el DataFrame por la cadena de custodia taxonómica correspondiente al nivel solicitado."""
        if df.empty or "%_hits" not in df.columns or "num_hits" not in df.columns:
            return df.copy()

        nivel_evaluado = nivel if nivel in NIVELES_VALIDOS else "genus"
        columnas_agrupamiento = [col for col in JERARQUIA[nivel_evaluado] if col in df.columns]

        if not columnas_agrupamiento:
            return df.copy()

        df_agrupado = (
            df.groupby(columnas_agrupamiento, as_index=False)
            .agg({"num_hits": "sum", "%_hits": "sum"})
            .sort_values(by="%_hits", ascending=False)
            .reset_index(drop=True)
        )
        return df_agrupado

    @staticmethod
    def filtrar_top_y_consolidar_residuo(df_total: pd.DataFrame, limite=10, nivel="genus") -> pd.DataFrame:
        """Filtra el Top N de microorganismos y une el remanente de menor abundancia bajo una categoría residual."""
        if df_total.empty or "%_hits" not in df_total.columns:
            return df_total.copy()

        nivel_evaluado = nivel if nivel in NIVELES_VALIDOS else "genus"

        if nivel_evaluado not in df_total.columns:
            return df_total.head(limite).copy()

        mask_control = df_total[nivel_evaluado].astype(str).str.lower().isin(CATEGORIAS_CONTROL)
        df_organismos_reales = df_total[~mask_control].copy()
        df_bloque_control = df_total[mask_control].copy()

        df_ordenado = df_organismos_reales.sort_values(by="%_hits", ascending=False).reset_index(drop=True)
        
        df_top = df_ordenado.head(limite).copy()
        df_excluidos = df_ordenado.iloc[limite:].copy()

        hits_residuales = int(df_excluidos["num_hits"].sum() + df_bloque_control["num_hits"].sum())
        pct_residual = float(df_excluidos["%_hits"].sum() + df_bloque_control["%_hits"].sum())

        if pct_residual > 0:
            fila_others: Dict[str, Any] = {
                col: "Others" for col in JERARQUIA[nivel_evaluado] if col in df_total.columns
            }
            
            fila_others["num_hits"] = hits_residuales
            fila_others["%_hits"] = round(pct_residual, 5)
            
            if "species" in fila_others:
                fila_others["species"] = "Others sp"
                
            df_top = pd.concat([df_top, pd.DataFrame([fila_others])], ignore_index=True)

        return df_top