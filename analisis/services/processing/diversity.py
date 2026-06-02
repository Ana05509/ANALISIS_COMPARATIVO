# Motor de cálculo de ecología microbiana cuantitativa (Diversidad Alfa y Beta).
import math
import pandas as pd

NIVELES_VALIDOS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
FILTROS_EXCLUSION = {"others", "unclassified", "unknown", "nan", "", "others sp"}


class DiversityService:
    """Servicio bioinformático para la evaluación de biodiversidad microbiana en agroecosistemas."""

    # ---------------------------
    # DIVERSIDAD ALFA (Intra-muestra)
    # ---------------------------

    @staticmethod
    def calcular_riqueza(df):
        """
        Número total de taxa únicos y válidos presentes en la muestra (S).
        Excluye las etiquetas artificiales de control y residuos ('Others', 'Unclassified').
        """
        if df.empty:
            return 0
        
        # Filtrar elementos no informativos para el conteo de riqueza real
        mask_validos = (
            df["%_hits"].gt(0) & 
            df.index.to_series().astype(str).str.lower().isin(FILTROS_EXCLUSION).invert()
        )
        if "%_hits" in df.columns and any(col in df.columns for col in NIVELES_VALIDOS):
            # Intentar buscar en las columnas de niveles taxonómicos si están presentes
            for nivel in NIVELES_VALIDOS:
                if nivel in df.columns:
                    mask_validos = mask_validos & df[nivel].astype(str).str.lower().isin(FILTROS_EXCLUSION).invert()
                    break

        return int(mask_validos.sum())

    @staticmethod
    def calcular_shannon(df):
        """
        Índice de Shannon (H'): Mide la incertidumbre/diversidad considerando riqueza y equitatividad.
        Re-normaliza las abundancias locales para evitar sesgos por truncamiento de datos.
        """
        if df.empty or "%_hits" not in df.columns:
            return 0.0

        abundancias = df["%_hits"].astype(float)
        # Filtrar valores en cero o negativos
        abundancias = abundancias[abundancias > 0]

        if abundancias.empty:
            return 0.0

        # Re-normalización ecológica: asegurar que sumen 1.0 de forma estricta en el fragmento evaluado
        total_suma = abundancias.sum()
        proporciones = abundancias / total_suma

        h = -sum(p * math.log(p) for p in proporciones)
        return round(float(h), 4)

    @staticmethod
    def calcular_simpson(df):
        """
        Índice de Simpson (1 - D): Probabilidad de que dos cepas elegidas al azar sean de taxones diferentes.
        """
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
        """
        Equitatividad de Pielou (J'): H' / ln(S).
        Indica qué tan uniforme es la distribución de bacterias u hongos en el suelo.
        """
        s = DiversityService.calcular_riqueza(df)
        if s <= 1:
            return 0.0
        h = DiversityService.calcular_shannon(df)
        return round(float(h / math.log(s)), 4)

    @staticmethod
    def calcular_diversidad_alfa(df):
        """
        Consolida el perfil de diversidad alfa para la caracterización de un lote biológico.
        """
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
        """Sanitiza y extrae el set de taxones reales de una muestra eliminando el residuo matemático."""
        campo = nivel if nivel in NIVELES_VALIDOS else "genus"
        if df.empty or campo not in df.columns:
            return set()

        # Extraer strings limpios en minúsculas sin espacios colaterales
        taxas_raw = df[campo].dropna().astype(str).str.strip().str.lower()
        
        # Aplicar el filtro de exclusión molecular estricto
        set_limpio = {t for t in taxas_raw if t not in FILTROS_EXCLUSION}
        return set_limpio

    @staticmethod
    def identificar_compartidos(df_a, df_b, nivel="genus"):
        """
        Core Microbiome: Taxones verdaderos presentes de forma simultánea en ambas muestras.
        """
        set_a = DiversityService._obtener_set_taxonomico_limpio(df_a, nivel)
        set_b = DiversityService._obtener_set_taxonomico_limpio(df_b, nivel)
        compartidos = set_a & set_b
        return sorted(list(compartidos))

    @staticmethod
    def identificar_exclusivos(df_a, df_b, nivel="genus"):
        """
        Biomarcadores Exclusivos: Identifica qué microorganismos diferencian a un cultivo de otro.
        """
        set_a = DiversityService._obtener_set_taxonomico_limpio(df_a, nivel)
        set_b = DiversityService._obtener_set_taxonomico_limpio(df_b, nivel)
        return {
            "exclusivos_a": sorted(list(set_a - set_b)),
            "exclusivos_b": sorted(list(set_b - set_a)),
        }

    @staticmethod
    def calcular_similitud_jaccard(df_a, df_b, nivel="genus"):
        """
        Índice de similitud comunitaria de Jaccard.
        Efectivo para comparar Cacao CCN51 vs Variedades Nativas sin sesgo por remanentes 'Others'.
        """
        set_a = DiversityService._obtener_set_taxonomico_limpio(df_a, nivel)
        set_b = DiversityService._obtener_set_taxonomico_limpio(df_b, nivel)
        
        interseccion = len(set_a & set_b)
        union = len(set_a | set_b)
        
        if union == 0:
            return 0.0
        return round(float(interseccion / union), 4)

    @staticmethod
    def calcular_diversidad_beta(df_a, df_b, nivel="genus"):
        """
        Análisis Diferencial Completo de Diversidad Beta entre dos matrices biológicas.
        """
        campo = nivel if nivel in NIVELES_VALIDOS else "genus"
        return {
            "compartidos": DiversityService.identify_compartidos_si_fuese_necesario(df_a, df_b, campo), # Mapeado interno interno
            "compartidos_lista": DiversityService.identificar_compartidos(df_a, df_b, campo),
            "exclusivos": DiversityService.identificar_exclusivos(df_a, df_b, campo),
            "jaccard": DiversityService.calcular_similitud_jaccard(df_a, df_b, campo),
            "total_taxa_reales_a": DiversityService.calcular_riqueza(df_a),
            "total_taxa_reales_b": DiversityService.calcular_riqueza(df_b),
            "nivel_evaluado": campo
        }

    @staticmethod
    def identify_compartidos_si_fuese_necesario(df_a, df_b, nivel):
        """Helper para compatibilidad de interfaz que cuenta los compartidos."""
        return len(DiversityService.identificar_compartidos(df_a, df_b, nivel))