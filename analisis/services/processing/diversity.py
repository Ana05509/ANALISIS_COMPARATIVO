import math
import numpy as np
import pandas as pd

from analisis.constants import NIVELES_VALIDOS

FILTROS_EXCLUSION = {"others", "unclassified", "unknown", "nan", "", "others sp"}

class DiversityService:
    """Servicio bioinformático para la evaluación de biodiversidad microbiana."""

    # ---------------------------
    # DIVERSIDAD ALFA (Intra-muestra)
    # ---------------------------

    @staticmethod
    def calcular_riqueza(df):
        """Calcula el número de taxones únicos presentes."""
        if df.empty or "%_hits" not in df.columns:
            return 0
        return len(df[df["%_hits"] > 0])

    @staticmethod
    def calcular_shannon(df):
        if df.empty or "%_hits" not in df.columns:
            return 0.0
        abundancias = df["%_hits"].astype(float)
        abundancias = abundancias[abundancias > 0]
        if abundancias.empty:
            return 0.0
        total_suma = abundancias.sum()
        proporciones = abundancias / total_suma
        h = -sum(p * math.log(p) for p in proporciones)
        return round(float(h), 4)

    @staticmethod
    def calcular_simpson(df):
        if df.empty or "%_hits" not in df.columns:
            return 0.0
        abundancias = df["%_hits"].astype(float)
        abundancias = abundancias[abundancias > 0]
        if abundancias.empty:
            return 0.0
        total_suma = abundancias.sum()
        proporciones = abundancias / total_suma
        d = 1.0 - sum(p ** 2 for p in proporciones)
        return round(float(d), 4)

    @staticmethod
    def calcular_equitatividad(df):
        s = DiversityService.calcular_riqueza(df)
        if s <= 1:
            return 0.0
        h = DiversityService.calcular_shannon(df)
        return round(float(h / math.log(s)), 4)

    @staticmethod
    def calcular_diversidad_alfa(df):
        """Consolida el perfil de diversidad alfa."""
        return {
            "riqueza": DiversityService.calcular_riqueza(df),
            "shannon": DiversityService.calcular_shannon(df),
            "simpson": DiversityService.calcular_simpson(df),
            "equitatividad": DiversityService.calcular_equitatividad(df),
        }

    # ---------------------------
    # DIVERSIDAD BETA (Inter-muestra)
    # ---------------------------

    @staticmethod
    def _obtener_set_taxonomico_limpio(df, nivel="genus"):
        campo = nivel if nivel in NIVELES_VALIDOS else "genus"
        if df.empty or campo not in df.columns:
            return set()
        taxas_raw = df[campo].dropna().astype(str).str.strip().str.lower()
        return {t for t in taxas_raw if t not in FILTROS_EXCLUSION}

    @staticmethod
    def identificar_compartidos(df_a, df_b, nivel="genus"):
        set_a = DiversityService._obtener_set_taxonomico_limpio(df_a, nivel)
        set_b = DiversityService._obtener_set_taxonomico_limpio(df_b, nivel)
        return sorted(list(set_a & set_b))

    @staticmethod
    def identificar_exclusivos(df_a, df_b, nivel="genus"):
        set_a = DiversityService._obtener_set_taxonomico_limpio(df_a, nivel)
        set_b = DiversityService._obtener_set_taxonomico_limpio(df_b, nivel)
        return {
            "exclusivos_a": sorted(list(set_a - set_b)),
            "exclusivos_b": sorted(list(set_b - set_a)),
        }

    @staticmethod
    def calcular_similitud_jaccard(df_a, df_b, nivel="genus"):
        set_a = DiversityService._obtener_set_taxonomico_limpio(df_a, nivel)
        set_b = DiversityService._obtener_set_taxonomico_limpio(df_b, nivel)
        interseccion = len(set_a & set_b)
        union = len(set_a | set_b)
        return round(float(interseccion / union), 4) if union > 0 else 0.0

    @staticmethod
    def calcular_diversidad_beta(df_a, df_b, nivel="genus"):
        campo = nivel if nivel in NIVELES_VALIDOS else "genus"
        compartidos = DiversityService.identificar_compartidos(df_a, df_b, campo)
        return {
            "compartidos": len(compartidos),
            "compartidos_lista": compartidos,
            "exclusivos": DiversityService.identificar_exclusivos(df_a, df_b, campo),
            "jaccard": DiversityService.calcular_similitud_jaccard(df_a, df_b, campo),
            "total_taxa_reales_a": DiversityService.calcular_riqueza(df_a),
            "total_taxa_reales_b": DiversityService.calcular_riqueza(df_b),
            "nivel_evaluado": campo
        }