"""
tests/unit/test_pipeline.py - Unit tests for the data processing pipeline

Tests the core pipeline logic for:
- Data loading (CSV, Excel)
- Column validation
- Data cleaning and normalization
- Top N filtering
"""

import pytest
import pandas as pd
import numpy as np
from io import StringIO

from analisis.services.processing.pipeline import (
    cargar_archivo,
    validar_columnas,
    limpiar_datos,
    procesar_archivo_df,
    procesar_archivo,
)


# ═══════════════════════════════════════════════════════════════
# TESTS: cargar_archivo()
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestCargarArchivo:
    """Tests for file loading functionality"""
    
    def test_cargar_csv_basico(self, sample_csv_file):
        """Test loading a basic CSV file"""
        df = cargar_archivo(sample_csv_file)
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert 'kingdom' in df.columns
    
    def test_cargar_excel_basico(self, sample_excel_file):
        """Test loading an Excel file"""
        df = cargar_archivo(sample_excel_file)
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert 'kingdom' in df.columns
    
    def test_cargar_archivo_invalido(self, tmp_path):
        """Test loading an invalid file format"""
        invalid_file = tmp_path / "test.txt"
        invalid_file.write_text("invalid content")
        
        with pytest.raises(ValueError, match="Formato no soportado"):
            cargar_archivo(str(invalid_file))
    
    def test_cargar_convierte_columnas_minusculas(self, sample_csv_file):
        """Test that column names are converted to lowercase"""
        df = cargar_archivo(sample_csv_file)
        
        for col in df.columns:
            assert col == col.lower()


# ═══════════════════════════════════════════════════════════════
# TESTS: validar_columnas()
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestValidarColumnas:
    """Tests for column validation"""
    
    def test_validar_columnas_validas(self, sample_dataframe):
        """Test validation passes with all required columns"""
        # Should not raise
        validar_columnas(sample_dataframe)
    
    def test_validar_columnas_faltantes(self):
        """Test validation fails when required columns are missing"""
        df = pd.DataFrame({'kingdom': ['Bacteria']})
        
        with pytest.raises(ValueError, match="Faltan columnas requeridas"):
            validar_columnas(df)
    
    def test_validar_columnas_parciales(self):
        """Test validation fails with partial columns"""
        df = pd.DataFrame({
            'kingdom': ['Bacteria'],
            'phylum': ['Proteobacteria'],
            'num_hits': [100],
            # Missing others
        })
        
        with pytest.raises(ValueError, match="Faltan columnas requeridas"):
            validar_columnas(df)


# ═══════════════════════════════════════════════════════════════
# TESTS: limpiar_datos()
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestLimpiarDatos:
    """Tests for data cleaning functionality"""
    
    def test_limpiar_espacios_en_blanco(self):
        """Test that leading/trailing whitespace is removed"""
        df = pd.DataFrame({
            'kingdom': [' Bacteria ', 'Archaea '],
            'phylum': ['Proteobacteria', ' Euryarchaeota'],
            'class': ['Gamma', 'Methanobacteria'],
            'order': ['Enterobacteriales', 'Methanobacteriales'],
            'family': ['Enterobacteriaceae', 'Methanobacteriaceae'],
            'genus': ['Bacillus', 'Methanobacterium'],
            'species': ['subtilis', 'formicicum'],
            'num_hits': [100, 200],
            '%_hits': [50.0, 50.0],
        })
        
        cleaned = limpiar_datos(df)
        
        assert cleaned['kingdom'].iloc[0] == 'Bacteria'
        assert cleaned['phylum'].iloc[1] == 'Euryarchaeota'
    
    def test_limpiar_valores_nulos(self):
        """Test that null values are replaced with 'Unclassified'"""
        df = pd.DataFrame({
            'kingdom': ['Bacteria', None],
            'phylum': ['Proteobacteria', 'NaN'],
            'class': ['Gamma', ''],
            'order': ['Enterobacteriales', 'nan'],
            'family': ['Enterobacteriaceae', 'None'],
            'genus': ['Bacillus', 'Unknown'],
            'species': ['subtilis', 'sp.'],
            'num_hits': [100, np.nan],
            '%_hits': [50.0, 0.0],
        })
        
        cleaned = limpiar_datos(df)
        
        assert cleaned['kingdom'].iloc[1] == 'Unclassified'
        assert cleaned['phylum'].iloc[1] == 'Unclassified'
        assert cleaned['class'].iloc[1] == 'Unclassified'
        assert cleaned['order'].iloc[1] == 'Unclassified'
    
    def test_limpiar_convierte_numericos(self):
        """Test that numeric columns are converted to proper types"""
        df = pd.DataFrame({
            'kingdom': ['Bacteria'],
            'phylum': ['Proteobacteria'],
            'class': ['Gamma'],
            'order': ['Enterobacteriales'],
            'family': ['Enterobacteriaceae'],
            'genus': ['Bacillus'],
            'species': ['subtilis'],
            'num_hits': ['100'],  # String that should become int
            '%_hits': ['50,5'],   # European decimal should become float
        })
        
        cleaned = limpiar_datos(df)
        
        assert cleaned['num_hits'].dtype == np.int64
        assert cleaned['%_hits'].dtype == float
        assert cleaned['num_hits'].iloc[0] == 100
        assert abs(cleaned['%_hits'].iloc[0] - 50.5) < 0.01
    
    def test_limpiar_normaliza_species(self):
        """Test that species names are normalized"""
        df = pd.DataFrame({
            'kingdom': ['Bacteria'],
            'phylum': ['Proteobacteria'],
            'class': ['Gamma'],
            'order': ['Enterobacteriales'],
            'family': ['Enterobacteriaceae'],
            'genus': ['Bacillus'],
            'species': ['subtilis (strain 168)'],
            'num_hits': [100],
            '%_hits': [50.0],
        })
        
        cleaned = limpiar_datos(df)
        
        # Should remove parentheses
        assert '(' not in cleaned['species'].iloc[0]
        assert 'strain' not in cleaned['species'].iloc[0]


# ═══════════════════════════════════════════════════════════════
# TESTS: procesar_archivo_df()
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestProcesarArchivoDf:
    """Tests for the complete pipeline processing"""
    
    def test_procesar_archivo_df_basico(self, sample_dataframe):
        """Test basic pipeline processing"""
        resultado = procesar_archivo_df(sample_dataframe, top_n=10, nivel='genus')
        
        assert 'data' in resultado
        assert 'total_registros' in resultado
        assert 'nivel' in resultado
        assert 'top_n' in resultado
        
        assert resultado['total_registros'] == 3
        assert resultado['nivel'] == 'genus'
        assert resultado['top_n'] == 10
    
    def test_procesar_archivo_df_top_n(self, sample_dataframe):
        """Test top N filtering"""
        resultado = procesar_archivo_df(sample_dataframe, top_n=2, nivel='genus')
        
        # Should only return top 2 by abundance
        assert len(resultado['data']) == 2
        
        # First should have highest abundance
        assert resultado['data'][0]['%_hits'] >= resultado['data'][1]['%_hits']
    
    def test_procesar_archivo_df_preserva_taxonomia(self, sample_dataframe):
        """Test that all taxonomic levels are preserved"""
        resultado = procesar_archivo_df(sample_dataframe, top_n=10, nivel='genus')
        
        for registro in resultado['data']:
            assert 'kingdom' in registro
            assert 'phylum' in registro
            assert 'class' in registro
            assert 'order' in registro
            assert 'family' in registro
            assert 'genus' in registro
            assert 'species' in registro
    
    def test_procesar_archivo_df_niveles_validos(self, sample_dataframe):
        """Test different taxonomic levels"""
        for level in ['kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species']:
            resultado = procesar_archivo_df(sample_dataframe, top_n=10, nivel=level)
            assert resultado['nivel'] == level
    
    def test_procesar_archivo_df_nivel_invalido_default(self, sample_dataframe):
        """Test that invalid level defaults to genus"""
        resultado = procesar_archivo_df(sample_dataframe, top_n=10, nivel='invalid_level')
        assert resultado['nivel'] == 'genus'
    
    def test_procesar_archivo_df_top_n_opciones_validas(self, sample_dataframe):
        """Test that only valid top_n options are allowed"""
        for top_n in [5, 10, 25, 50]:
            resultado = procesar_archivo_df(sample_dataframe, top_n=top_n, nivel='genus')
            assert resultado['top_n'] == top_n
        
        # Invalid option should default to 10
        resultado = procesar_archivo_df(sample_dataframe, top_n=100, nivel='genus')
        assert resultado['top_n'] == 10
    
    def test_procesar_archivo_df_numeros_validos(self, sample_dataframe):
        """Test that numeric values are properly formatted"""
        resultado = procesar_archivo_df(sample_dataframe, top_n=10, nivel='genus')
        
        for registro in resultado['data']:
            assert isinstance(registro['num_hits'], int)
            assert isinstance(registro['%_hits'], float)
            assert registro['num_hits'] >= 0
            assert 0 <= registro['%_hits'] <= 100


# ═══════════════════════════════════════════════════════════════
# TESTS: procesar_archivo()
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestProcesarArchivo:
    """Tests for file-based processing"""
    
    def test_procesar_archivo_csv(self, sample_csv_file):
        """Test processing a CSV file end-to-end"""
        resultado = procesar_archivo(sample_csv_file, top_n=10, nivel='genus')
        
        assert 'data' in resultado
        assert resultado['total_registros'] == 3
    
    def test_procesar_archivo_excel(self, sample_excel_file):
        """Test processing an Excel file end-to-end"""
        resultado = procesar_archivo(sample_excel_file, top_n=10, nivel='genus')
        
        assert 'data' in resultado
        assert resultado['total_registros'] == 3


# ═══════════════════════════════════════════════════════════════
# TESTS: Edge Cases & Error Handling
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases and error handling"""
    
    def test_procesar_dataframe_vacio(self):
        """Test processing an empty DataFrame"""
        df = pd.DataFrame(columns=['kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species', 'num_hits', '%_hits'])
        
        # Should handle gracefully
        resultado = procesar_archivo_df(df, top_n=10, nivel='genus')
        assert len(resultado['data']) == 0
    
    def test_procesar_un_solo_registro(self):
        """Test processing with only one record"""
        df = pd.DataFrame({
            'kingdom': ['Bacteria'],
            'phylum': ['Proteobacteria'],
            'class': ['Gamma'],
            'order': ['Enterobacteriales'],
            'family': ['Enterobacteriaceae'],
            'genus': ['Bacillus'],
            'species': ['subtilis'],
            'num_hits': [100],
            '%_hits': [100.0],
        })
        
        resultado = procesar_archivo_df(df, top_n=10, nivel='genus')
        assert len(resultado['data']) == 1
    
    def test_procesar_con_valores_nan(self):
        """Test processing with NaN values"""
        df = pd.DataFrame({
            'kingdom': ['Bacteria', 'Bacteria'],
            'phylum': ['Proteobacteria', np.nan],
            'class': ['Gamma', 'Gamma'],
            'order': ['Enterobacteriales', 'Enterobacteriales'],
            'family': ['Enterobacteriaceae', 'Enterobacteriaceae'],
            'genus': ['Bacillus', 'Pseudomonas'],
            'species': ['subtilis', np.nan],
            'num_hits': [100, 200],
            '%_hits': [50.0, 50.0],
        })
        
        resultado = procesar_archivo_df(df, top_n=10, nivel='genus')
        
        # Should not raise and should handle NaN gracefully
        assert len(resultado['data']) == 2
        assert resultado['data'][1]['phylum'] == 'Unclassified'
