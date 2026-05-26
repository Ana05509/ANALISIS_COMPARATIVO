# services/processing/abundance.py
# Cálculo y normalización de abundancias relativas
# README: "Curación de Datos: cálculo de abundancias (num_hits y %_hits)"
#         "Normalización: en proceso de optimización para comparativas inter-muestra"

import pandas as pd


def calcular_abundancia_relativa(df):
    """
    Recalcula %_hits como porcentaje real sobre el total de num_hits.
    Útil cuando el archivo cargado no trae %_hits o viene incompleto.
    """
    total_hits = df["num_hits"].sum()
    if total_hits == 0:
        df["%_hits"] = 0.0
    else:
        df["%_hits"] = (df["num_hits"] / total_hits * 100).round(5)
    return df


def normalizar_abundancias(df):
    """
    Normaliza %_hits para que sumen exactamente 100%.
    README: "Normalización: optimización para comparativas inter-muestra"
    Evita que redondeos acumulados distorsionen comparaciones entre muestras.
    """
    total = df["%_hits"].sum()
    if total == 0:
        return df
    df["%_hits"] = (df["%_hits"] / total * 100).round(5)
    return df


def calcular_abundancia_acumulada(df, nivel="genus"):
    """
    Agrega una columna de abundancia acumulada ordenada de mayor a menor.
    Útil para curvas de dominancia y gráficos del dashboard.
    """
    df = df.sort_values(by="%_hits", ascending=False).copy()
    df["%_hits_acumulado"] = df["%_hits"].cumsum().round(5)
    return df


def comparar_abundancias(df_a, df_b, nivel="genus"):
    """
    Compara la abundancia relativa de dos muestras para un nivel taxonómico.
    Retorna un DataFrame con las diferencias absolutas entre muestras.
    README: "Análisis Diferencial: comparativa entre muestras de una misma especie"
    """
    merge = pd.merge(
        df_a[[nivel, "%_hits"]].rename(columns={"%_hits": "%_hits_a"}),
        df_b[[nivel, "%_hits"]].rename(columns={"%_hits": "%_hits_b"}),
        on=nivel,
        how="outer"
    ).fillna(0)

    merge["diferencia"] = (merge["%_hits_a"] - merge["%_hits_b"]).round(5)
    merge["diferencia_abs"] = merge["diferencia"].abs()

    return merge.sort_values(by="diferencia_abs", ascending=False).reset_index(drop=True)


def identificar_dominantes(df, umbral=1.0):
    """
    Identifica microorganismos dominantes: aquellos cuya abundancia supera
    el umbral definido (default: >= 1% de abundancia relativa).
    README: "Identificación de microorganismos Dominantes, Compartidos y Exclusivos"
    """
    return df[df["%_hits"] >= umbral].copy()


def identificar_raros(df, umbral=0.1):
    """
    Identifica microorganismos raros: abundancia menor al umbral (default: < 0.1%).
    Complementa el análisis diferencial del README.
    """
    return df[df["%_hits"] < umbral].copy()