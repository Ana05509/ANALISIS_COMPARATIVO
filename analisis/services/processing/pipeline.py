import pandas as pd

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
            raise ValueError(
                f"El archivo no cumple con el estándar molecular. "
                f"Columnas faltantes: {faltantes}. "
                f"Columnas recibidas: {list(df.columns)}"
            )

    @staticmethod
    def limpiar_datos(df):
        """
        Limpia strings, elimina caracteres especiales taxonómicos y asegura tipos primitivos.
        Garantiza que fillna() ocurra ANTES del casteo a string para no generar textos 'nan'.
        """
        df = df.copy()

        cols_texto = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
        for col in cols_texto:
            if col not in df.columns:
                df[col] = "Unclassified"

        df[cols_texto] = df[cols_texto].fillna("Unclassified")

        for col in cols_texto:
            df[col] = df[col].astype(str).str.strip()

        valores_nulos = ["", "nan", "None", "NaN", "unclassified", "unknown", "Unclassified "]
        df[cols_texto] = df[cols_texto].replace(valores_nulos, "Unclassified")

        if "species" in df.columns:
            df["species"] = (
                df["species"]
                .str.replace(r"\(.*?\)", "", regex=True)
                .str.replace("_", " ", regex=False)
                .str.replace(r"\bsp\.?\b", "sp", regex=True)
                .str.strip()
            )
            df["species"] = df["species"].replace(["", "nan"], "Unclassified")

        df["num_hits"] = pd.to_numeric(df["num_hits"], errors="coerce").fillna(0).astype(int)
        df["%_hits"] = pd.to_numeric(
            df["%_hits"].astype(str).str.replace(",", ".", regex=False),
            errors="coerce"
        ).fillna(0.0).astype(float)

        return df

    @staticmethod
    def procesar_archivo_df(df):
        """
        Procesa y limpia el DataFrame taxonómico completo.
        Guarda TODOS los taxones para preservar la integridad científica.
        El filtrado Top N se aplica únicamente en la capa de visualización.
        """
        df = df.copy()
        df.columns = df.columns.str.strip().str.lower()

        PipelineProcesamiento.validar_columnas(df)
        df = PipelineProcesamiento.limpiar_datos(df)
        df = df[df["num_hits"] > 0].reset_index(drop=True)

        registros = []
        for _, row in df.iterrows():
            registros.append({
                "kingdom":   str(row["kingdom"]),
                "phylum":    str(row["phylum"]),
                "tax_class": str(row["class"]),
                "order":     str(row["order"]),
                "family":    str(row["family"]),
                "genus":     str(row["genus"]),
                "species":   str(row["species"]),
                "num_hits":  int(row["num_hits"]),
                "%_hits":    round(float(row["%_hits"]), 5),
            })

        return {
            "data":            registros,
            "total_registros": len(registros),
        }