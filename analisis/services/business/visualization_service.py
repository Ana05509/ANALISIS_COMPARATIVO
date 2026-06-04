import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

class VisualizationService:
    """
    Servicio de visualización avanzada encargado del procesamiento metagenómico
    y el renderizado de gráficos estadísticos sin sobrecargar las vistas de Django.
    """

    @staticmethod
    def obtener_paquete_graficos_avanzados(df_pivote: pd.DataFrame, columnas_muestras: list, nivel: str, top_n: int = 10) -> dict:
        """
        Coordinador analítico: Procesa el DataFrame de abundancias microbianas según el Top N elegido.
        Retorna un diccionario estructurado en español con objetos JSON listos para el frontend.
        """
        paquete_graficos = {}
        
        # Validación inicial de datos de entrada
        if df_pivote.empty or not columnas_muestras:
            return paquete_graficos

        # Asegurar casteo numérico limpio de las muestras antes de los cálculos estadísticos
        for col in columnas_muestras:
            df_pivote[col] = pd.to_numeric(df_pivote[col], errors='coerce').fillna(0)

        # Clonación del DataFrame para proteger la inmutabilidad de los datos de la sesión
        df_analisis = df_pivote.copy()
        
        # Calcular la abundancia promedio para realizar el ordenamiento del Top N de microorganismos
        df_analisis['__promedio_abundancia'] = df_analisis[columnas_muestras].mean(axis=1)
        df_ordenado = df_analisis.sort_values(by='__promedio_abundancia', ascending=False)

        # -----------------------------------------------------------------
        # 1. GRÁFICO DE BARRAS APILADAS AL 100% (Composición Comunitaria)
        # -----------------------------------------------------------------
        try:
            df_top = df_ordenado.head(top_n).copy()
            df_resto = df_ordenado.tail(len(df_ordenado) - top_n)

            # Agrupación de taxones menos abundantes bajo la firma de 'Otros'
            if not df_resto.empty:
                fila_otros = {nivel: "Otros microorganismos (< abundancia)"}
                for col in columnas_muestras:
                    fila_otros[col] = df_resto[col].sum()
                df_top = pd.concat([df_top, pd.DataFrame([fila_otros])], ignore_index=True)

            # Transformación de matriz ancha a formato largo para Plotly Express
            df_formato_largo = df_top.melt(
                id_vars=[nivel], 
                value_vars=columnas_muestras,
                var_name="Muestra", 
                value_name="Abundancia"
            )
            
            fig_barras = px.bar(
                df_formato_largo, x="Muestra", y="Abundancia", color=nivel,
                title=f"Composición de la Comunidad Microbiana (Top {top_n} - Nivel: {nivel.capitalize()})",
                template="plotly_white"
            )
            fig_barras.update_layout(
                barmode="stack",
                barnorm="percent",
                yaxis_title="Abundancia Relativa (%)", 
                xaxis_title="Muestras Evaluadas",
                height=520, 
                legend_title=nivel.capitalize()
            )
            
            # Validación estricta de tipo para erradicar advertencias de Pylance y asegurar datos
            json_barras = fig_barras.to_json()
            if isinstance(json_barras, str):
                paquete_graficos["grafico_barras_apiladas"] = json.loads(json_barras)
            else:
                raise TypeError("El motor de Plotly no generó una cadena JSON válida para el gráfico de barras.")
            
        except Exception as e:
            print(f"\n[ERROR DE VISUALIZACIÓN] Gráfico de Barras Apiladas falló. Detalles: {str(e)}")
            paquete_graficos["error_barras"] = f"No se pudo estructurar el gráfico de barras apiladas: {str(e)}"

        # -----------------------------------------------------------------
        # 2. MAPA DE CALOR INTERACTIVO (Core Microbioma / Patrones)
        # -----------------------------------------------------------------
        try:
            df_datos_mapa = df_ordenado.head(top_n)
            
            fig_heatmap = go.Figure(data=go.Heatmap(
                z=df_datos_mapa[columnas_muestras].values,
                x=columnas_muestras,
                y=df_datos_mapa[nivel].tolist(),
                colorscale="Viridis", 
                hoverongaps=False
            ))
            fig_heatmap.update_layout(
                title=f"Mapa de Calor - Patrones de Abundancia Core (Top {top_n})",
                xaxis_title="Muestras de Suelo", 
                yaxis_title=nivel.capitalize(),
                height=400 + (top_n * 6)
            )
            
            json_heatmap = fig_heatmap.to_json()
            if isinstance(json_heatmap, str):
                paquete_graficos["grafico_heatmap"] = json.loads(json_heatmap)
            else:
                raise TypeError("El motor de Plotly no generó una cadena JSON válida para el Mapa de Calor.")
            
        except Exception as e:
            print(f"\n[ERROR DE VISUALIZACIÓN] Gráfico de Mapa de Calor falló. Detalles: {str(e)}")
            paquete_graficos["error_heatmap"] = f"No se pudo estructurar el mapa de calor: {str(e)}"

        # -----------------------------------------------------------------
        # 3. ANÁLISIS DE COMPONENTES PRINCIPALES - PCA (Beta Diversidad)
        # -----------------------------------------------------------------
        try:
            df_datos_pca = df_ordenado.head(top_n)
            
            # Un PCA requiere matemáticamente al menos 2 dimensiones (muestras) y 2 variables (taxones)
            if len(columnas_muestras) >= 2 and len(df_datos_pca) >= 2:
                df_pca_entrada = df_datos_pca[columnas_muestras].set_index(df_datos_pca[nivel]).T
                
                # Escalado estándar (Media = 0, Varianza = 1) antes de aplicar PCA
                datos_escalados = StandardScaler().fit_transform(df_pca_entrada)
                pca = PCA(n_components=2)
                componentes_principales = pca.fit_transform(datos_escalados)
                
                df_pca_resultado = pd.DataFrame(
                    data=componentes_principales, columns=['PC1', 'PC2'], index=columnas_muestras
                ).reset_index().rename(columns={'index': 'Muestra'})
                
                varianza_explicada = pca.explained_variance_ratio_ * 100
                
                fig_pca = px.scatter(
                    df_pca_resultado, x='PC1', y='PC2', text='Muestra',
                    title=f'Análisis de Componentes Principales (PCA - Beta Diversidad con Top {top_n})',
                    template='plotly_white'
                )
                fig_pca.update_traces(
                    textposition='top center', 
                    marker=dict(size=13, symbol="diamond-open", color='DarkSlateGrey')
                )
                fig_pca.update_layout(
                    xaxis_title=f"PC1 ({varianza_explicada[0]:.2f}%)",
                    yaxis_title=f"PC2 ({varianza_explicada[1]:.2f}%)",
                    height=500
                )
                
                json_pca = fig_pca.to_json()
                if isinstance(json_pca, str):
                    paquete_graficos["grafico_pca"] = json.loads(json_pca)
                else:
                    raise TypeError("El motor de Plotly no generó una cadena JSON válida para el análisis PCA.")
            else:
                raise ValueError("Se requieren al menos 2 muestras válidas de suelo para computar un plano de Componentes Principales (PCA).")
                
        except Exception as e:
            print(f"\n[ERROR DE VISUALIZACIÓN] Gráfico Estadístico PCA falló. Detalles: {str(e)}")
            paquete_graficos["error_pca"] = f"No se pudo estructurar el gráfico ecológico PCA: {str(e)}"

        return paquete_graficos