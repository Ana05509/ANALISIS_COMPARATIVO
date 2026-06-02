# services/processing/taxonomy.py
# Motor bioinformático para el agrupamiento jerárquico multinivel y la filtración de perfiles taxonómicos.

import pandas as pd
from typing import Any, dict

NIVELES_VALIDOS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
CATEGORIAS_CONTROL = {"others", "unclassified", "unknown", "others sp"}

# Jerarquía completa para agrupamiento acumulativo (Garantiza consistencia filogenética)
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
        """
        Agrupa el DataFrame por la cadena de custodia taxonómica correspondiente al nivel solicitado.
        Asegura que las métricas num_hits y %_hits sumen correctamente usando NamedAgg para blindar a Pylance.
        """
        nivel_evaluado = nivel if nivel in NIVELES_VALIDOS else "genus"

        # Extraer ramas de la jerarquía que estén presentes físicamente en el DataFrame
        columnas_grupo = [c for c in JERARQUIA[nivel_evaluado] if c in df.columns]

        if not columnas_grupo:
            return pd.DataFrame()

        df_copy = df.copy()

        # Agregación nombrada explícita en lugar de diccionarios crudos de mapeo
        df_grouped = (
            df_copy.groupby(columnas_grupo, as_index=False)
            .agg(
                num_hits=pd.NamedAgg(column="num_hits", aggfunc="sum"),
                **{"%_hits": pd.NamedAgg(column="%_hits", aggfunc="sum")}
            )
        )

        # Inyectar columna homogeneizada para el consumo de componentes analíticos genéricos
        if nivel_evaluado in df_grouped.columns:
            df_grouped["taxonomia"] = df_grouped[nivel_evaluado].astype(str).str.strip()
        else:
            df_grouped["taxonomia"] = "Unclassified"

        return df_grouped

    @staticmethod
    def obtener_jerarquia_completa(df: pd.DataFrame) -> dict:
        """
        Construye y empaqueta la distribución del microbioma desglosada en todos los rangos taxonómicos.
        Crucial para la renderización de perfiles dinámicos y gráficos multinivel.
        """
        return {nivel: TaxonomyService.agrupar_por_nivel(df, nivel) for nivel in NIVELES_VALIDOS}

    @staticmethod
    def filtrar_por_taxa(df: pd.DataFrame, nivel: str, valor: str) -> pd.DataFrame:
        """
        Segmenta la comunidad microbiana aislando un taxón específico en base a su rango jerárquico.
        Ejemplo: Capturar únicamente registros donde 'phylum' sea 'Firmicutes'.
        """
        if nivel not in df.columns:
            raise ValueError(f"El rango taxonómico '{nivel}' no existe en el set de datos provisto.")
            
        df_copy = df.copy()
        mask = df_copy[nivel].astype(str).str.lower() == valor.strip().lower()
        return df_copy[mask].copy()

    @staticmethod
    def obtener_top_n_con_residuo(df: pd.DataFrame, nivel="genus", top_n=10) -> pd.DataFrame:
        """
        Filtra y ordena la comunidad microbiana extrayendo el Top N legítimo de abundancia.
        Aísla las categorías de control del cálculo del ranking competitivo y las unifica en una
        fila final 'Others' para conservar la consistencia matemática del 100%.
        """
        opciones_validas = [5, 10, 25, 50]
        limite = top_n if top_n in opciones_validas else 10
        nivel_evaluado = nivel if nivel in NIVELES_VALIDOS else "genus"

        # 1. Agrupar la muestra en el nivel solicitado de forma consistente
        df_total = TaxonomyService.agrupar_por_nivel(df, nivel_evaluado)
        if df_total.empty:
            return df_total

        # 2. Separar microorganismos reales aptos para el Top de las bolsas residuales o de control
        mask_control = df_total["taxonomia"].str.lower().isin(CATEGORIAS_CONTROL)
        
        df_organismos_reales = df_total[~mask_control].copy()
        df_bloque_control = df_total[mask_control].copy()

        # 3. Ordenar y segmentar los más dominantes reales
        df_ordenado = df_organismos_reales.sort_values(by="%_hits", ascending=False).reset_index(drop=True)
        
        df_top = df_ordenado.head(limite).copy()
        df_excluidos = df_ordenado.iloc[limite:].copy()

        # 4. Consolidar el residuo matemático total (Excluidos + Bolsas de control previas)
        hits_residuales = int(df_excluidos["num_hits"].sum() + df_bloque_control["num_hits"].sum())
        pct_residual = float(df_excluidos["%_hits"].sum() + df_bloque_control["%_hits"].sum())

        # 5. Si existe un residuo real, inyectar de forma atómica la fila final de control balanceada
        if pct_residual > 0:
            # SOLUCIÓN PYLANCE: Forzar explícitamente que el diccionario sea de tipo dict[str, Any]
            # Esto permite mezclar valores str, int y float de manera segura para el analizador de tipos.
            fila_others: dict[str, Any] = {
                col: "Others" for col in JERARQUIA[nivel_evaluado] if col in df_total.columns
            }
            
            fila_others["num_hits"] = hits_residuales
            fila_others["%_hits"] = round(pct_residual, 5)
            fila_others["taxonomia"] = "Others"
            
            df_others = pd.DataFrame([fila_others])
            df_final = pd.concat([df_top, df_others], ignore_index=True)
            return df_final

        return df_top