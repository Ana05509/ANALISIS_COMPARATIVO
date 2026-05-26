import pandas as pd

def generar_insights(df: pd.DataFrame):
    insights = []

    if df.empty:
        return ["No hay datos suficientes"]

    # Promedio general
    promedio = df["%_hits"].mean()

    # Taxonomía dominante
    dominante = (
        df.groupby("taxonomia")["%_hits"]
        .sum()
        .sort_values(ascending=False)
        .head(1)
    )

    if not dominante.empty:
        tax = dominante.index[0]
        val = dominante.values[0]
        insights.append(f"La taxonomía dominante es {tax} con {val:.2f}%")

    insights.append(f"Promedio general de abundancia: {promedio:.2f}%")

    return insights