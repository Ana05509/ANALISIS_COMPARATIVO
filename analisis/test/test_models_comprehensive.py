"""
tests/unit/test_models.py - Unit tests for Django models

Tests model creation, validation, relationships, and constraints
"""

import pytest
from django.db import IntegrityError

from analisis.models import (
    Cultivo, VariedadClon, MuestraSuelo, ArchivoMolecular,
    ResultadoTaxonomico, CatalogoMicroorganismo, Usuario
)


# ═══════════════════════════════════════════════════════════════
# TESTS: Cultivo Model
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.django_db
class TestCultivoModel:
    """Tests for Cultivo model"""
    
    def test_crear_cultivo_basico(self):
        """Test creating a basic crop"""
        cultivo = Cultivo.objects.create(
            nombre='Cacao',
            descripcion='Árbol de cacao ecuatoriano'
        )
        
        assert cultivo.nombre == 'Cacao'
        assert cultivo.descripcion == 'Árbol de cacao ecuatoriano'
        assert Cultivo.objects.count() == 1
    
    def test_cultivo_nombre_unico(self):
        """Test that crop names must be unique"""
        Cultivo.objects.create(nombre='Cacao')
        
        with pytest.raises(IntegrityError):
            Cultivo.objects.create(nombre='Cacao')
    
    def test_cultivo_str(self):
        """Test Cultivo string representation"""
        cultivo = Cultivo.objects.create(nombre='Café')
        assert str(cultivo) == 'Café'


# ═══════════════════════════════════════════════════════════════
# TESTS: VariedadClon Model
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.django_db
class TestVariedadClonModel:
    """Tests for VariedadClon model"""
    
    def test_crear_variedad(self, cultivo):
        """Test creating a variety/clone"""
        variedad = VariedadClon.objects.create(
            cultivo=cultivo,
            nombre='CCN51',
            descripcion='Clon de cacao fino'
        )
        
        assert variedad.cultivo == cultivo
        assert variedad.nombre == 'CCN51'
        assert VariedadClon.objects.count() == 1
    
    def test_variedad_relacion_cultivo(self, cultivo):
        """Test relationship with Cultivo"""
        variedad = VariedadClon.objects.create(cultivo=cultivo, nombre='CCN51')
        
        assert cultivo.variedadclon_set.count() == 1
        assert cultivo.variedadclon_set.first() == variedad
    
    def test_variedad_unique_together(self, cultivo):
        """Test that (cultivo, nombre) is unique together"""
        VariedadClon.objects.create(cultivo=cultivo, nombre='CCN51')
        
        # Same variety name in same crop should fail
        with pytest.raises(IntegrityError):
            VariedadClon.objects.create(cultivo=cultivo, nombre='CCN51')
    
    def test_variedad_mismo_nombre_distinto_cultivo(self, cultivo):
        """Test that same variety name in different crops is allowed"""
        otro_cultivo = Cultivo.objects.create(nombre='Café')
        
        VariedadClon.objects.create(cultivo=cultivo, nombre='Variedad1')
        VariedadClon.objects.create(cultivo=otro_cultivo, nombre='Variedad1')
        
        assert VariedadClon.objects.count() == 2


# ═══════════════════════════════════════════════════════════════
# TESTS: MuestraSuelo Model
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.django_db
class TestMuestraSueloModel:
    """Tests for MuestraSuelo model"""
    
    def test_crear_muestra(self, cultivo, variedad):
        """Test creating a soil sample"""
        muestra = MuestraSuelo.objects.create(
            codigo='MUESTRA-001',
            cultivo=cultivo,
            variedad_clon=variedad,
            tipo_muestra='Suelo'
        )
        
        assert muestra.codigo == 'MUESTRA-001'
        assert muestra.cultivo == cultivo
        assert muestra.variedad_clon == variedad
    
    def test_muestra_sin_variedad(self, cultivo):
        """Test creating sample without variety (nullable field)"""
        muestra = MuestraSuelo.objects.create(
            codigo='MUESTRA-002',
            cultivo=cultivo,
            tipo_muestra='Suelo'
        )
        
        assert muestra.variedad_clon is None
        assert muestra.codigo == 'MUESTRA-002'
    
    def test_muestra_cultivo_required(self):
        """Test that cultivo is required"""
        with pytest.raises(IntegrityError):
            MuestraSuelo.objects.create(
                codigo='MUESTRA-003',
                tipo_muestra='Suelo'
            )
    
    def test_muestra_fecha_registro_auto(self, cultivo):
        """Test that fecha_registro is auto-set"""
        muestra = MuestraSuelo.objects.create(
            codigo='MUESTRA-004',
            cultivo=cultivo
        )
        
        assert muestra.fecha_registro is not None


# ═══════════════════════════════════════════════════════════════
# TESTS: ArchivoMolecular Model
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.django_db
class TestArchivoMolecularModel:
    """Tests for ArchivoMolecular model"""
    
    def test_crear_archivo_16s(self, muestra):
        """Test creating a 16S analysis file"""
        archivo = ArchivoMolecular.objects.create(
            muestra=muestra,
            tipo_analisis='16S',
            archivo='archivos/16s_sample.csv'
        )
        
        assert archivo.tipo_analisis == '16S'
        assert archivo.muestra == muestra
    
    def test_crear_archivo_its(self, muestra):
        """Test creating an ITS analysis file"""
        archivo = ArchivoMolecular.objects.create(
            muestra=muestra,
            tipo_analisis='ITS',
            archivo='archivos/its_sample.csv'
        )
        
        assert archivo.tipo_analisis == 'ITS'
    
    def test_archivo_tipos_analisis_validos(self, muestra):
        """Test that only valid analysis types are allowed"""
        # Valid types
        ArchivoMolecular.objects.create(
            muestra=muestra,
            tipo_analisis='16S',
            archivo='test.csv'
        )
        ArchivoMolecular.objects.create(
            muestra=muestra,
            tipo_analisis='ITS',
            archivo='test.csv'
        )
        
        assert ArchivoMolecular.objects.count() == 2


# ═══════════════════════════════════════════════════════════════
# TESTS: ResultadoTaxonomico Model
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.django_db
class TestResultadoTaxonomicoModel:
    """Tests for ResultadoTaxonomico model"""
    
    def test_crear_resultado_taxonomico(self, archivo_16s):
        """Test creating a taxonomic result"""
        resultado = ResultadoTaxonomico.objects.create(
            archivo=archivo_16s,
            kingdom='Bacteria',
            phylum='Proteobacteria',
            tax_class='Gammaproteobacteria',
            order='Enterobacteriales',
            family='Enterobacteriaceae',
            genus='Bacillus',
            species='subtilis',
            num_hits=100,
            porcentaje_hits=50.0
        )
        
        assert resultado.genus == 'Bacillus'
        assert resultado.num_hits == 100
        assert resultado.porcentaje_hits == 50.0
    
    def test_resultado_valores_default(self, archivo_16s):
        """Test default values for numeric fields"""
        resultado = ResultadoTaxonomico.objects.create(
            archivo=archivo_16s,
            kingdom='Bacteria',
            phylum='Proteobacteria',
            tax_class='Gamma',
            order='Enterobacteriales',
            family='Enterobacteriaceae',
            genus='Bacillus',
            species='subtilis'
        )
        
        assert resultado.num_hits == 0
        assert resultado.porcentaje_hits == 0
    
    def test_resultado_relacion_archivo(self, archivo_16s):
        """Test relationship with ArchivoMolecular"""
        resultado1 = ResultadoTaxonomico.objects.create(
            archivo=archivo_16s,
            kingdom='Bacteria',
            phylum='Proteobacteria',
            tax_class='Gamma',
            order='Enterobacteriales',
            family='Enterobacteriaceae',
            genus='Bacillus',
            species='subtilis',
            num_hits=100
        )
        resultado2 = ResultadoTaxonomico.objects.create(
            archivo=archivo_16s,
            kingdom='Bacteria',
            phylum='Proteobacteria',
            tax_class='Gamma',
            order='Enterobacteriales',
            family='Enterobacteriaceae',
            genus='Pseudomonas',
            species='aeruginosa',
            num_hits=50
        )
        
        assert archivo_16s.resultadotaxonomico_set.count() == 2


# ═══════════════════════════════════════════════════════════════
# TESTS: CatalogoMicroorganismo Model
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.django_db
class TestCatalogoMicroorganismoModel:
    """Tests for CatalogoMicroorganismo model"""
    
    def test_crear_catalogo_benefico(self):
        """Test creating a beneficial microorganism entry"""
        entrada = CatalogoMicroorganismo.objects.create(
            nombre='Bacillus',
            nivel='genus',
            clasificacion='benefico',
            descripcion='Productor de antibióticos'
        )
        
        assert entrada.nombre == 'Bacillus'
        assert entrada.clasificacion == 'benefico'
    
    def test_crear_catalogo_patogeno(self):
        """Test creating a pathogenic microorganism entry"""
        entrada = CatalogoMicroorganismo.objects.create(
            nombre='Xanthomonas',
            nivel='genus',
            clasificacion='fitopatogeno',
            descripcion='Bacteria fitopatógena'
        )
        
        assert entrada.clasificacion == 'fitopatogeno'
    
    def test_clasificaciones_validas(self):
        """Test all valid classification options"""
        clasificaciones = ['benefico', 'fitopatogeno', 'neutral', 'sin_clasificar']
        
        for clasificacion in clasificaciones:
            entrada = CatalogoMicroorganismo.objects.create(
                nombre=f'Microorg_{clasificacion}',
                nivel='genus',
                clasificacion=clasificacion
            )
            assert entrada.clasificacion == clasificacion


# ═══════════════════════════════════════════════════════════════
# TESTS: Usuario Model
# ═══════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.django_db
class TestUsuarioModel:
    """Tests for custom Usuario model"""
    
    def test_crear_usuario_admin(self):
        """Test creating an admin user"""
        usuario = Usuario.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='pass123',
            rol='admin'
        )
        
        assert usuario.rol == 'admin'
        assert usuario.is_superuser
    
    def test_crear_usuario_tecnico(self):
        """Test creating a technician user"""
        usuario = Usuario.objects.create_user(
            username='tecnico1',
            email='tecnico@test.com',
            password='pass123',
            rol='tecnico'
        )
        
        assert usuario.rol == 'tecnico'
    
    def test_crear_usuario_agricultor(self):
        """Test creating a farmer user"""
        usuario = Usuario.objects.create_user(
            username='agricultor1',
            email='agricultor@test.com',
            password='pass123',
            rol='agricultor'
        )
        
        assert usuario.rol == 'agricultor'
    
    def test_usuario_str(self):
        """Test Usuario string representation"""
        usuario = Usuario.objects.create_user(
            username='testuser',
            password='pass123',
            rol='tecnico'
        )
        
        assert 'testuser' in str(usuario)
        assert 'Técnico' in str(usuario)
