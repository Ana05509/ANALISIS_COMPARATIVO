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
            fig.update_layout(
                xaxis=dict(tickangle=-45, automargin=True, tickfont=dict(size=10)),
                margin=dict(b=160, t=60, l=60, r=20),
                height=500,
            )
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
                xaxis=dict(tickangle=-45, automargin=True, tickfont=dict(size=10)),
                margin=dict(b=160, t=60, l=60, r=20),
            )
            return str(fig.to_json())
        except Exception as e:
            print(f"Error en gráfico comparativo: {e}")
            return None

    @staticmethod
    def obtener_paquete_graficos_avanzados(df_pivote: pd.DataFrame, columnas_muestras: List[str], nivel: str, top_n: int = 10,
                                            orden_taxa: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Coordinador analítico: Procesa el DataFrame de abundancias microbianas según el Top N elegido.
        Retorna un diccionario estructurado con objetos JSON (dict) listos para el frontend.

        `orden_taxa`: lista opcional de nombres de taxón, ya ordenada de mayor a
        menor abundancia con el MISMO criterio que la tabla "Top N" de la misma
        página (hits acumulados/pooled). Si se pasa, las gráficas usan ese orden
        para elegir el Top N en vez de calcular uno propio por promedio de
        porcentajes — así la tabla y las gráficas siempre muestran los mismos
        taxa. Si no se pasa, se conserva el criterio de promedio (compatibilidad).
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

        if orden_taxa:
            # Mismo orden que la tabla Top N (hits acumulados/pooled) — se
            # reindexa en vez de recalcular un criterio de orden propio.
            orden_presente = [t for t in orden_taxa if t in set(df_analisis[nivel])]
            df_analisis = df_analisis.set_index(nivel).reindex(orden_presente).reset_index()
        else:
            # Compatibilidad: sin orden explícito, se ordena por promedio de
            # abundancia relativa entre las muestras seleccionadas.
            df_analisis['__promedio_abundancia'] = df_analisis[columnas_muestras].mean(axis=1)
            df_analisis = df_analisis.sort_values(by='__promedio_abundancia', ascending=False)
        df_ordenado = df_analisis

        # -----------------------------------------------------------------
        # 1. GRÁFICO DE BARRAS APILADAS AL 100%
        # -----------------------------------------------------------------
        try:
            df_top = df_ordenado.head(top_n).copy()
            df_resto = df_ordenado.iloc[top_n:]

            n_otros = len(df_resto)
            if not df_resto.empty:
                label_otros = f"Otros ({n_otros} taxa agrupados)"
                fila_otros = {nivel: label_otros}
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
                    color_map[taxon] = '#B0B8C1'
                else:
                    color_map[taxon] = PALETA[idx % len(PALETA)]
                    idx += 1

            # Margen derecho adaptativo según longitud del nombre más largo en la leyenda
            max_len = max((len(str(t)) for t in taxa_ordenados), default=10)
            r_margin = max(min(max_len * 6 + 50, 300), 140)

            fig_barras = px.bar(
                df_formato_largo, x="Muestra", y="Abundancia", color=nivel,
                color_discrete_map=color_map,
                title=f"Top {top_n} {nivel.capitalize()} — Abundancia Relativa por Muestra (%)",
                template="plotly_white",
            )
            fig_barras.update_traces(
                # El % de cada segmento se ve al pasar el cursor, no como texto
                # fijo sobre la barra — con varias muestras, cada taxón tiene un
                # valor distinto por muestra y no cabe legible ahí.
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>"
                    "Muestra: %{x}<br>"
                    "Abundancia: <b>%{y:.2f} %</b>"
                    "<extra></extra>"
                ),
            )
            fig_barras.update_layout(
                barmode="stack", barnorm="percent",
                yaxis=dict(title="Abundancia Relativa (%)", range=[0, 103]),
                xaxis=dict(title="Muestras Evaluadas", automargin=True, tickfont=dict(size=11)),
                height=540,
                legend=dict(
                    title=dict(text=nivel.capitalize(), font=dict(size=11)),
                    orientation='v',
                    x=1.01, y=1,
                    xanchor='left', yanchor='top',
                    bgcolor='rgba(255,255,255,0.9)',
                    bordercolor='rgba(200,200,200,0.5)',
                    borderwidth=1,
                    font=dict(size=10),
                    itemsizing='constant',
                ),
                margin=dict(b=80, t=60, l=60, r=r_margin),
            )
            
            paquete_graficos["grafico_barras_apiladas"] = json.loads(fig_barras.to_json() or "{}")
            
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
        # -----------------------------------------------------------------
        try:
            n_muestras = len(columnas_muestras)
            if n_muestras >= 3:
                matriz = df_analisis[columnas_muestras].values.T
                sumas = matriz.sum(axis=1, keepdims=True)
                sumas[sumas == 0] = 1
                matriz_norm = matriz / sumas

                dist_matrix = np.zeros((n_muestras, n_muestras))
                for i in range(n_muestras):
                    for j in range(i + 1, n_muestras):
                        d = braycurtis(matriz_norm[i], matriz_norm[j])
                        dist_matrix[i, j] = d
                        dist_matrix[j, i] = d

                mds = MDS(n_components=2, dissimilarity='precomputed', random_state=42)
                coords = mds.fit_transform(dist_matrix)

                # Centroide y distancias al centroide
                cx = float(np.mean(coords[:, 0]))
                cy = float(np.mean(coords[:, 1]))
                dist_cent = np.sqrt((coords[:, 0] - cx) ** 2 + (coords[:, 1] - cy) ** 2)

                # Calidad del estrés MDS
                stress = round(float(mds.stress_), 4)
                stress_label = (
                    "Excelente" if stress < 0.05 else
                    "Bueno"     if stress < 0.10 else
                    "Aceptable" if stress < 0.20 else
                    "Pobre"
                )

                # Hover enriquecido con disimilitudes Bray-Curtis reales
                hover_texts = []
                for i, m_i in enumerate(columnas_muestras):
                    bc_lines = "<br>".join(
                        f"&nbsp;&nbsp;vs {columnas_muestras[j]}: {dist_matrix[i, j]:.3f}"
                        for j in range(n_muestras) if i != j
                    )
                    hover_texts.append(
                        f"<b>{m_i}</b><br>"
                        f"PCo1: {coords[i, 0]:.4f}  |  PCo2: {coords[i, 1]:.4f}<br>"
                        f"Dist. al centroide: {dist_cent[i]:.4f}<br>"
                        f"── Bray-Curtis ──<br>{bc_lines}"
                    )

                PALETTE_PCOA = [
                    '#1D9E75', '#E07B39', '#264653', '#9B2226', '#457B9D',
                    '#E9C46A', '#6D6875', '#FFBA08', '#3A86FF', '#8338EC',
                    '#FB5607', '#2A9D8F', '#B5838D', '#F4A261', '#A8DADC',
                ]
                colors_pcoa = [PALETTE_PCOA[i % len(PALETTE_PCOA)] for i in range(n_muestras)]

                fig_pcoa = go.Figure()

                # Líneas de referencia en el origen (cuadrantes)
                fig_pcoa.add_hline(y=0, line=dict(dash='dot', color='rgba(160,160,160,0.35)', width=1))
                fig_pcoa.add_vline(x=0, line=dict(dash='dot', color='rgba(160,160,160,0.35)', width=1))

                # Centroide de la comunidad
                fig_pcoa.add_trace(go.Scatter(
                    x=[cx], y=[cy],
                    mode='markers',
                    name='Centroide',
                    marker=dict(size=12, color='rgba(100,100,100,0.55)',
                                symbol='cross', line=dict(color='#555', width=2)),
                    hovertemplate=f"<b>Centroide</b><br>PCo1: {cx:.4f}<br>PCo2: {cy:.4f}<extra></extra>",
                    showlegend=True,
                ))

                # Un trace por muestra → color + leyenda individuales
                for i, muestra_i in enumerate(columnas_muestras):
                    fig_pcoa.add_trace(go.Scatter(
                        x=[coords[i, 0]],
                        y=[coords[i, 1]],
                        mode='markers+text',
                        name=muestra_i,
                        text=[muestra_i],
                        textposition='top center',
                        textfont=dict(size=11, color=colors_pcoa[i]),
                        marker=dict(
                            size=18,
                            color=colors_pcoa[i],
                            line=dict(color='white', width=2),
                            symbol='circle',
                        ),
                        customdata=[[hover_texts[i]]],
                        hovertemplate='%{customdata[0]}<extra></extra>',
                        showlegend=True,
                    ))

                fig_pcoa.update_layout(
                    title=dict(text='PCoA — Disimilitud Bray-Curtis', font=dict(size=14),
                               x=0.5, xanchor='center'),
                    xaxis=dict(title='Coordenada Principal 1 (PCo1) — eje sin unidad física', zeroline=False,
                               gridcolor='#c8c8c8', automargin=True),
                    yaxis=dict(title='Coordenada Principal 2 (PCo2) — eje sin unidad física', zeroline=False,
                               gridcolor='#c8c8c8', automargin=True),
                    template='plotly_white',
                    height=560,
                    legend=dict(
                        title=dict(text='Muestras', font=dict(size=11)),
                        orientation='v', x=1.02, y=1,
                        bgcolor='rgba(255,255,255,0.9)',
                        bordercolor='rgba(200,200,200,0.6)', borderwidth=1,
                    ),
                    margin=dict(b=60, t=80, l=60, r=170),
                    annotations=[dict(
                        x=0.0, y=-0.07,
                        xref='paper', yref='paper',
                        text=(f"Estrés MDS: <b>{stress}</b> ({stress_label})"
                              f"  ·  < 0.10 = representación confiable  ·  "
                              f"< 0.20 = aceptable"),
                        showarrow=False,
                        font=dict(size=9, color='gray'),
                        align='left',
                    )],
                )

                paquete_graficos["grafico_pca"] = json.loads(str(fig_pcoa.to_json()))
            else:
                paquete_graficos["error_pca"] = "Se requieren al menos 3 muestras para PCoA (Bray-Curtis)."

        except Exception as e:
            paquete_graficos["error_pca"] = f"Error en PCoA Bray-Curtis: {str(e)}"

        return paquete_graficos