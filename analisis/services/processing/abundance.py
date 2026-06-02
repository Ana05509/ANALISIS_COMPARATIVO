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
        """
        Normaliza %_hits para asegurar que la muestra sume exactamente el 100.0% analítico,
        mitigando errores de redondeo acumulado en el archivo de origen.
        """
        df_copy = df.copy()
        if "%_hits" not in df_copy.columns:
            return df_copy

        total = df_copy["%_hits"].sum()
        if total == 0:
            return df_copy
            
        df_copy["%_hits"] = (df_copy["%_hits"] / total * 100).round(5)
        return df_copy

    @staticmethod
    def calcular_abundancia_acumulada(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula la curva de distribución acumulada de mayor a menor abundancia.
        Indispensable para las curvas de dominancia del dashboard de investigación.
        """
        df_copy = df.copy()
        if "%_hits" not in df_copy.columns:
            df_copy["%_hits_acumulado"] = 0.0
            return df_copy

        df_copy = df_copy.sort_values(by="%_hits", ascending=False)
        df_copy["%_hits_acumulado"] = df_copy["%_hits"].cumsum().round(5)
        return df_copy

    @staticmethod
    def comparar_abundancias(df_a: pd.DataFrame, df_b: pd.DataFrame, nivel="genus") -> pd.DataFrame:
        """
        Ejecuta el Análisis Diferencial entre dos comunidades microbianas (Ej: Cacao CCN51 vs Clon Nacional).
        Agrupa previamente para evitar explosiones de productos cartesianos y duplicidades taxonómicas.
        """
        campo = nivel if nivel in NIVELES_VALIDOS else "genus"
        
        df_a_clean = df_a.copy()
        df_b_clean = df_b.copy()
        
        for df_target in [df_a_clean, df_b_clean]:
            if campo in df_target.columns:
                df_target[campo] = df_target[campo].astype(str).str.strip()

        agg_a = df_a_clean.groupby(campo, as_index=False).agg(**{"%_hits_a": pd.NamedAgg(column="%_hits", aggfunc="sum")})
        agg_b = df_b_clean.groupby(campo, as_index=False).agg(**{"%_hits_b": pd.NamedAgg(column="%_hits", aggfunc="sum")})

        merged = pd.merge(
            agg_a,
            agg_b,
            on=campo,
            how="outer"
        ).fillna(0.0)

        merged["diferencia"] = (merged["%_hits_a"] - merged["%_hits_b"]).round(5)
        merged["diferencia_abs"] = merged["diferencia"].abs()

        return merged.sort_values(by="diferencia_abs", ascending=False).reset_index(drop=True)

    @staticmethod
    def construir_matriz_abundancia_lote(dfs: List[pd.DataFrame], nombres_muestras: List[str], nivel="genus") -> pd.DataFrame:
        """
        Consolida N muestras (ej. 4 parcelas del mismo cultivo) en una matriz unificada.
        Calcula estadísticas de variabilidad intra-cultivo (desviación estándar y promedio).
        Diseñado para ser 100% inmune a problemas de tipos de Pylance.
        """
        campo = nivel if nivel in NIVELES_VALIDOS else "genus"
        
        if not dfs or len(dfs) != len(nombres_muestras):
            return pd.DataFrame(columns=[campo, "promedio", "desviacion_estandar"])

        muestras_procesadas = []
        columnas_abundancia = []

        # 1. Procesar, agrupar y renombrar de forma independiente cada muestra del lote
        for idx, df_individual in enumerate(dfs):
            nombre_col = f"abundancia_{nombres_muestras[idx]}"
            columnas_abundancia.append(nombre_col)
            
            df_tmp = df_individual.copy()
            if campo in df_tmp.columns:
                df_tmp[campo] = df_tmp[campo].astype(str).str.strip()
            
            # Agrupación segura sin .rename() usando NamedAgg
            agg_individual = df_tmp.groupby(campo, as_index=False).agg(
                **{nombre_col: pd.NamedAgg(column="%_hits", aggfunc="sum")}
            )
            muestras_procesadas.append(agg_individual)

        # 2. Consolidar de forma iterativa usando un merge externo continuo
        matriz_global = muestras_procesadas[0]
        for df_siguiente in muestras_procesadas[1:]:
            matriz_global = pd.merge(matriz_global, df_siguiente, on=campo, how="outer")

        # Rellenar con 0.0 aquellos microorganismos que no aparecieron en alguna de las parcelas
        matriz_global = matriz_global.fillna(0.0)

        # 3. Agregar métricas de control agronómico
        # Promedio de presencia en el cultivo
        matriz_global["promedio"] = matriz_global[columnas_abundancia].mean(axis=1).round(5)
        # Desviación Estándar: Si es baja, significa que el microbioma es homogéneo en todo el cultivo
        matriz_global["desviacion_estandar"] = matriz_global[columnas_abundancia].std(axis=1).fillna(0.0).round(5)

        return matriz_global.sort_values(by="promedio", ascending=False).reset_index(drop=True)

    @staticmethod
    def identificar_dominantes(df: pd.DataFrame, umbral=1.0, nivel="genus") -> pd.DataFrame:
        """
        Filtra biomarcadores dominantes excluyendo categorías de control analítico.
        """
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
        """
        Filtra el microbioma raro u oculto del suelo (presencia < 0.1%).
        """
        if df.empty or "%_hits" not in df.columns:
            return df.copy()

        df_copy = df.copy()
        campo = nivel if nivel in NIVELES_VALIDOS else "genus"

        if campo in df_copy.columns:
            mask = (
                (df_copy["%_hits"] < umbral) & 
                (df_copy["%_hits"] > 0) & 
                (~df_copy[campo].astype(str).str.lower().isin(CATEGORIAS_CONTROL))
            )
            return df_copy[mask].copy()

        return df_copy[(df_copy["%_hits"] < umbral) & (df_copy["%_hits"] > 0)].copy()