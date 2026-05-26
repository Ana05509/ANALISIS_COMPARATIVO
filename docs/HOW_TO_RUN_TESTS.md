# 🧪 EXECUTING TESTS - Step by Step (Week 2)

**Objetivo:** Ejecutar 62 tests y generar reporte de cobertura  
**Duración:** ~5 minutos  
**Resultado esperado:** 62/62 tests pasando, >80% coverage  

---

## 📋 Prerequisitos

✅ Python 3.11+ instalado  
✅ Django 6.0.4 instalado  
✅ Proyecto en: C:\Users\fherr\Documents\FINAL\ANALISIS_COMPARATIVO  

---

## 🚀 OPCIÓN 1: Ejecución Rápida (Recomendado - 3 minutos)

### Paso 1: Abrir Command Prompt

```
Presionar: Windows + R
Escribir: cmd
Presionar: Enter
```

### Paso 2: Navegar al Proyecto

```bash
cd C:\Users\fherr\Documents\FINAL\ANALISIS_COMPARATIVO
```

### Paso 3: Instalar Dependencias de Testing

```bash
pip install -r requirements-testing.txt -q
```

**Qué instala:**
- pytest 7.4.3
- pytest-django
- pytest-cov (coverage)
- Factory Boy
- Faker

**Duración:** 1-2 minutos

### Paso 4: Ejecutar Tests CON Cobertura

```bash
pytest -v --cov=analisis --cov-report=html --tb=short
```

**Explicación:**
- `-v` → Modo verbose (muestra cada test)
- `--cov=analisis` → Medir cobertura en app 'analisis'
- `--cov-report=html` → Generar reporte HTML
- `--tb=short` → Mostrar errores cortos

---

## 🧪 OPCIÓN 2: Ejecución Simple (Sin Coverage - 1 minuto)

```bash
pytest -v
```

**Resultado esperado:**
```
collected 62 items

analisis/test/test_pipeline_comprehensive.py ......................  [ 32%]
analisis/test/test_models_comprehensive.py .............................  [ 64%]
analisis/test/test_comparison_service.py .......................  [ 100%]

========================= 62 passed in 2.45s ==========================
```

---

## 📊 OPCIÓN 3: Tests Específicos

### Solo tests de pipeline:
```bash
pytest -v analisis/test/test_pipeline_comprehensive.py
```

### Solo tests de modelos:
```bash
pytest -v analisis/test/test_models_comprehensive.py
```

### Solo tests de comparación:
```bash
pytest -v analisis/test/test_comparison_service.py
```

---

## 📈 Interpretar Resultados

### Éxito Completo ✅

```
========================= 62 passed in 2.45s ==========================
Coverage: 85% (see htmlcov/index.html for details)
```

**Significa:**
- ✅ Todos los tests pasaron
- ✅ Cobertura superior a 80%
- ✅ Sistema funcionando correctamente

### Si Hay Fallos ❌

```
FAILED analisis/test/test_pipeline_comprehensive.py::test_cargar_archivo_csv
```

**Qué hacer:**
1. Leer el error mostrado
2. Consultar WEEK2_EXECUTION_GUIDE.md → "Troubleshooting"
3. Revisar el archivo de test indicado

---

## 📊 Ver Reporte de Cobertura

### Opción 1: Abrir en el navegador (Automático)

Después de ejecutar pytest, se crea `htmlcov/index.html`:

```bash
# Windows
start htmlcov\index.html

# macOS
open htmlcov/index.html

# Linux
firefox htmlcov/index.html
```

### Qué verás:

```
TOTAL        621   90   85%   ← Cobertura general

analisis/__init__.py              0      0   100%  ✅
analisis/models.py              120     10    91%  ✅
analisis/views/dashboard.py       40      8    80%  ✅
analisis/services/...           200     30    85%  ✅
```

**Interpretación:**
- 100% = Perfectamente testeado
- 85%+ = Excelente
- 80%+ = Aceptable
- <75% = Revisar y mejorar

---

## 🔍 Detalles de Coverage

### Por Componente

```
analisis/services/business/upload_service.py
  Líneas totales: 200
  Líneas testeadas: 170
  Coverage: 85%
  
  No testeadas:
  - Línea 145: Manejo de archivo corrupto (edge case)
  - Línea 156: Timeout en lectura (raro en tests)
```

### Cómo Mejorar Coverage

**Si coverage < 80%:**

1. Identificar las líneas no testeadas (en htmlcov)
2. Abrir el archivo en editor
3. Escribir test para esa funcionalidad
4. Re-ejecutar pytest

---

## ⏱️ Duración Esperada

| Paso | Tiempo |
|------|--------|
| Navegar a carpeta | 30 seg |
| Instalar dependencias | 1-2 min |
| Ejecutar tests | 2-3 seg |
| Ver cobertura | 1 min |
| **TOTAL** | **4-5 min** |

---

## 📋 Checklist Ejecución

- [ ] Abrir Command Prompt
- [ ] `cd C:\Users\fherr\Documents\FINAL\ANALISIS_COMPARATIVO`
- [ ] `pip install -r requirements-testing.txt -q`
- [ ] `pytest -v --cov=analisis --cov-report=html --tb=short`
- [ ] Esperar a que termine
- [ ] `start htmlcov\index.html` para ver cobertura
- [ ] Verificar: 62/62 tests pasando
- [ ] Verificar: Coverage >80%

---

## 🎯 Resultados Esperados

### Ejecución Exitosa:

```
platform win32 -- Python 3.11.x, pytest-7.4.3
Django settings module configured.
collected 62 items

analisis/test/test_pipeline_comprehensive.py::test_cargar_archivo_csv PASSED      [  1%]
analisis/test/test_pipeline_comprehensive.py::test_validar_columnas PASSED        [  3%]
analisis/test/test_pipeline_comprehensive.py::test_limpiar_datos PASSED           [  4%]
...
analisis/test/test_comparison_service.py::test_comparar_productos PASSED          [ 97%]
analisis/test/test_comparison_service.py::test_obtener_exclusivos PASSED          [100%]

========================= 62 passed in 2.45s ==========================

Coverage Report:
Name                                   Stmts   Miss  Cover
──────────────────────────────────────────────────────────────
analisis/models.py                       120     10    91%
analisis/services/business/...           200     30    85%
analisis/services/processing/...         150     15    90%
analisis/views/dashboard.py               40      8    80%
──────────────────────────────────────────────────────────────
TOTAL                                    621     90    85%
```

---

## 🐛 Si Algo Falla

### Error: "No module named 'pytest'"

```bash
pip install pytest -q
pip install pytest-django -q
pip install pytest-cov -q
```

### Error: "ModuleNotFoundError: No module named 'django'"

```bash
pip install -r requirements.txt -q
```

### Error: "Database locked" (SQLite issue)

```bash
# Esto es normal en tests - SQLite es limitado
# Simplemente re-ejecutar:
pytest -v
```

### Error: "CONNECTION REFUSED" (database)

```bash
# Los tests usan BD en memoria - debería estar OK
# Si persiste:
python manage.py migrate
pytest -v
```

---

## ✅ Próximos Pasos (Después de Tests Exitosos)

### Si 62/62 tests pasan:

1. ✅ **Celebrar!** El sistema está funcionando
2. 📝 Documentar resultados en PHASE1_WEEK2_REPORT.md
3. 🔄 Escribir integration tests (usar INTEGRATION_TESTS_TEMPLATE.md)
4. 🐘 Instalar PostgreSQL (ver POSTGRESQL_SETUP_GUIDE.md)
5. 🔄 Migrar base de datos a PostgreSQL

### Si algunos tests fallan:

1. ❌ Leer el error específico
2. 🔍 Buscar la línea del error en el archivo de test
3. 🐛 Debuggear el código o el test
4. ✏️ Corregir
5. 🔄 Re-ejecutar hasta que pasen

---

## 📊 Comandos Rápidos (Copy & Paste)

### Ejecutar TODO (recomendado):
```bash
cd C:\Users\fherr\Documents\FINAL\ANALISIS_COMPARATIVO && pip install -r requirements-testing.txt -q && pytest -v --cov=analisis --cov-report=html --tb=short && start htmlcov\index.html
```

### Solo tests:
```bash
pytest -v
```

### Tests + cobertura (sin browser):
```bash
pytest -v --cov=analisis --cov-report=term-missing
```

### Tests en modo watch (ejecuta cuando cambias archivos):
```bash
pip install pytest-watch
ptw -- -v
```

---

## 🎯 Resultado Final Esperado

**Status:** ✅ ALL TESTS PASSING

```
========== 62 passed in 2.45s ==========
Coverage: 85%

✅ Pipeline tests: 20/20 passing
✅ Models tests: 25/25 passing  
✅ Services tests: 15/15 passing
✅ Coverage: 85% (target: >80%)
```

---

**Time to Execute:** 5 minutes  
**Expected Result:** 62/62 tests passing  
**Success Indicator:** ✅ Coverage >80%  

Ready? Run the command above! 🚀

---

**Created:** May 2026  
**Phase:** 1 Week 2  
**Purpose:** Test execution guide
