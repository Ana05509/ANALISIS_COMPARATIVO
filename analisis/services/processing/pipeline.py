# Pipeline bioinformático para la normalización, limpieza y cálculo 
# del residuo de abundancia.
import pandas as pd
import re

COLUMNAS_REQUERIDAS = [
    "kingdom", "phylum", "class", "order",
    "family", "genus", "species", "num_hits", "%_hits"
]

NIVELES_VALIDOS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]


class PipelineProcesamiento:
    """Motor de procesamiento y normalización de perfiles taxonómicos masivos."""

    @staticmethod
    def validar_columnas(df):
        """Valida la presencia de la estructura de datos obligatoria."""
        faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
        if faltantes:
            raise ValueError(f"El archivo no cumple con el estándar molecular. Columnas faltantes: {faltantes}")

    @staticmethod
    def limpiar_datos(df):
        """Limpia strings, elimina caracteres especiales taxonómicos y asegura tipos primitivos rígidos."""
        df = df.copy()
        
        # Limpieza inicial de espacios y strings vacíos
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str).str.strip()
        
        # Reemplazar nulos textuales por Unclassified de forma segura sin usar inplace
        valores_nulos = ["", "nan", "None", "NaN", "unclassified", "unknown"]
        df.replace(valores_nulos, "Unclassified", inplace=True)

        # Rellenar remanentes NaN reales según el tipo de columna
        for col in df.columns:
            if df[col].dtype in ["object", "str"]:
                df[col] = df[col].fillna("Unclassified")
            elif df[col].dtype in ["int64", "float64"]:
                df[col] = df[col].fillna(0)

        # Tratamiento específico de nomenclatura botánica/microbiana para especies
        if "species" in df.columns:
            df["species"] = (
                df["species"]
                .str.replace(r"\(.*?\)", "", regex=True)
                .str.replace("_", " ", regex=False)
                .str.replace(r"\bsp\.?\b", "sp", regex=True)
                .str.strip()
            )

        # Casteo forzado y blindado de datos cuantitativos
        df["num_hits"] = pd.to_numeric(df["num_hits"], errors="coerce").fillna(0).astype(int)
        df["%_hits"] = pd.to_numeric(
            df["%_hits"].astype(str).str.replace(",", ".", regex=False),
            errors="coerce"
        ).fillna(0.0).astype(float)
        
        return df

    @staticmethod
    def procesar_archivo_df(df, top_n=10, nivel="genus"):
        """
        Procesa el DataFrame taxonómico. Extrae el Top N dominante y consolida el
        residuo matemático en la fila 'Others' para preservar el 100% de la abundancia.
        """
        df.columns = df.columns.str.strip().str.lower()
        PipelineProcesamiento.validar_columnas(df)
        
        total_registros = len(df)
        df = PipelineProcesamiento.limpiar_datos(df)

        nivel_clean = nivel if nivel in NIVELES_VALIDOS else "genus"
        if top_n not in [5, 10, 25, 50]:
            top_n = 10

        # Ordenar por abundancia descendente
        df_sorted = df.sort_values(by="%_hits", ascending=False).copy()

        # Separar el bloque dominante del residuo ecológico
        df_top = df_sorted.head(top_n).copy()
        df_residuo = df_sorted.iloc[top_n:].copy()

        registros = []
        for _, row in df_top.iterrows():
            registros.append({
                "kingdom": str(row["kingdom"]),
                "phylum": str(row["phylum"]),
                "tax_class": str(row["class"]),  # Guardado seguro evitando la palabra reservada 'class'
                "order": str(row["order"]),
                "family": str(row["family"]),
                "genus": str(row["genus"]),
                "species": str(row["species"]),
                "num_hits": int(row["num_hits"]),
                "%_hits": round(float(row["%_hits"]), 5),
            })

        # CÁLCULO CIENTÍFICO DE "OTHERS": Agrupar el remanente ecológico si existe
        if not df_residuo.empty:
            sum_num_hits = int(df_residuo["num_hits"].sum())
            sum_porcentaje = round(float(df_residuo["%_hits"].sum()), 5)

            if sum_porcentaje > 0 or sum_num_hits > 0:
                registros.append({
                    "kingdom": "Unclassified",
                    "phylum": "Unclassified",
                    "tax_class": "Unclassified",
                    "order": "Unclassified",
                    "family": "Unclassified",
                    "genus": "Others",
                    "species": "Others sp",
                    "num_hits": sum_num_hits,
                    "%_hits": sum_porcentaje,
                })

        return {
            "data": registros,
            "total_registros": total_registros,
            "nivel": nivel_clean,
            "top_n": top_n,
        }