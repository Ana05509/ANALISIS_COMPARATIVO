"""
conftest.py - Shared test configuration and fixtures for all tests

This file provides:
- Django test database setup
- Common fixtures for models and services
- Factory fixtures for easy test data creation
"""

import os
import pytest
import pandas as pd
import numpy as np
from django.test import Client
from django.contrib.auth import get_user_model

# Import factories
from factory.django import DjangoModelFactory
import factory

from analisis.models import Cultivo, VariedadClon, MuestraSuelo, ArchivoMolecular, ResultadoTaxonomico, CatalogoMicroorganismo


# ═══════════════════════════════════════════════════════════════
# FACTORIES
# ═══════════════════════════════════════════════════════════════

User = get_user_model()


class UsuarioFactory(DjangoModelFactory):
    """Factory for creating test users"""
    class Meta:
        model = User
    
    username = factory.Sequence(lambda n: f'usuario{n}')
    email = factory.Sequence(lambda n: f'user{n}@example.com')
    password = 'testpass123'
    rol = 'tecnico'
    
    @classmethod
    def create(cls, **kwargs):
        """Override to hash password"""
        user = super().create(**kwargs)
        user.set_password(kwargs.get('password', 'testpass123'))
        user.save()
        return user


class CultivoFactory(DjangoModelFactory):
    """Factory for creating test crops"""
    class Meta:
        model = Cultivo
    
    nombre = factory.Sequence(lambda n: f'Cultivo{n}')
    descripcion = "Cultivo de prueba"


class VariedadClonFactory(DjangoModelFactory):
    """Factory for creating test varieties/clones"""
    class Meta:
        model = VariedadClon
    
    cultivo = factory.SubFactory(CultivoFactory)
    nombre = factory.Sequence(lambda n: f'Variedad{n}')
    descripcion = "Variedad de prueba"


class MuestraSueloFactory(DjangoModelFactory):
    """Factory for creating test soil samples"""
    class Meta:
        model = MuestraSuelo
    
    codigo = factory.Sequence(lambda n: f'MUESTRA-{n:04d}')
    cultivo = factory.SubFactory(CultivoFactory)
    variedad_clon = factory.SubFactory(VariedadClonFactory, cultivo=factory.SelfAttribute('..cultivo'))
    tipo_muestra = "Suelo"
    observaciones = "Muestra de prueba"


class ArchivoMolecularFactory(DjangoModelFactory):
    """Factory for creating test molecular analysis files"""
    class Meta:
        model = ArchivoMolecular
    
    muestra = factory.SubFactory(MuestraSueloFactory)
    tipo_analisis = "16S"


class ResultadoTaxonomicoFactory(DjangoModelFactory):
    """Factory for creating test taxonomic results"""
    class Meta:
        model = ResultadoTaxonomico
    
    archivo = factory.SubFactory(ArchivoMolecularFactory)
    kingdom = "Bacteria"
    phylum = "Proteobacteria"
    tax_class = "Gammaproteobacteria"
    order = "Enterobacteriales"
    family = "Enterobacteriaceae"
    genus = "Bacillus"
    species = "subtilis"
    num_hits = factory.Faker('random_int', min=1, max=1000)
    porcentaje_hits = factory.Faker('pyfloat', left_digits=2, right_digits=2, positive=True)


class CatalogoMicroorganismoFactory(DjangoModelFactory):
    """Factory for creating test microorganism catalog entries"""
    class Meta:
        model = CatalogoMicroorganismo
    
    nombre = factory.Sequence(lambda n: f'Microorganismo{n}')
    nivel = "genus"
    clasificacion = "sin_clasificar"
    descripcion = "Entrada de prueba del catálogo"


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def admin_user(db):
    """Create an admin user"""
    user = User.objects.create_superuser(
        username='admin',
        email='admin@test.com',
        password='adminpass123',
        rol='admin'
    )
    return user


@pytest.fixture
def analyst_user(db):
    """Create an analyst user"""
    return UsuarioFactory(rol='tecnico', username='analyst')


@pytest.fixture
def farmer_user(db):
    """Create a farmer user"""
    return UsuarioFactory(rol='agricultor', username='farmer')


@pytest.fixture
def client():
    """Return a Django test client"""
    return Client()


@pytest.fixture
def authenticated_client(client, analyst_user):
    """Return an authenticated client"""
    client.login(username='analyst', password='testpass123')
    return client


@pytest.fixture
def cultivo(db):
    """Create a test crop"""
    return CultivoFactory(nombre='Cacao')


@pytest.fixture
def variedad(db, cultivo):
    """Create a test variety"""
    return VariedadClonFactory(cultivo=cultivo, nombre='CCN51')


@pytest.fixture
def muestra(db, cultivo, variedad):
    """Create a test soil sample"""
    return MuestraSueloFactory(cultivo=cultivo, variedad_clon=variedad)


@pytest.fixture
def archivo_16s(db, muestra):
    """Create a 16S molecular file"""
    return ArchivoMolecularFactory(muestra=muestra, tipo_analisis='16S')


@pytest.fixture
def archivo_its(db, muestra):
    """Create an ITS molecular file"""
    return ArchivoMolecularFactory(muestra=muestra, tipo_analisis='ITS')


@pytest.fixture
def resultados_16s(db, archivo_16s):
    """Create multiple 16S taxonomic results"""
    resultados = []
    genera_16s = ['Bacillus', 'Pseudomonas', 'Rhizobium', 'Streptomyces', 'Serratia']
    
    for i, genus in enumerate(genera_16s):
        resultado = ResultadoTaxonomicoFactory(
            archivo=archivo_16s,
            genus=genus,
            num_hits=100 * (len(genera_16s) - i),  # Decreasing abundance
            porcentaje_hits=(100 - i*20) / 100,  # Decreasing percentage
        )
        resultados.append(resultado)
    
    return resultados


@pytest.fixture
def sample_dataframe():
    """Create a sample DataFrame for pipeline testing"""
    data = {
        'kingdom': ['Bacteria', 'Bacteria', 'Fungi'],
        'phylum': ['Proteobacteria', 'Proteobacteria', 'Ascomycota'],
        'class': ['Gammaproteobacteria', 'Alphaproteobacteria', 'Eurotiomycetes'],
        'order': ['Enterobacteriales', 'Rhizobiales', 'Eurotiales'],
        'family': ['Enterobacteriaceae', 'Rhizobiaceae', 'Aspergillaceae'],
        'genus': ['Bacillus', 'Rhizobium', 'Aspergillus'],
        'species': ['subtilis', 'leguminosarum', 'niger'],
        'num_hits': [500, 300, 200],
        '%_hits': [50.0, 30.0, 20.0],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_csv_file(tmp_path, sample_dataframe):
    """Create a temporary CSV file for upload testing"""
    csv_file = tmp_path / "sample_16s.csv"
    sample_dataframe.to_csv(csv_file, index=False)
    return str(csv_file)


@pytest.fixture
def sample_excel_file(tmp_path, sample_dataframe):
    """Create a temporary Excel file for upload testing"""
    excel_file = tmp_path / "sample_16s.xlsx"
    sample_dataframe.to_excel(excel_file, index=False, sheet_name='16S')
    return str(excel_file)


# ═══════════════════════════════════════════════════════════════
# MARKERS & CONFIGURATION
# ═══════════════════════════════════════════════════════════════

def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow"
    )
    config.addinivalue_line(
        "markers", "django_db: mark test as requiring database"
    )


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def cleanup_media(settings):
    """Cleanup media files after test"""
    yield
    # Cleanup code here if needed
    pass
