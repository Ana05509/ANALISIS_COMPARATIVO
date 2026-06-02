import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

class VisualizationService:
    """
    Servicio de visualización avanzada encargado del procesamiento metagenómico
    y renderizado simultáneo sin sobrecargar las vistas.
    """

    @staticmethod
    def obtener_paquete_graficos_avanzados(df_pivote: pd.DataFrame, columnas_muestras: list, nivel: str, top_n: int = 10) -> dict:
        """
        COORDINADOR: Procesa el DataFrame pivoteado según el Top N elegido (5, 10, 25, 50).
        Retorna un diccionario con estructuras JSON listas para ser renderizadas por las pestañas.
        """
        paquete_graficos = {}
        
        if df_pivote.empty or not columnas_muestras:
            return paquete_graficos

        # Asegurar casteo numérico limpio antes de cálculos estadísticos
        for col in columnas_muestras:
            df_pivote[col] = pd.to_numeric(df_pivote[col], errors='coerce').fillna(0)

        # Clonamos el df para no mutar los datos originales de la sesión
        df_analisis = df_pivote.copy()
        
        # Calculamos la abundancia promedio total de cada microorganismo para ordenar el Top N
        df_analisis['__promedio_abundancia'] = df_analisis[columnas_muestras].mean(axis=1)
        df_ordenado = df_analisis.sort_values(by='__promedio_abundancia', ascending=False)

        # =======================================================================
        # 1. GRÁFICO DE BARRAS APILADAS AL 100%
        # =======================================================================
        try:
            df_top = df_ordenado.head(top_n).copy()
            df_resto = df_ordenado.tail(len(df_ordenado) - top_n)

            if not df_resto.empty:
                fila_otros = {nivel: "Otros microorganismos (< abundancia)"}
                for col in columnas_muestras:
                    fila_otros[col] = df_resto[col].sum()
                df_top = pd.concat([df_top, pd.DataFrame([fila_otros])], ignore_index=True)

            df_long = df_top.melt(
                id_vars=[nivel], 
                value_vars=columnas_muestras,
                var_name="Muestra", 
                value_name="Abundancia"
            )
            
            fig_barras = px.bar(
                df_long, x="Muestra", y="Abundancia", color=nivel,
                title=f"Composición de la Comunidad Microbiana (Top {top_n} - Nivel: {nivel.capitalize()})",
                template="plotly_white"
            )
            # CORRECCIÓN PYLANCE: Forzamos el barmode y barnorm desde el layout para evitar el reporte de error
            fig_barras.update_layout(
                barmode="stack",
                barnorm="percent",
                yaxis_title="Abundancia Relativa (%)", 
                height=520, 
                legend_title=nivel.capitalize()
            )
            
            # CORRECCIÓN PYLANCE: Cast seguro a string para evitar que reciba tipos nulos en json.loads
            json_str_barras = str(fig_barras.to_json())
            paquete_graficos["grafico_barras_apiladas"] = json.loads(json_str_barras)
            
        except Exception as e:
            print(f"Error en motor de barras: {e}")

        # =======================================================================
        # 2. MAPA DE CALOR (HEATMAP INTERACTIVO - Core Microbioma)
        # =======================================================================
        try:
            df_heatmap_data = df_ordenado.head(top_n)
            
            fig_heatmap = go.Figure(data=go.Heatmap(
                z=df_heatmap_data[columnas_muestras].values,
                x=columnas_muestras,
                y=df_heatmap_data[nivel].tolist(),
                colorscale="Viridis", hoverongaps=False
            ))
            fig_heatmap.update_layout(
                title=f"Mapa de Calor - Patrones de Abundancia Core (Top {top_n})",
                xaxis_title="Muestras de Suelo", yaxis_title=nivel.capitalize(),
                height=400 + (top_n * 6)
            )
            
            # CORRECCIÓN PYLANCE: Cast seguro a string
            json_str_heatmap = str(fig_heatmap.to_json())
            paquete_graficos["grafico_heatmap"] = json.loads(json_str_heatmap)
            
        except Exception as e:
            print(f"Error en motor de Heatmap: {e}")

        # =======================================================================
        # 3. GRÁFICO DE DISPERSIÓN PCA (BETA DIVERSIDAD)
        # =======================================================================
        try:
            df_pca_subset = df_ordenado.head(top_n)
            
            if len(columnas_muestras) >= 2 and len(df_pca_subset) >= 2:
                df_pca_input = df_pca_subset[columnas_muestras].set_index(df_pca_subset[nivel]).T
                
                scaled_data = StandardScaler().fit_transform(df_pca_input)
                pca = PCA(n_components=2)
                componentes = pca.fit_transform(scaled_data)
                
                df_pca_res = pd.DataFrame(
                    data=componentes, columns=['PC1', 'PC2'], index=columnas_muestras
                ).reset_index().rename(columns={'index': 'Muestra'})
                
                var_explicada = pca.explained_variance_ratio_ * 100
                
                fig_pca = px.scatter(
                    df_pca_res, x='PC1', y='PC2', text='Muestra',
                    title=f'Análisis de Componentes Principales (PCA - Beta Diversidad con Top {top_n})',
                    template='plotly_white'
                )
                fig_pca.update_traces(textposition='top center', marker=dict(size=13, symbol="diamond-open", color='DarkSlateGrey'))
                fig_pca.update_layout(
                    xaxis_title=f"PC1 ({var_explicada[0]:.2f}%)",
                    yaxis_title=f"PC2 ({var_explicada[1]:.2f}%)",
                    height=500
                )
                
                # CORRECCIÓN PYLANCE: Cast seguro a string
                json_str_pca = str(fig_pca.to_json())
                paquete_graficos["grafico_pca"] = json.loads(json_str_pca)
                
        except Exception as e:
            print(f"Error en motor estadístico PCA: {e}")

        return paquete_graficos