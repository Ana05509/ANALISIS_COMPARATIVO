import pandas as pd

COLUMNAS_REQUERIDAS = [
    "kingdom", "phylum", "class", "order",
    "family", "genus", "species", "num_hits", "%_hits"
]

NIVELES_VALIDOS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

TRADUCCION_COLUMNAS = {
    "kingdom": "Reino", "phylum": "Filo", "class": "Clase",
    "order": "Orden", "family": "Familia", "genus": "Género",
    "species": "Especie", "num_hits": "Número de Hits", "%_hits": "% de Abundancia",
}


def cargar_archivo(ruta_archivo):
    if ruta_archivo.endswith(".csv"):
        df = pd.read_csv(ruta_archivo)
    elif ruta_archivo.endswith((".xlsx", ".xls")):
        df = pd.read_excel(ruta_archivo)
    else:
        raise ValueError("Formato no soportado. Use CSV o Excel.")
    df.columns = df.columns.str.strip().str.lower()
    return df


def validar_columnas(df):
    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas requeridas: {faltantes}")


def limpiar_datos(df):
    df = df.copy()
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
    df.replace(["", "nan", "None", "NaN"], "Unclassified", inplace=True)
    
    # Fill NaN values column-by-column based on dtype
    for col in df.columns:
        if df[col].isna().any():
            if df[col].dtype == 'object' or df[col].dtype == 'str':
                df[col].fillna("Unclassified", inplace=True)
            elif df[col].dtype in ['int64', 'float64']:
                df[col].fillna(0, inplace=True)

    if "species" in df.columns:
        df["species"] = (
            df["species"]
            .str.replace(r"\(.*?\)", "", regex=True)
            .str.replace("_", " ")
            .str.replace(r"\bsp\.?\b", "sp", regex=True)
            .str.strip()
        )

    df["num_hits"] = pd.to_numeric(df["num_hits"], errors="coerce").fillna(0).astype(int)
    df["%_hits"] = pd.to_numeric(
        df["%_hits"].astype(str).str.replace(",", ".", regex=False),
        errors="coerce"
    ).fillna(0)
    return df


def procesar_archivo_df(df, top_n=10, nivel="genus"):
    """
    Pipeline completo. Preserva todas las columnas taxonómicas en cada
    registro para que upload_service pueda mapearlas a ResultadoTaxonomico.
    """
    df.columns = df.columns.str.strip().str.lower()
    validar_columnas(df)
    total_registros = len(df)
    df = limpiar_datos(df)

    if nivel not in NIVELES_VALIDOS:
        nivel = "genus"

    opciones_top_n = [5, 10, 25, 50]
    if top_n not in opciones_top_n:
        top_n = 10

    # Tomar el top N directamente de los datos originales (sin perder columnas)
    df_sorted = df.sort_values(by="%_hits", ascending=False).head(top_n).copy()
    df_sorted["%_hits"]   = df_sorted["%_hits"].round(5)
    df_sorted["num_hits"] = df_sorted["num_hits"].astype(int)

    registros = []
    for _, row in df_sorted.iterrows():
        registros.append({
            "kingdom":  str(row.get("kingdom", "")),
            "phylum":   str(row.get("phylum", "")),
            "class":    str(row.get("class", "")),
            "order":    str(row.get("order", "")),
            "family":   str(row.get("family", "")),
            "genus":    str(row.get("genus", "")),
            "species":  str(row.get("species", "")),
            "num_hits": int(row["num_hits"]),
            "%_hits":   float(row["%_hits"]),
        })

    return {
        "data":            registros,
        "total_registros": total_registros,
        "nivel":           nivel,
        "top_n":           top_n,
    }


def procesar_archivo(ruta_archivo, top_n=10, nivel="genus"):
    df = cargar_archivo(ruta_archivo)
    return procesar_archivo_df(df, top_n=top_n, nivel=nivel)