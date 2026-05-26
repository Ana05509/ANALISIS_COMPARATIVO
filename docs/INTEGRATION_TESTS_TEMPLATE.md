# 🧪 Integration Tests Template - Ready to Implement

**File:** `analisis/test/test_integration_flows.py`  
**Purpose:** End-to-end testing of core workflows  
**Marker:** `@pytest.mark.integration`  

---

## Usage

```bash
# Run ALL integration tests
pytest -v -m integration

# Run specific integration test
pytest -v analisis/test/test_integration_flows.py::TestUploadFlow::test_complete_upload_pipeline

# Run with coverage
pytest -v -m integration --cov=analisis --cov-report=html
```

---

## Template Structure

### Integration Test 1: Complete Upload Flow

**What it tests:** File upload → Data processing → Storage → Classification

```python
@pytest.mark.integration
def test_complete_upload_pipeline(client, admin_user, cultivo_factory, sample_16s_csv):
    """
    SCENARIO: Admin uploads a valid 16S CSV file
    
    STEPS:
    1. Create cultivo and login as admin
    2. POST /subir/ with CSV file
    3. Verify MuestraSuelo created
    4. Verify ArchivoMolecular created
    5. Verify ResultadoTaxonomico created (bulk)
    6. Verify CatalogoMicroorganismo updated with classifications
    
    EXPECTED: All objects created, classifications assigned
    """
    # Setup
    cultivo = cultivo_factory(nombre='Cacao')
    client.force_login(admin_user)
    
    # Action: Upload file
    response = client.post('/analisis/subir/', {
        'archivo': sample_16s_csv,
        'cultivo_id': cultivo.id,
        'tipo_analisis': '16S'
    })
    
    # Assertions
    assert response.status_code == 302  # Redirect to dashboard
    assert MuestraSuelo.objects.count() == 1
    assert ArchivoMolecular.objects.count() == 1
    assert ResultadoTaxonomico.objects.count() > 0
    
    # Check classifications
    archivo = ArchivoMolecular.objects.first()
    resultados = ResultadoTaxonomico.objects.filter(archivo=archivo)
    
    assert resultados.filter(genus__in=['Bacillus', 'Pseudomonas']).exists()
    beneficos = [r.genus for r in resultados if es_benefico(r.genus)]
    assert len(beneficos) > 0
```

---

### Integration Test 2: Comparison Flow

**What it tests:** Load 2 files → Comparison → Results

```python
@pytest.mark.integration
def test_complete_comparison(client, analyst_user, archivo_factory):
    """
    SCENARIO: Analyst compares 2 samples
    
    STEPS:
    1. Create 2 files with different microbe profiles
    2. Login as analyst
    3. GET /comparar/ (select both files)
    4. POST /comparar/ (request comparison)
    5. Verify response includes:
       - Top 10 microbes by abundance
       - Shared organisms
       - Exclusive organisms (file1 only, file2 only)
       - Differential (which is more abundant)
    
    EXPECTED: Comparison table with all metrics
    """
    # Setup
    client.force_login(analyst_user)
    archivo1 = archivo_factory(tipo_analisis='16S')
    archivo2 = archivo_factory(tipo_analisis='16S')
    
    # Action: Request comparison
    response = client.post('/analisis/comparar/', {
        'archivo1_id': archivo1.id,
        'archivo2_id': archivo2.id,
        'nivel': 'genus',
        'top_n': 10
    })
    
    # Assertions
    assert response.status_code == 200
    assert 'tabla_comparacion' in response.context
    
    tabla = response.context['tabla_comparacion']
    assert tabla['compartidos'] != []  # Some shared organisms
    assert tabla['exclusivos_archivo1'] != []  # Some unique to file1
    assert tabla['exclusivos_archivo2'] != []  # Some unique to file2
```

---

### Integration Test 3: Data Integrity with Transactions

**What it tests:** Database consistency, rollback on error

```python
@pytest.mark.integration
def test_upload_rollback_on_error(client, admin_user, cultivo_factory, invalid_csv):
    """
    SCENARIO: Upload fails midway, verify rollback
    
    STEPS:
    1. Start upload process
    2. Inject error in processing
    3. Verify rollback (no partial data)
    4. Verify error message to user
    
    EXPECTED: No orphaned records, clean rollback
    """
    cultivo = cultivo_factory()
    client.force_login(admin_user)
    
    # Count before
    antes_muestra = MuestraSuelo.objects.count()
    
    # Action: Upload invalid file (missing required columns)
    response = client.post('/analisis/subir/', {
        'archivo': invalid_csv,
        'cultivo_id': cultivo.id,
        'tipo_analisis': '16S'
    })
    
    # Assertions: Should fail and rollback
    assert response.status_code == 400  # Bad request
    assert MuestraSuelo.objects.count() == antes_muestra  # No new records
    assert 'columnas requeridas' in response.content.decode()
```

---

### Integration Test 4: Concurrent Uploads

**What it tests:** Multiple simultaneous uploads don't interfere

```python
@pytest.mark.integration
def test_concurrent_uploads(client, admin_user, cultivo_factory, sample_csv_factory):
    """
    SCENARIO: 3 users upload simultaneously
    
    STEPS:
    1. Create 3 users
    2. Submit 3 upload requests concurrently
    3. Verify all complete successfully
    4. Verify correct associations (no cross-contamination)
    
    EXPECTED: 3 independent uploads, no errors
    """
    import concurrent.futures
    
    usuarios = [admin_user] + [UsuarioFactory() for _ in range(2)]
    cultivo = cultivo_factory()
    
    def upload_for_user(usuario):
        client.force_login(usuario)
        response = client.post('/analisis/subir/', {
            'archivo': sample_csv_factory(),
            'cultivo_id': cultivo.id,
            'tipo_analisis': '16S'
        })
        return response.status_code == 302
    
    # Execute concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(upload_for_user, usuarios))
    
    # All uploads succeeded
    assert all(results)
    # 3 distinct files created
    assert ArchivoMolecular.objects.count() == 3
    # Each owned by correct user
    for usuario, archivo in zip(usuarios, ArchivoMolecular.objects.all()):
        assert archivo.usuario == usuario
```

---

### Integration Test 5: Report Generation

**What it tests:** Generate PDF/Excel report from analysis

```python
@pytest.mark.integration
def test_generate_report(client, analyst_user, archivo_factory):
    """
    SCENARIO: Analyst generates report for a sample
    
    STEPS:
    1. Load sample with analysis results
    2. Request report generation (PDF or Excel)
    3. Verify file returned with correct content
    4. Verify formatting (headers, data, visualizations)
    
    EXPECTED: Valid report file with all data
    """
    client.force_login(analyst_user)
    archivo = archivo_factory()
    
    # Action: Request PDF report
    response = client.get(f'/analisis/reportes/{archivo.id}/?format=pdf')
    
    # Assertions
    assert response.status_code == 200
    assert response['Content-Type'] == 'application/pdf'
    assert 'Content-Disposition' in response
    assert 'attachment' in response['Content-Disposition']
    assert b'PDF-1.' in response.content  # PDF header
```

---

## Test Fixtures Needed

### 1. Sample CSV Files

```python
# conftest.py additions

@pytest.fixture
def sample_16s_csv(tmp_path):
    """Create a valid 16S CSV file for testing"""
    csv_path = tmp_path / "sample_16s.csv"
    csv_path.write_text("""kingdom,phylum,class,order,family,genus,species,num_hits,porcentaje_hits
Bacteria,Firmicutes,Bacilli,Bacillales,Bacillaceae,Bacillus,subtilis,500,25.5
Bacteria,Proteobacteria,Gamma,Pseudomonadales,Pseudomonadaceae,Pseudomonas,aeruginosa,450,23.0
Bacteria,Actinobacteria,Actinobacteria,Actinomycetales,Streptomycetaceae,Streptomyces,coelicolor,350,17.8
Bacteria,Firmicutes,Bacilli,Bacillales,Bacillaceae,Bacillus,cereus,300,15.3
Bacteria,Proteobacteria,Alpha,Rhizobiales,Rhizobiaceae,Rhizobium,leguminosarum,200,10.2""")
    return csv_path

@pytest.fixture
def invalid_csv(tmp_path):
    """Create a CSV missing required columns"""
    csv_path = tmp_path / "invalid.csv"
    csv_path.write_text("genus,species\nBacillus,subtilis")  # Missing many columns
    return csv_path

@pytest.fixture
def sample_csv_factory(tmp_path):
    """Factory to create multiple test CSV files"""
    def _create_csv(num_records=5):
        import csv
        csv_path = tmp_path / f"sample_{num_records}.csv"
        
        genera = ['Bacillus', 'Pseudomonas', 'Rhizobium', 'Streptomyces', 'Serratia']
        species = ['subtilis', 'aeruginosa', 'leguminosarum', 'coelicolor', 'marcescens']
        
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species', 
                'num_hits', 'porcentaje_hits'
            ])
            writer.writeheader()
            for i in range(num_records):
                writer.writerow({
                    'kingdom': 'Bacteria',
                    'phylum': 'Firmicutes',
                    'class': 'Bacilli',
                    'order': 'Bacillales',
                    'family': 'Bacillaceae',
                    'genus': genera[i % len(genera)],
                    'species': species[i % len(species)],
                    'num_hits': 100 * (i + 1),
                    'porcentaje_hits': 20.0 - (i * 2)
                })
        return csv_path
    
    return _create_csv
```

---

## Running Integration Tests

### Full Suite
```bash
pytest -v -m integration
```

### Specific Test
```bash
pytest -v analisis/test/test_integration_flows.py::TestUploadFlow::test_complete_upload_pipeline
```

### With Coverage
```bash
pytest -v -m integration --cov=analisis --cov-report=html
```

### With Output
```bash
pytest -v -m integration -s  # Show print() output
```

---

## Expected Results

```
collected 6 items

analisis/test/test_integration_flows.py::TestUploadFlow::test_complete_upload_pipeline PASSED      [ 16%]
analisis/test/test_integration_flows.py::TestUploadFlow::test_upload_rollback_on_error PASSED      [ 33%]
analisis/test/test_integration_flows.py::TestComparisonFlow::test_complete_comparison PASSED      [ 50%]
analisis/test/test_integration_flows.py::TestDataIntegrity::test_concurrent_uploads PASSED        [ 66%]
analisis/test/test_integration_flows.py::TestReportGeneration::test_generate_report PASSED        [ 83%]

========================= 5 passed in 3.2s ==========================
```

---

## Checklist Before Implementation

- [ ] All unit tests passing (from Week 1)
- [ ] Fixtures defined in conftest.py
- [ ] Test file created: `analisis/test/test_integration_flows.py`
- [ ] Test classes and methods named with `test_` prefix
- [ ] Each test has docstring (SCENARIO, STEPS, EXPECTED)
- [ ] Fixtures used correctly (client, admin_user, factory classes)
- [ ] Assertions verify outcomes clearly
- [ ] All tests marked with `@pytest.mark.integration`

---

**Template Version:** 1.0  
**Status:** Ready for Implementation  
**Next:** Copy and adapt to your project's specific flows
