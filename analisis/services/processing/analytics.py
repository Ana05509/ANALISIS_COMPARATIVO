# Motor de generación de insights agronómicos y consistencia poblacional por lote.

import pandas as pd

NIVELES_VALIDOS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
ETIQUETAS_CONTROL = {"others", "unclassified", "unknown", "others sp"}


class TaxonomicInsightsService:
    """Servicio encargado de traducir matrices numéricas metagenómicas en conclusiones textuales accionables."""

    @staticmethod
    def generar_insights_muestra(df: pd.DataFrame, nivel_evaluado: str = "genus") -> list:
        """
        Analiza el DataFrame de una muestra individual y genera interpretaciones científicas reales.
        Mide dominancia legítima, nivel de indeterminación y la representatividad del residuo.
        """
        insights = []

        # 1. Validación de seguridad en entornos vacíos
        if df.empty or "%_hits" not in df.columns:
            return ["El set de datos no contiene registros suficientes para generar interpretaciones biológicas."]

        # 2. Garantizar que el nivel taxonómico solicitado exista en el DataFrame
        campo_taxonomico = nivel_evaluado if nivel_evaluado in df.columns else None
        if not campo_taxonomico:
            for nivel in NIVELES_VALIDOS:
                if nivel in df.columns:
                    campo_taxonomico = nivel
                    break
        
        if not campo_taxonomico:
            return ["No se identificaron columnas taxonómicas estandarizadas para el análisis."]

        df_analisis = df.copy()
        df_analisis[campo_taxonomico] = df_analisis[campo_taxonomico].astype(str).str.strip()

        # 3. Separar microorganismos reales de las categorías artificiales de control
        df_microorganismos = df_analisis[
            ~df_analisis[campo_taxonomico].str.lower().isin(ETIQUETAS_CONTROL)
        ]
        df_no_clasificados = df_analisis[
            df_analisis[campo_taxonomico].str.lower() == "unclassified"
        ]
        df_others = df_analisis[
            df_analisis[campo_taxonomico].str.lower().isin(["others", "others sp"])
        ]

        # 4. INSIGHT 1: Identificación legítima del Microorganismo Dominante Real (Evitando errores de Pylance)
        if not df_microorganismos.empty:
            dominante = (
                df_microorganismos.groupby(campo_taxonomico, as_index=False)
                .agg(total_pct=pd.NamedAgg(column="%_hits", aggfunc="sum"))
                .sort_values(by="total_pct", ascending=False)
            )
            
            if not dominante.empty:
                fila_top = dominante.iloc[0]
                tax_name = str(fila_top[campo_taxonomico])
                val_pct = float(fila_top["total_pct"])
                insights.append(
                    f"El taxón biológico dominante identificado en nivel de {campo_taxonomico} "
                    f"es '{tax_name}' con un {val_pct:.2f}% de abundancia relativa."
                )
        else:
            insights.append("No se detectaron microorganismos plenamente clasificados dentro del rango dominante.")

        # 5. INSIGHT 2: Nivel de Incertidumbre / Presencia de Desconocidos (Métrica de Calidad)
        if not df_no_clasificados.empty:
            pct_unclassified = float(df_no_clasificados["%_hits"].sum())
            if pct_unclassified > 30.0:
                insights.append(
                    f"Alerta biológica: Existe una alta tasa de microorganismos 'No Clasificados' ({pct_unclassified:.2f}%). "
                    f"El suelo presenta una gran cantidad de materia oscura microbiana o cepas no registradas."
                )
            elif pct_unclassified > 0:
                insights.append(
                    f"El {pct_unclassified:.2f}% de la muestra corresponde a microorganismos no clasificados."
                )

        # 6. INSIGHT 3: Diversidad y Cobertura de la categoría residual 'Others'
        if not df_others.empty:
            pct_others = float(df_others["%_hits"].sum())
            insights.append(
                f"El remanente de la comunidad microbiana de menor abundancia ocupa el {pct_others:.2f}% del suelo "
                f"(agrupado bajo la categoría 'Others')."
            )

        return insights

    @staticmethod
    def generar_insights_lote(matriz_global: pd.DataFrame, nivel: str = "genus") -> list:
        """
        Devora la matriz consolidada de N muestras (ej. tus 4 parcelas del mismo cultivo) y extrae
        conclusiones agronómicas avanzadas basadas en la estabilidad y la desviación estándar.
        """
        insights = []

        if matriz_global.empty or "promedio" not in matriz_global.columns or "desviacion_estandar" not in matriz_global.columns:
            return ["No hay datos de lote suficientes para calcular la variabilidad intra-cultivo."]

        campo = nivel if nivel in NIVELES_VALIDOS else "genus"
        if campo not in matriz_global.columns:
            return ["El nivel taxonómico de la matriz global no coincide con el parámetro de evaluación."]

        # Filtrar remanentes para evaluar biodiversidad real distribuida
        df_real = matriz_global[~matriz_global[campo].astype(str).str.lower().isin(ETIQUETAS_CONTROL)]

        if df_real.empty:
            return ["El lote está compuesto únicamente por categorías no clasificadas o residuales."]

        # 1. INSIGHT DE LOTE 1: El Rey del Cultivo (Mayor promedio en las 4 muestras)
        top_lote = df_real.sort_values(by="promedio", ascending=False).iloc[0]
        insights.append(
            f"A nivel de lote completo, el microorganismo más representativo es '{top_lote[campo]}' "
            f"con un promedio de presencia del {top_lote['promedio']:.2f}% en todas las muestras."
        )

        # 2. INSIGHT DE LOTE 2: Alerta de Inestabilidad Biológica (Desviación Estándar Alta)
        # Una desviación estándar > 5% en un taxón dominante delata que el suelo cambia drásticamente entre parcelas
        taxones_inestables = df_real[(df_real["desviacion_estandar"] > 5.0) & (df_real["promedio"] > 2.0)]
        
        if not taxones_inestables.empty:
            mas_inestable = taxones_inestables.sort_values(by="desviacion_estandar", ascending=False).iloc[0]
            insights.append(
                f"Alerta de heterogeneidad: El taxón '{mas_inestable[campo]}' muestra alta variación entre parcelas "
                f"(Desviación Estándar: {mas_inestable['desviacion_estandar']:.2f}%, Promedio: {mas_inestable['promedio']:.2f}%). "
                f"Esto sugiere un manejo de suelo dispar o microclimas internos en el cultivo."
            )
        else:
            insights.append(
                "Consistencia biológica óptima: No se registran desviaciones drásticas en los taxones principales. "
                "El microbioma es homogéneo a lo largo de las muestras del cultivo."
            )

        # 3. INSIGHT DE LOTE 3: Riqueza Consolidada del Lote
        riqueza_total_lote = int(df_real[campo].nunique())
        insights.append(
            f"El lote unificado de cultivo exhibe una riqueza consolidada de {riqueza_total_lote} taxones "
            f"únicos identificados."
        )

        return insights