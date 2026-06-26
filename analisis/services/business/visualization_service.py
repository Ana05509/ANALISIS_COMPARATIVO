import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sklearn.manifold import MDS
from scipy.spatial.distance import braycurtis
from typing import Dict, List, Any, Optional
import numpy as np

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
        try:
            fig = px.bar(df, x=x, y=y, title=titulo, template="plotly_white")
            fig.update_layout(xaxis_tickangle=-45, height=500)
            return str(fig.to_json())
        except Exception as e:
            print(f"Error en gráfico de barras: {e}")
            return None

    @staticmethod
    def crear_grafico_abundancia_pie(df: pd.DataFrame, nombres: str, valores: str, titulo: str = "") -> Optional[str]:
        """Gráfico circular para dashboard."""
        if df.empty or nombres not in df.columns or valores not in df.columns:
            return None
        try:
            fig = px.pie(df, names=nombres, values=valores, title=titulo)
            return str(fig.to_json())
        except Exception as e:
            print(f"Error en gráfico de pastel: {e}")
            return None

    @staticmethod
    def crear_grafico_comparativo_barras(df_comp: pd.DataFrame, muestra_1_nombre: str, muestra_2_nombre: str, top_n: int = 10) -> Optional[str]:
        """Gráfico comparativo de barras para dos muestras con límite dinámico."""
        if df_comp.empty:
            return None
        try:
            muestras_cols = [c for c in df_comp.columns if c not in ['taxonomia', 'clasificacion']]
            if len(muestras_cols) < 2:
                return None
                
            top_taxa = df_comp.head(top_n)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=top_taxa['taxonomia'], y=top_taxa[muestras_cols[0]], name=muestra_1_nombre))
            fig.add_trace(go.Bar(x=top_taxa['taxonomia'], y=top_taxa[muestras_cols[1]], name=muestra_2_nombre))
            fig.update_layout(
                barmode='group',
                title=f"Comparación: {muestra_1_nombre} vs {muestra_2_nombre} (Top {top_n})",
                xaxis_tickangle=-45
            )
            return str(fig.to_json())
        except Exception as e:
            print(f"Error en gráfico comparativo: {e}")
            return None

    @staticmethod
    def obtener_paquete_graficos_avanzados(df_pivote: pd.DataFrame, columnas_muestras: List[str], nivel: str, top_n: int = 10) -> Dict[str, Any]:
        """
        Coordinador analítico: Procesa el DataFrame de abundancias microbianas según el Top N elegido.
        Retorna un diccionario estructurado con objetos JSON (dict) listos para el frontend.
        """
        paquete_graficos: Dict[str, Any] = {}
        
        if df_pivote.empty or not columnas_muestras:
            return paquete_graficos

        # Verificar que la columna 'nivel' exista (debe ser columna, no índice)
        if nivel not in df_pivote.columns:
            # Si el índice tiene el nombre 'nivel', resetearlo
            if df_pivote.index.name == nivel:
                df_pivote = df_pivote.reset_index()
            else:
                return {"error": f"La columna '{nivel}' no existe en el DataFrame"}

        # Clonación y casteo numérico limpio
        df_analisis = df_pivote.copy()
        for col in columnas_muestras:
            if col in df_analisis.columns:
                df_analisis[col] = pd.to_numeric(df_analisis[col], errors='coerce').fillna(0)
            else:
                df_analisis[col] = 0.0

        # Calcular promedio para el ordenamiento del Top N
        df_analisis['__promedio_abundancia'] = df_analisis[columnas_muestras].mean(axis=1)
        df_ordenado = df_analisis.sort_values(by='__promedio_abundancia', ascending=False)

        # -----------------------------------------------------------------
        # 1. GRÁFICO DE BARRAS APILADAS AL 100%
        # -----------------------------------------------------------------
        try:
            df_top = df_ordenado.head(top_n).copy()
            df_resto = df_ordenado.iloc[top_n:]

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

            # Paleta fija; "Otros" siempre en gris para no confundir con taxones reales
            PALETA = ['#1D9E75','#0F6E56','#BA7517','#185FA5','#A32D2D','#9E6515',
                      '#0C447C','#6B4E9E','#2E8B57','#c7a640','#5F5E5A','#085041']
            taxa_ordenados = df_top[nivel].tolist()
            color_map = {}
            idx = 0
            for taxon in taxa_ordenados:
                if taxon and 'otros' in str(taxon).lower():
                    color_map[taxon] = '#B0B8C1'   # gris neutro
                else:
                    color_map[taxon] = PALETA[idx % len(PALETA)]
                    idx += 1

            fig_barras = px.bar(
                df_formato_largo, x="Muestra", y="Abundancia", color=nivel,
                color_discrete_map=color_map,
                title=f"Composición de la Comunidad Microbiana (Top {top_n} — {nivel.capitalize()})",
                template="plotly_white"
            )
            fig_barras.update_layout(
                barmode="stack", barnorm="percent",
                yaxis_title="Abundancia Relativa (%)", xaxis_title="Muestras Evaluadas",
                height=520, legend_title=nivel.capitalize()
            )
            
            paquete_graficos["grafico_barras_apiladas"] = json.loads(fig_barras.to_json())
            
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
                title=f"Mapa de Calor — Abundancia Core (Top {top_n})",
                xaxis_title="Muestras de Suelo",
                yaxis_title=nivel.capitalize(),
                height=max(420, top_n * 42 + 120),
                margin=dict(l=220, r=30, t=60, b=60),
                yaxis=dict(
                    tickmode="linear",
                    tick0=0,
                    dtick=1,
                    tickfont=dict(size=11),
                    automargin=True,
                ),
            )
            
            paquete_graficos["grafico_heatmap"] = json.loads(str(fig_heatmap.to_json()))
            
        except Exception as e:
            paquete_graficos["error_heatmap"] = f"Error en mapa de calor: {str(e)}"

        # -----------------------------------------------------------------
        # 3. ANÁLISIS DE COORDENADAS PRINCIPALES – PCoA (Bray-Curtis)
        # Reemplaza PCA: la distancia de Bray-Curtis es la métrica estándar
        # para beta-diversidad microbiana en ecología molecular.
        # -----------------------------------------------------------------
        try:
            n_muestras = len(columnas_muestras)
            if n_muestras >= 3:
                # Matriz abundancias: filas=taxones (todos), columnas=muestras
                matriz = df_analisis[columnas_muestras].values.T  # shape (n_muestras, n_taxones)

                # Normalizar filas para que sumen 1 (proporciones)
                sumas = matriz.sum(axis=1, keepdims=True)
                sumas[sumas == 0] = 1
                matriz_norm = matriz / sumas

                # Calcular matriz de disimilitud Bray-Curtis
                dist_matrix = np.zeros((n_muestras, n_muestras))
                for i in range(n_muestras):
                    for j in range(i + 1, n_muestras):
                        d = braycurtis(matriz_norm[i], matriz_norm[j])
                        dist_matrix[i, j] = d
                        dist_matrix[j, i] = d

                mds = MDS(n_components=2, dissimilarity='precomputed', random_state=42)
                coords = mds.fit_transform(dist_matrix)

                df_pcoa = pd.DataFrame(
                    coords, columns=['PCo1', 'PCo2'], index=columnas_muestras
                ).reset_index().rename(columns={'index': 'Muestra'})

                fig_pcoa = px.scatter(
                    df_pcoa, x='PCo1', y='PCo2', text='Muestra',
                    title='PCoA – Bray-Curtis Beta Diversidad (todos los taxones)',
                    template='plotly_white'
                )
                fig_pcoa.update_traces(
                    textposition='top center',
                    marker=dict(size=13, symbol="diamond-open", color='DarkSlateGrey')
                )
                fig_pcoa.update_layout(
                    xaxis_title="PCo1", yaxis_title="PCo2", height=500
                )

                paquete_graficos["grafico_pca"] = json.loads(str(fig_pcoa.to_json()))
            else:
                paquete_graficos["error_pca"] = "Se requieren al menos 3 muestras para PCoA (Bray-Curtis)."

        except Exception as e:
            paquete_graficos["error_pca"] = f"Error en PCoA Bray-Curtis: {str(e)}"

        return paquete_graficos