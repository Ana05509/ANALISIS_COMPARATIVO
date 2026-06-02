# Motor especializado en curación, sanitización y 
# normalización de texto y métricas taxonómicas.

import pandas as pd

NIVELES_TAXONOMICOS_VARIOS = ["kingdom", "phylum", "class", "order", "family", "genus"]
VALORES_NULOS_MUTABLES = ["", "nan", "none", "nan", "unclassified", "unknown", "null", "n/a"]


class DataCleaningService:
    """Servicio bioinformático para la curación estricta de archivos metagenómicos y perfiles de abundancia."""

    @staticmethod
    def homologar_y_limpiar_strings(df):
        """
        Detecta, limpia espacios en blanco y unifica cualquier variante de nulo o no clasificado
        bajo el estándar rígido 'Unclassified' sin usar operaciones inplace propensas a fallos.
        """
        df = df.copy()
        
        # 1. Convertir columnas de tipo objeto a string y aplicar strip() para eliminar espacios locos
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str).str.strip()
                
                # Pasar temporalmente a minúsculas para una detección de nulos/desconocidos 100% efectiva
                mascara_nulos = df[col].str.lower().isin(VALORES_NULOS_MUTABLES) | df[col].isna()
                df.loc[mascara_nulos, col] = "Unclassified"
            else:
                # Tratar nulos en columnas no-objeto de forma preventiva
                df[col] = df[col].fillna("Unclassified" if df[col].dtype == "object" else 0)
                
        return df

    @staticmethod
    def limpiar_species(df):
        """
        Normaliza la columna de especies eliminando ruido de secuenciación como anotaciones 
        entre paréntesis, guiones bajos de bases de datos crudas y abreviaturas inconsistentes.
        Garantiza el formato biológico correcto (todo en minúsculas).
        """
        if "species" not in df.columns:
            return df

        df = df.copy()
        
        # Limpieza de patrones de texto bioinformáticos comunes
        df["species"] = (
            df["species"]
            .astype(str)
            .str.replace(r"\(.*?\)", "", regex=True)
            .str.replace("_", " ", regex=False)
            .str.replace(r"\bsp\.?\b", "sp", regex=True)
            .str.strip()
        )
        
        # Regla Científica Internacional: La especie va estrictamente en minúsculas (ej: 'subtilis', 'putida')
        # Si es un registro 'Unclassified', lo preservamos intacto.
        mascara_validos = df["species"].str.lower() != "unclassified"
        df.loc[mascara_validos, "species"] = df.loc[mascara_validos, "species"].str.lower()
        df.loc[~mascara_validos, "species"] = "Unclassified"
        
        return df

    @staticmethod
    def limpiar_numericos(df):
        """
        Convierte de forma segura los impactos de secuenciación (num_hits) y abundancia (%_hits).
        Soporta y corrige automáticamente archivos que vengan con comas decimales europeas/latinas (,).
        """
        df = df.copy()
        
        if "num_hits" in df.columns:
            df["num_hits"] = pd.to_numeric(df["num_hits"], errors="coerce").fillna(0).astype(int)

        if "%_hits" in df.columns:
            df["%_hits"] = (
                df["%_hits"]
                .astype(str)
                .str.replace(",", ".", regex=False)
            )
            df["%_hits"] = pd.to_numeric(df["%_hits"], errors="coerce").fillna(0.0).astype(float)

        return df

    @staticmethod
    def normalizar_taxonomia_macro(df):
        """
        Estandariza los rangos taxonómicos mayores (Kingdom hasta Genus) a Title Case 
        para permitir cruces consistentes e impecables entre múltiples muestras.
        """
        df = df.copy()
        for col in NIVELES_TAXONOMICOS_VARIOS:
            if col in df.columns:
                # Asegurar formato 'Title' (Ej: 'Bacteria', 'Firmicutes', 'Bacillus')
                df[col] = df[col].astype(str).str.title()
                
                # Re-homologar en caso de que el title case haya alterado un 'Unclassified' a 'Unclassified'
                mascara_unclass = df[col].str.lower() == "unclassified"
                df.loc[mascara_unclass, col] = "Unclassified"
        return df

    @staticmethod
    def ejecutar_pipeline_limpieza_completo(df):
        """
        Ejecuta el flujo secuencial blindado de curación de datos metagenómicos.
        Garantiza que no existan valores NaN intermedios que rompan la persistencia en Django.
        """
        df = df.copy()
        
        # 1. Normalizar y capturar strings / nulos de forma global
        df = DataCleaningService.homologar_y_limpiar_strings(df)
        
        # 2. Corregir y castear tipos numéricos (eliminar comas decimales)
        df = DataCleaningService.limpiar_numericos(df)
        
        # 3. Sanitizar nomenclaturas botánicas/microbianas de especies
        df = DataCleaningService.limpiar_species(df)
        
        # 4. Formatear rangos mayores a Title Case sin romper reglas científicas
        df = DataCleaningService.normalizar_taxonomia_macro(df)
        
        return df