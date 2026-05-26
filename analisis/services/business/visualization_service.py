# analisis/services/business/visualization_service.py

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class VisualizationService:
    """
    Servicio de visualización avanzada con Plotly.
    """

    @staticmethod
    def crear_grafico_abundancia_barras(
        data: pd.DataFrame,
        x: str,
        y: str,
        titulo: str = "Abundancia por Categoría",
        color: Optional[str] = None,
    ):
        """
        Crear gráfico de barras para abundancia.
        """

        fig = px.bar(
            data,
            x=x,
            y=y,
            color=color,
            title=titulo,
            template="plotly_white",
        )

        fig.update_layout(
            xaxis_title=x,
            yaxis_title=y,
            height=500,
        )

        return fig

    @staticmethod
    def crear_grafico_abundancia_pie(
        data: pd.DataFrame,
        nombres: str,
        valores: str,
        titulo: str = "Distribución de Abundancia",
    ):
        """
        Crear gráfico circular.
        """

        fig = px.pie(
            data,
            names=nombres,
            values=valores,
            title=titulo,
            hole=0.3,
        )

        fig.update_traces(textposition="inside", textinfo="percent+label")

        return fig

    @staticmethod
    def crear_grafico_diversidad_linea(
        data: pd.DataFrame,
        x: str,
        y: str,
        titulo: str = "Índice de Diversidad",
        color: Optional[str] = None,
    ):
        """
        Crear gráfico de líneas.
        """

        fig = px.line(
            data,
            x=x,
            y=y,
            color=color,
            markers=True,
            title=titulo,
            template="plotly_white",
        )

        fig.update_layout(
            height=500,
            xaxis_title=x,
            yaxis_title=y,
        )

        return fig

    @staticmethod
    def crear_grafico_comparacion_heatmap(
        matriz,
        etiquetas_x: List[str],
        etiquetas_y: List[str],
        titulo: str = "Mapa de Calor Comparativo",
    ):
        """
        Crear heatmap comparativo.
        """

        fig = go.Figure(
            data=go.Heatmap(
                z=matriz,
                x=etiquetas_x,
                y=etiquetas_y,
                colorscale="Viridis",
                colorbar=dict(title="Valor"),
            )
        )

        fig.update_layout(
            title=titulo,
            height=600,
        )

        return fig

    @staticmethod
    def crear_diagrama_venn(
        conjunto_a: int,
        conjunto_b: int,
        interseccion: int,
        titulo: str = "Diagrama de Venn",
    ):
        """
        Simulación simple de diagrama Venn con shapes.
        """

        fig = go.Figure()

        fig.add_shape(
            type="circle",
            x0=0,
            y0=0,
            x1=2,
            y1=2,
            fillcolor="blue",
            opacity=0.4,
            line_color="blue",
        )

        fig.add_shape(
            type="circle",
            x0=1,
            y0=0,
            x1=3,
            y1=2,
            fillcolor="red",
            opacity=0.4,
            line_color="red",
        )

        fig.add_annotation(x=0.7, y=1, text=str(conjunto_a))
        fig.add_annotation(x=1.5, y=1, text=str(interseccion))
        fig.add_annotation(x=2.3, y=1, text=str(conjunto_b))

        fig.update_layout(
            title=titulo,
            showlegend=False,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            height=500,
        )

        return fig

    @staticmethod
    def crear_dashboard_metricas(
        metricas: Dict[str, float],
        titulo: str = "Dashboard de Métricas",
    ):
        """
        Crear dashboard KPI.
        """

        fig = make_subplots(
            rows=1,
            cols=len(metricas),
            specs=[{"type": "indicator"}] * len(metricas),
        )

        for idx, (nombre, valor) in enumerate(metricas.items(), start=1):
            fig.add_trace(
                go.Indicator(
                    mode="number",
                    value=valor,
                    title={"text": nombre},
                ),
                row=1,
                col=idx,
            )

        fig.update_layout(
            title=titulo,
            height=300,
        )

        return fig

    @staticmethod
    def exportar_grafico_html(
        fig,
        ruta_salida: str,
    ):
        """
        Exportar gráfico interactivo HTML.
        """

        ruta = Path(ruta_salida)
        ruta.parent.mkdir(parents=True, exist_ok=True)

        fig.write_html(str(ruta))

        return ruta

    @staticmethod
    def exportar_grafico_imagen(
        fig,
        ruta_salida: str,
        ancho: int = 1200,
        alto: int = 800,
        escala: int = 2,
    ):
        """
        Exportar gráfico como PNG/JPG/SVG/PDF.
        Requiere kaleido.
        """

        ruta = Path(ruta_salida)
        ruta.parent.mkdir(parents=True, exist_ok=True)

        fig.write_image(
            str(ruta),
            width=ancho,
            height=alto,
            scale=escala,
        )

        return ruta 