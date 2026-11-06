import pandas as pd
import numpy as np


COLUMNAS_REQUERIDAS = [
    "kingdom", "phylum", "class", "order",
    "family", "genus", "species", "num_hits", "%_hits"
]


class ColumnasInvalidasError(ValueError):
    def __init__(self, faltantes, recibidas):
        self.faltantes = faltantes
        self.recibidas = recibidas
        self.requeridas = COLUMNAS_REQUERIDAS
        super().__init__(
            f"Columnas faltantes: {', '.join(faltantes)}. "
            f"Detectadas: {', '.join(recibidas) or '(ninguna)'}."
        )


class PipelineProcesamiento:
    """Motor de procesamiento y normalización de perfiles taxonómicos masivos."""

    @staticmethod
    def validar_columnas(df):
        """Valida la presencia de la estructura de datos obligatoria."""
        faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
        if faltantes:
            raise ColumnasInvalidasError(
                faltantes=faltantes,
                recibidas=df.columns.tolist(),
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
                .str.replace(r"\bsp\b\.?", "sp", regex=True)
                .str.strip()
            )
            df["species"] = df["species"].replace(["", "nan"], "Unclassified")

        # No convertir datos inválidos en ceros ni truncar lecturas fraccionarias.
        for columna in ("num_hits", "%_hits"):
            valores = df[columna].astype(str).str.strip()
            if columna == "%_hits":
                valores = valores.str.replace(",", ".", regex=False)
            numeros = pd.to_numeric(valores, errors="coerce")
            invalidos = ~np.isfinite(numeros) | (numeros < 0)
            if columna == "num_hits":
                invalidos |= (numeros % 1 != 0) | (numeros > 2147483647)
            else:
                invalidos |= numeros > 100
            if invalidos.any():
                filas = [str(i + 2) for i, mal in enumerate(invalidos) if mal][:10]
                raise ValueError(
                    f"Valores inválidos en {columna}, filas {', '.join(filas)}. "
                    "Use conteos enteros no negativos y porcentajes entre 0 y 100."
                )
            df[columna] = numeros.astype("int64" if columna == "num_hits" else float)
        total = int(df["num_hits"].sum())
        if total:
            esperados = df["num_hits"] / total * 100
            # Acepta el redondeo habitual a dos decimales del laboratorio.
            if not np.allclose(df["%_hits"], esperados, atol=0.02, rtol=0):
                raise ValueError(
                    "Los porcentajes no corresponden a num_hits (tolerancia 0,02 puntos). "
                    "Revise que el archivo contenga el perfil completo de la muestra."
                )
        elif (df["%_hits"] != 0).any():
            raise ValueError("Un perfil sin lecturas no puede tener porcentajes positivos.")

        return df

    @staticmethod
    def procesar_archivo_df(df):
        """
        Procesa y limpia el DataFrame taxonómico completo.
        Guarda TODOS los taxones para preservar la integridad científica.
        El filtrado Top N se aplica únicamente en la capa de visualización.
        """
        df = df.copy()
        df.columns = pd.Index([str(col).strip().lower() for col in df.columns])
        if df.columns.duplicated().any():
            raise ValueError("Hay columnas duplicadas después de normalizar los encabezados.")

        PipelineProcesamiento.validar_columnas(df)
        df = PipelineProcesamiento.limpiar_datos(df)
        df = df[df["num_hits"] > 0].reset_index(drop=True)

        # Vectorizado (antes iterrows): mismas claves, tipos y redondeo.
        salida = pd.DataFrame({
            "kingdom":   df["kingdom"].astype(str),
            "phylum":    df["phylum"].astype(str),
            "tax_class": df["class"].astype(str),
            "order":     df["order"].astype(str),
            "family":    df["family"].astype(str),
            "genus":     df["genus"].astype(str),
            "species":   df["species"].astype(str),
            "num_hits":  df["num_hits"].astype(int),
            "%_hits":    df["%_hits"].astype(float),
        })
        registros = salida.to_dict("records")
        for fila in registros:  # round() de Python: idéntico al de la versión anterior
            fila["num_hits"] = int(fila["num_hits"])
            fila["%_hits"] = round(float(fila["%_hits"]), 5)

        return {
            "data":            registros,
            "total_registros": len(registros),
        }