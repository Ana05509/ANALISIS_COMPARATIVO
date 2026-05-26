from django.test import TestCase, Client
import pytest
import pandas as pd
import numpy as np
from django.contrib.auth.models import User
from django.urls import reverse
from analisis.services.business.visualization_service import VisualizationService
from analisis.services.business.statistics_service import StatisticalAnalyzer
from analisis.services.business.export_service import ExportService


# ========== TESTS: visualization_service.py ==========

class TestVisualizationService(TestCase):
    """Tests para gráficos Plotly."""
    
    def setUp(self):
        """Preparar datos de prueba."""
        self.df = pd.DataFrame({
            'genus': ['Bacillus', 'Pseudomonas', 'Streptomyces', 'Actinobacteria', 'Firmicutes'],
            'total_porcentaje': [25.5, 18.3, 15.2, 12.1, 10.5],
        })
        self.viz = VisualizationService()
    
    def test_crear_grafico_abundancia_barras(self):
        """Test gráfico de barras."""
        fig = self.viz.crear_grafico_abundancia_barras(
            self.df,
            x='genus',
            y='total_porcentaje',
            titulo='Test Barras'
        )
        
        self.assertIsNotNone(fig)
        self.assertEqual(len(fig.data[0].x), 5)
    
    def test_crear_grafico_abundancia_pie(self):
        """Test gráfico de pastel."""
        fig = self.viz.crear_grafico_abundancia_pie(
            self.df,
            nombres='genus',
            valores='total_porcentaje',
            titulo='Test Pie'
        )
        
        self.assertIsNotNone(fig)
        self.assertEqual(len(fig.data[0].labels), 5)
    
    def test_crear_grafico_diversidad_linea(self):
        """Test gráfico de línea."""
        fig = self.viz.crear_grafico_diversidad_linea(
            self.df,
            x='genus',
            y='total_porcentaje',
            titulo='Test Línea'
        )
        
        self.assertIsNotNone(fig)
        self.assertGreaterEqual(len(fig.data), 1)
    
    def test_crear_grafico_comparacion_heatmap(self):
        """Test heatmap."""
        matriz = [[1, 2, 3], [4, 5, 6]]
        fig = self.viz.crear_grafico_comparacion_heatmap(
            matriz,
            etiquetas_x=['A', 'B', 'C'],
            etiquetas_y=['X', 'Y'],
            titulo='Test Heatmap'
        )
        
        self.assertIsNotNone(fig)
    
    def test_exportar_grafico_json(self):
        """Test exportación a JSON."""
        fig = self.viz.crear_grafico_abundancia_barras(
            self.df,
            x='genus',
            y='total_porcentaje'
        )
        
        json_data = self.viz.exportar_grafico_json(fig)
        self.assertIsNotNone(json_data)
        self.assertIn('data', json_data)
        self.assertIn('layout', json_data)
    
    def test_empty_dataframe(self):
        """Test con DataFrame vacío."""
        empty_df = pd.DataFrame()
        
        fig = self.viz.crear_grafico_abundancia_barras(empty_df, x='genus', y='valor')
        self.assertIsNone(fig)


# ========== TESTS: statistics_service.py ==========

class TestStatisticalAnalyzer(TestCase):
    """Tests para análisis estadístico."""
    
    def setUp(self):
        """Preparar datos de prueba."""
        self.df = pd.DataFrame({
            '%_hits': [15.5, 12.3, 18.2, 14.1, 16.5, 13.2, 17.8, 14.9],
        })
        self.analyzer = StatisticalAnalyzer()
    
    def test_calcular_descriptivas(self):
        """Test estadísticas descriptivas."""
        stats = self.analyzer.calcular_descriptivas(self.df)
        
        self.assertIsNotNone(stats)
        self.assertIn('media', stats)
        self.assertIn('mediana', stats)
        self.assertIn('desv_estandar', stats)
        self.assertGreater(stats['media'], 0)
    
    def test_test_t_independiente(self):
        """Test t-test."""
        df_a = pd.DataFrame({'%_hits': [10, 12, 14, 13, 11]})
        df_b = pd.DataFrame({'%_hits': [20, 22, 24, 23, 21]})
        
        result = self.analyzer.test_t_independiente(df_a, df_b)
        
        self.assertIsNotNone(result)
        self.assertIn('t_statistic', result)
        self.assertIn('p_value', result)
        self.assertIn('significante', result)
    
    def test_test_mann_whitney(self):
        """Test Mann-Whitney."""
        df_a = pd.DataFrame({'%_hits': [10, 12, 14, 13, 11]})
        df_b = pd.DataFrame({'%_hits': [20, 22, 24, 23, 21]})
        
        result = self.analyzer.test_mann_whitney(df_a, df_b)
        
        self.assertIsNotNone(result)
        self.assertIn('u_statistic', result)
        self.assertIn('p_value', result)
    
    def test_calcular_pca(self):
        """Test PCA."""
        df = pd.DataFrame({
            'var1': np.random.rand(20),
            'var2': np.random.rand(20),
            'var3': np.random.rand(20),
        })
        
        result = self.analyzer.calcular_pca(df, n_componentes=2)
        
        self.assertIsNotNone(result)
        self.assertIn('componentes', result)
        self.assertIn('varianza_explicada', result)
    
    def test_calcular_similitud_jaccard(self):
        """Test Jaccard."""
        set_a = {'a', 'b', 'c'}
        set_b = {'b', 'c', 'd'}
        
        jaccard = self.analyzer.calcular_similitud_jaccard(set_a, set_b)
        
        self.assertIsNotNone(jaccard)
        self.assertGreaterEqual(jaccard, 0)
        self.assertLessEqual(jaccard, 1)
    
    def test_test_normalidad_shapiro(self):
        """Test Shapiro-Wilk."""
        result = self.analyzer.test_normalidad_shapiro(self.df)
        
        self.assertIsNotNone(result)
        self.assertIn('w_statistic', result)
        self.assertIn('p_value', result)
        self.assertIn('es_normal', result)


# ========== TESTS: export_service.py ==========

class TestExportService(TestCase):
    """Tests para exportación."""
    
    def setUp(self):
        """Preparar datos de prueba."""
        self.df = pd.DataFrame({
            'genus': ['Bacillus', 'Pseudomonas', 'Streptomyces'],
            'abundancia': [25.5, 18.3, 15.2],
        })
        self.export_service = ExportService()
    
    def test_exportar_json(self):
        """Test exportación JSON."""
        json_str = self.export_service.exportar_json({'test': 'data'})
        
        self.assertIsNotNone(json_str)
        self.assertIn('test', json_str)
    
    def test_exportar_csv_avanzado(self):
        """Test exportación CSV."""
        csv_data = self.export_service.exportar_csv_avanzado(self.df)
        
        self.assertIsNotNone(csv_data)
        self.assertIn(b'genus', csv_data)
    
    def test_generar_pdf_completo(self):
        """Test generación PDF."""
        datos = {
            'Análisis': {'Media': 15.3, 'Mediana': 14.2},
        }
        
        pdf_bytes = self.export_service.generar_pdf_completo(
            titulo='Test PDF',
            datos_analisis=datos,
            df_datos=self.df
        )
        
        self.assertIsNotNone(pdf_bytes)
        self.assertGreater(len(pdf_bytes), 0)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))
    
    def test_generar_html_reporte(self):
        """Test generación HTML."""
        datos = {
            'Análisis': {'Media': 15.3, 'Mediana': 14.2},
        }
        
        html = self.export_service.generar_html_reporte(
            titulo='Test HTML',
            datos_analisis=datos,
            df_datos=self.df
        )
        
        self.assertIsNotNone(html)
        self.assertIn('<html', html)
        self.assertIn('Test HTML', html)


# ========== TESTS DE INTEGRACIÓN: VISTAS ==========

class TestDashboardView(TestCase):
    """Tests para dashboard view con Phase 2."""
    
    def setUp(self):
        """Preparar cliente y usuario."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_dashboard_accessible(self):
        """Test que dashboard es accesible."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('analisis:dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_dashboard_redirect_login(self):
        """Test que redirige a login sin autenticación."""
        response = self.client.get(reverse('analisis:dashboard'))
        self.assertEqual(response.status_code, 302)
    
    def test_dashboard_context(self):
        """Test que context contiene variables esperadas."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('analisis:dashboard'))
        
        self.assertIn('tipo_actual', response.context)
        self.assertIn('total_analisis', response.context)
        self.assertIn('total_productos', response.context)


class TestAnalysisView(TestCase):
    """Tests para analysis view."""
    
    def setUp(self):
        """Preparar cliente y usuario."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_analisis_avanzado_accessible(self):
        """Test que análisis es accesible."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('analisis:analisis_avanzado'))
        self.assertEqual(response.status_code, 200)
    
    def test_analisis_parameters(self):
        """Test que acepta parámetros."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('analisis:analisis_avanzado'),
            {'tipo': '16S', 'nivel': 'genus', 'top_n': '10'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['tipo_actual'], '16S')
        self.assertEqual(response.context['nivel'], 'genus')


class TestComparisonView(TestCase):
    """Tests para comparison view."""
    
    def setUp(self):
        """Preparar cliente y usuario."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_comparar_accessible(self):
        """Test que comparar es accesible."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('analisis:comparar'))
        self.assertEqual(response.status_code, 200)


class TestReportesView(TestCase):
    """Tests para reportes view."""
    
    def setUp(self):
        """Preparar cliente y usuario."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_reportes_accessible(self):
        """Test que reportes es accesible."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('analisis:reportes'))
        self.assertEqual(response.status_code, 200)


