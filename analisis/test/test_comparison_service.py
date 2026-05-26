"""
tests/unit/test_comparison_service.py - Unit tests for comparison services

Tests the comparison logic for microorganism profiles:
- Comparative tables
- Dominant organisms
- Shared organisms (core microbiome)
- Exclusive organisms
"""

import pytest
import pandas as pd

from analisis.services.business.comparison_service import (
    comparar_productos,
    ejecutar_comparacion_clean,
    obtener_microorganismos_compartidos,
    obtener_microorganismos_exclusivos,
)


# ═══════════════════════════════════════════════════════════════
# TESTS: comparar_productos()
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.django_db
class TestCompararProductos:
    """Tests for product comparison"""
    
    def test_comparar_productos_basico(self, resultados_16s):
        """Test basic product comparison"""
        from analisis.models import ResultadoTaxonomico
        
        analisis = ResultadoTaxonomico.objects.filter(
            archivo__muestra__archivomolecular__tipo_analisis='16S'
        )
        
        tabla = comparar_productos(analisis, nivel='genus')
        
        # Should return list of dicts
        assert isinstance(tabla, list)
        assert len(tabla) > 0
    
    def test_comparar_productos_contiene_taxonomia(self, resultados_16s):
        """Test that comparison includes taxonomic information"""
        from analisis.models import ResultadoTaxonomico
        
        analisis = ResultadoTaxonomico.objects.filter(
            archivo__muestra__archivomolecular__tipo_analisis='16S'
        )
        
        tabla = comparar_productos(analisis, nivel='genus')
        
        # Each row should have taxonomia column
        if tabla:
            assert 'taxonomia' in tabla[0]
            assert 'clasificacion' in tabla[0]
    
    def test_comparar_productos_vacio(self):
        """Test comparison with empty queryset"""
        from analisis.models import ResultadoTaxonomico
        
        analisis = ResultadoTaxonomico.objects.none()
        tabla = comparar_productos(analisis, nivel='genus')
        
        assert tabla == []


# ═══════════════════════════════════════════════════════════════
# TESTS: _calcular_diferencial()
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestCalcularDiferencial:
    """Tests for differential analysis (dominant, shared, exclusive)"""
    
    def test_dominantes_basico(self):
        """Test identifying dominant organisms"""
        from analisis.services.business.comparison_service import _calcular_diferencial
        
        # 3 muestras: Bacillus in 2/3 (>50%), Pseudomonas in 3/3, Rhizobium in 1/3
        sets = {
            'muestra1': {'Bacillus', 'Pseudomonas', 'Rhizobium'},
            'muestra2': {'Bacillus', 'Pseudomonas'},
            'muestra3': {'Pseudomonas', 'Streptomyces'},
        }
        
        dominantes, compartidos, exclusivos = _calcular_diferencial(sets)
        
        # Pseudomonas should be dominant (in all 3)
        assert 'Pseudomonas' in dominantes
    
    def test_compartidos_basico(self):
        """Test identifying shared (core) organisms"""
        from analisis.services.business.comparison_service import _calcular_diferencial
        
        sets = {
            'muestra1': {'Bacillus', 'Pseudomonas'},
            'muestra2': {'Bacillus', 'Pseudomonas'},
            'muestra3': {'Bacillus', 'Streptomyces'},
        }
        
        dominantes, compartidos, exclusivos = _calcular_diferencial(sets)
        
        # Bacillus is in all 3 (shared/core)
        assert 'Bacillus' in compartidos
    
    def test_exclusivos_basico(self):
        """Test identifying exclusive organisms"""
        from analisis.services.business.comparison_service import _calcular_diferencial
        
        sets = {
            'muestra1': {'Bacillus', 'Pseudomonas', 'Rhizobium'},
            'muestra2': {'Bacillus', 'Pseudomonas'},
            'muestra3': {'Bacillus'},
        }
        
        dominantes, compartidos, exclusivos = _calcular_diferencial(sets)
        
        # Rhizobium is only in muestra1 (exclusive)
        assert 'Rhizobium' in exclusivos
    
    def test_diferencial_una_muestra(self):
        """Test differential with only one sample"""
        from analisis.services.business.comparison_service import _calcular_diferencial
        
        sets = {'muestra1': {'Bacillus', 'Pseudomonas'}}
        
        dominantes, compartidos, exclusivos = _calcular_diferencial(sets)
        
        # Shared should be empty with only one sample
        assert compartidos == []
    
    def test_diferencial_vacio(self):
        """Test differential with empty sets"""
        from analisis.services.business.comparison_service import _calcular_diferencial
        
        sets = {}
        
        dominantes, compartidos, exclusivos = _calcular_diferencial(sets)
        
        assert dominantes == []
        assert compartidos == []
        assert exclusivos == []


# ═══════════════════════════════════════════════════════════════
# TESTS: ejecutar_comparacion_clean()
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.django_db
class TestEjecutarComparacionClean:
    """Tests for the complete comparison workflow"""
    
    def test_comparacion_sin_muestras(self):
        """Test comparison with no samples selected"""
        cleaned_data = {
            'tipo': '16S',
            'nivel': 'genus',
            'top_n': 10,
            'productos': [],
        }
        
        resultado = ejecutar_comparacion_clean(cleaned_data)
        
        # Should return empty result
        assert resultado['tabla'] == []
        assert resultado['dominantes'] == []
    
    def test_comparacion_tipo_invalido_default(self):
        """Test that invalid analysis type defaults to 16S"""
        cleaned_data = {
            'tipo': 'INVALID',
            'nivel': 'genus',
            'top_n': 10,
            'productos': [],
        }
        
        resultado = ejecutar_comparacion_clean(cleaned_data)
        assert resultado['tipo_actual'] == '16S'
    
    def test_comparacion_nivel_invalido_default(self):
        """Test that invalid level defaults to genus"""
        cleaned_data = {
            'tipo': '16S',
            'nivel': 'invalid_level',
            'top_n': 10,
            'productos': [],
        }
        
        resultado = ejecutar_comparacion_clean(cleaned_data)
        assert resultado['nivel_actual'] == 'genus'
    
    def test_comparacion_top_n_fuera_rango(self):
        """Test that top_n outside valid range is handled"""
        cleaned_data = {
            'tipo': '16S',
            'nivel': 'genus',
            'top_n': 999,  # Invalid option
            'productos': [],
        }
        
        resultado = ejecutar_comparacion_clean(cleaned_data)
        assert resultado['top_actual'] == 10  # Default


# ═══════════════════════════════════════════════════════════════
# TESTS: obtener_microorganismos_compartidos()
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.django_db
class TestObtenerMicroorganismosCompartidos:
    """Tests for shared microorganism identification"""
    
    def test_compartidos_con_dos_muestras(self, muestra, variedad, cultivo):
        """Test identifying shared organisms with multiple samples"""
        from analisis.models import ResultadoTaxonomico
        
        # Create two samples with shared genera
        muestra2 = pytest.importorskip('conftest').MuestraSueloFactory(
            cultivo=cultivo,
            variedad_clon=variedad,
            codigo='MUESTRA-2'
        )
        
        archivo1 = pytest.importorskip('conftest').ArchivoMolecularFactory(
            muestra=muestra,
            tipo_analisis='16S'
        )
        archivo2 = pytest.importorskip('conftest').ArchivoMolecularFactory(
            muestra=muestra2,
            tipo_analisis='16S'
        )
        
        # Shared genus
        ResultadoTaxonomico.objects.create(
            archivo=archivo1, kingdom='Bacteria', phylum='P1',
            tax_class='C1', order='O1', family='F1',
            genus='Bacillus', species='s1', num_hits=100
        )
        ResultadoTaxonomico.objects.create(
            archivo=archivo2, kingdom='Bacteria', phylum='P1',
            tax_class='C1', order='O1', family='F1',
            genus='Bacillus', species='s1', num_hits=100
        )
        
        # Exclusive genus (only in muestra1)
        ResultadoTaxonomico.objects.create(
            archivo=archivo1, kingdom='Bacteria', phylum='P1',
            tax_class='C1', order='O1', family='F1',
            genus='Pseudomonas', species='s1', num_hits=50
        )
        
        compartidos = obtener_microorganismos_compartidos(tipo='16S', variedad_id=variedad.id)
        
        # Bacillus should be shared
        assert 'Bacillus' in compartidos
        # Pseudomonas should NOT be shared
        assert 'Pseudomonas' not in compartidos


# ═══════════════════════════════════════════════════════════════
# TESTS: obtener_microorganismos_exclusivos()
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.django_db
class TestObtenerMicroorganismosExclusivos:
    """Tests for exclusive microorganism identification"""
    
    def test_exclusivos_de_variedad(self, muestra, variedad, cultivo):
        """Test identifying organisms exclusive to a variety"""
        from analisis.models import ResultadoTaxonomico
        
        # Create a different variety
        otra_variedad = pytest.importorskip('conftest').VariedadClonFactory(
            cultivo=cultivo,
            nombre='OtraVariedad'
        )
        
        otra_muestra = pytest.importorskip('conftest').MuestraSueloFactory(
            cultivo=cultivo,
            variedad_clon=otra_variedad,
            codigo='MUESTRA-OTRA'
        )
        
        archivo1 = pytest.importorskip('conftest').ArchivoMolecularFactory(
            muestra=muestra,
            tipo_analisis='16S'
        )
        archivo2 = pytest.importorskip('conftest').ArchivoMolecularFactory(
            muestra=otra_muestra,
            tipo_analisis='16S'
        )
        
        # Exclusive to variedad1
        ResultadoTaxonomico.objects.create(
            archivo=archivo1, kingdom='Bacteria', phylum='P1',
            tax_class='C1', order='O1', family='F1',
            genus='ExclusiveGenus', species='s1', num_hits=100
        )
        
        # Common genus
        ResultadoTaxonomico.objects.create(
            archivo=archivo1, kingdom='Bacteria', phylum='P1',
            tax_class='C1', order='O1', family='F1',
            genus='CommonGenus', species='s1', num_hits=100
        )
        ResultadoTaxonomico.objects.create(
            archivo=archivo2, kingdom='Bacteria', phylum='P1',
            tax_class='C1', order='O1', family='F1',
            genus='CommonGenus', species='s1', num_hits=100
        )
        
        exclusivos = obtener_microorganismos_exclusivos(tipo='16S', variedad_id=variedad.id)
        
        # ExclusiveGenus should be exclusive
        assert 'ExclusiveGenus' in exclusivos
        # CommonGenus should NOT be exclusive
        assert 'CommonGenus' not in exclusivos
