import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from typing import Dict, List, Any, Optional

class VisualizationService:
    """
    Servicio de visualización avanzada encargado del procesamiento metagenómico
    y el renderizado de gráficos estadísticos sin sobrecargar las vistas de Django.
    """

    @staticmethod
    def crear_grafico_abundancia_barras(df: pd.DataFrame, x: str, y: str, titulo: str = "") -> Optional[str]:
        """Gráfico de barras simple para dashboard."""
        if df.empty or x not in df.columns or y not in df.columns:
            return None
        fig = px.bar(df, x=x, y=y, title=titulo, template="plotly_white")
        fig.update_layout(xaxis_tickangle=-45, height=500)
        return str(fig.to_json())

    @staticmethod
    def crear_grafico_abundancia_pie(df: pd.DataFrame, nombres: str, valores: str, titulo: str = "") -> Optional[str]:
        """Gráfico circular para dashboard."""
        if df.empty or nombres not in df.columns or valores not in df.columns:
            return None
        fig = px.pie(df, names=nombres, values=valores, title=titulo)
        return str(fig.to_json())

    @staticmethod
    def crear_grafico_comparativo_barras(df_comp: pd.DataFrame, muestra_1_nombre: str, muestra_2_nombre: str, top_n: int = 10) -> Optional[str]:
        """Gráfico comparativo de barras para dos muestras con límite dinámico."""
        if df_comp.empty:
            return None
            
        # Buscar columnas de muestras (excluyendo 'taxonomia' y 'clasificacion')
        muestras_cols = [c for c in df_comp.columns if c not in ['taxonomia', 'clasificacion']]
        
        if len(muestras_cols) < 2:
            return None
            
        # Aplicamos el filtro dinámico top_n elegido por el usuario
        top_taxa = df_comp.head(top_n) 
        
        fig = go.Figure()
        fig.add_trace(go.Bar(x=top_taxa['taxonomia'], y=top_taxa[muestras_cols[0]], name=muestra_1_nombre))
        fig.add_trace(go.Bar(x=top_taxa['taxonomia'], y=top_taxa[muestras_cols[1]], name=muestra_2_nombre))
        
        # Añadimos el top_n al título para que el usuario sepa qué está viendo
        fig.update_layout(
            barmode='group', 
            title=f"Comparación: {muestra_1_nombre} vs {muestra_2_nombre} (Top {top_n})", 
            xaxis_tickangle=-45
        )
        
        return str(fig.to_json())

    @staticmethod
    def obtener_paquete_graficos_avanzados(df_pivote: pd.DataFrame, columnas_muestras: List[str], nivel: str, top_n: int = 10) -> Dict[str, Any]:
        """
        Coordinador analítico: Procesa el DataFrame de abundancias microbianas según el Top N elegido.
        Retorna un diccionario estructurado con objetos JSON (dict) listos para el frontend.
        """
        paquete_graficos: Dict[str, Any] = {}
        
        if df_pivote.empty or not columnas_muestras:
            return paquete_graficos

        # Clonación y casteo numérico limpio
        df_analisis = df_pivote.copy()
        for col in columnas_muestras:
            df_analisis[col] = pd.to_numeric(df_analisis[col], errors='coerce').fillna(0)

        # Calcular promedio para el ordenamiento del Top N
        df_analisis['__promedio_abundancia'] = df_analisis[columnas_muestras].mean(axis=1)
        df_ordenado = df_analisis.sort_values(by='__promedio_abundancia', ascending=False)

        # -----------------------------------------------------------------
        # 1. GRÁFICO DE BARRAS APILADAS AL 100%
        # -----------------------------------------------------------------
        try:
            df_top = df_ordenado.head(top_n).copy()
            df_resto = df_ordenado.iloc[top_n:]  # Más limpio y eficiente que .tail()

            if not df_resto.empty:
                fila_otros = {nivel: "Otros microorganismos (< abundancia)"}
                for col in columnas_muestras:
                    fila_otros[col] = df_resto[col].sum()
                df_top = pd.concat([df_top, pd.DataFrame([fila_otros])], ignore_index=True)

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
                barmode="stack", barnorm="percent",
                yaxis_title="Abundancia Relativa (%)", xaxis_title="Muestras Evaluadas",
                height=520, legend_title=nivel.capitalize()
            )
            
            paquete_graficos["grafico_barras_apiladas"] = fig_barras.to_dict()
            
        except Exception as e:
            paquete_graficos["error_barras"] = f"Error en barras apiladas: {str(e)}"

        # -----------------------------------------------------------------
        # 2. MAPA DE CALOR INTERACTIVO
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
                xaxis_title="Muestras de Suelo", yaxis_title=nivel.capitalize(),
                height=400 + (top_n * 6)
            )
            
            paquete_graficos["grafico_heatmap"] = json.loads(str(fig_heatmap.to_json()))
            
        except Exception as e:
            paquete_graficos["error_heatmap"] = f"Error en mapa de calor: {str(e)}"

        # -----------------------------------------------------------------
        # 3. ANÁLISIS DE COMPONENTES PRINCIPALES (PCA)
        # -----------------------------------------------------------------
        try:
            df_datos_pca = df_ordenado.head(top_n)
            
            # Subimos el umbral mínimo a 3 muestras para que el PCA bidimensional tenga sentido biológico
            if len(columnas_muestras) >= 3 and len(df_datos_pca) >= 2:
                df_pca_entrada = df_datos_pca[columnas_muestras].set_index(df_datos_pca[nivel]).T
                
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
                
                paquete_graficos["grafico_pca"] = json.loads(str(fig_pca.to_json()))
            else:
                paquete_graficos["error_pca"] = "Se requieren al menos 3 muestras para un análisis de componentes principales (PCA) representativo."
                
        except Exception as e:
            paquete_graficos["error_pca"] = f"Error en cálculo de ecología PCA: {str(e)}"

        return paquete_graficos