# 🔬 REPORTE ESTRUCTURAL DE ARQUITECTURA: TERRABIOLAB
**Fecha de Análisis:** 2026-06-07 11:05:57
**Directorio Raíz:** `C:\Users\fherr\Documents\Proyecto_Analisis_Final\ANALISIS_COMPARATIVO`

---
## 📊 MÉTRICAS GENERALES DEL PROYECTO

**Módulos de Código Python Analizados:** 61

### Componentes del Ecosistema Detectados:
- **Procesamiento Algorítmico y Bioinformática:** 18 archivo(s) estructurado(s)
- **Enrutamiento del Sistema (URLs):** 4 archivo(s) estructurado(s)
- **Administración Personalizada (Unfold):** 1 archivo(s) estructurado(s)
- **Configuración / Infraestructura Core:** 13 archivo(s) estructurado(s)
- **Modelos y Persistencia (Base de Datos):** 3 archivo(s) estructurado(s)
- **Ecosistema de Pruebas Automatizadas (Tests):** 10 archivo(s) estructurado(s)
- **Servicios de Datos e Interpretación:** 1 archivo(s) estructurado(s)
- **Controladores de Interfaz (Vistas/Views):** 11 archivo(s) estructurado(s)

---
## 📂 DESGLOSE TÉCNICO POR MÓDULO

### 📄 `analisis_proyect.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Implementa 5 funciones lógicas.

  **Funciones de Procesamiento:**
  - `detect_category()`
  - `analyze_python_file()`
  - `generate_description()`
  - `analyze_project()`
  - `generate_markdown()`
  **Módulos / Dependencias Relacionadas:**
  - `[collections, pathlib, datetime, os, ast]`

——————————————————————————————

### 📄 `generar_estructura.py`

- **Capa de Software:** Enrutamiento del Sistema (URLs)
- **Resumen Estático:** Módulo enfocado en **Enrutamiento del Sistema (URLs)**. Implementa 1 funciones lógicas.

  **Funciones de Procesamiento:**
  - `listar_estructura()`
  **Módulos / Dependencias Relacionadas:**
  - `[os, pathlib]`

——————————————————————————————

### 📄 `manage.py`

- **Capa de Software:** Enrutamiento del Sistema (URLs)
- **Resumen Estático:** Módulo enfocado en **Enrutamiento del Sistema (URLs)**. Implementa 1 funciones lógicas.

  **Funciones de Procesamiento:**
  - `main()`
  **Módulos / Dependencias Relacionadas:**
  - `[sys, os, django.core.management]`

——————————————————————————————

### 📄 `analisis\admin.py`

- **Capa de Software:** Administración Personalizada (Unfold)
- **Resumen Estático:** Módulo enfocado en **Administración Personalizada (Unfold)**. Define 7 estructuras de objeto/clase. Implementa 4 funciones lógicas.

  **Estructuras de Clases:**
  - `CultivoAdmin`
  - `VariedadClonAdmin`
  - `MuestraSueloAdmin`
  - `ArchivoMolecularAdmin`
  - `ResultadoTaxonomicoAdmin`
  - `CatalogoMicroorganismoAdmin`
  - `UsuarioAdmin`
  **Funciones de Procesamiento:**
  - `save_model()`
  - `save_model()`
  - `save_model()`
  - `get_fieldsets()`
  **Módulos / Dependencias Relacionadas:**
  - `[unfold.admin, django.contrib.auth.admin, models, django.contrib]`

——————————————————————————————

### 📄 `analisis\apps.py`

- **Capa de Software:** Configuración / Infraestructura Core
- **Resumen Estático:** Módulo enfocado en **Configuración / Infraestructura Core**. Define 1 estructuras de objeto/clase. Implementa 2 funciones lógicas.

  **Estructuras de Clases:**
  - `AnalisisConfig`
  **Funciones de Procesamiento:**
  - `ready()`
  - `capitalizar_nombre_y_apellido()`
  **Módulos / Dependencias Relacionadas:**
  - `[django.contrib.auth, django.db.models.signals, django.apps]`

——————————————————————————————

### 📄 `analisis\forms.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Define 3 estructuras de objeto/clase. Implementa 4 funciones lógicas.

  **Estructuras de Clases:**
  - `CompararForm`
  - `SubirDatosForm`
  - `CustomSignupForm`
  **Funciones de Procesamiento:**
  - `__init__()`
  - `clean_top_n()`
  - `clean_top_n()`
  - `signup()`
  **Módulos / Dependencias Relacionadas:**
  - `[models, django]`

——————————————————————————————

### 📄 `analisis\models.py`

- **Capa de Software:** Modelos y Persistencia (Base de Datos)
- **Resumen Estático:** Módulo enfocado en **Modelos y Persistencia (Base de Datos)**. Define 12 estructuras de objeto/clase. Implementa 8 funciones lógicas.

  **Estructuras de Clases:**
  - `Cultivo`
  - `VariedadClon`
  - `MuestraSuelo`
  - `ArchivoMolecular`
  - `ResultadoTaxonomico`
  - `CatalogoMicroorganismo`
  - `Usuario`
  - `Meta`
  - `Meta`
  - `Meta`
  - `Meta`
  - `Meta`
  **Funciones de Procesamiento:**
  - `ruta_archivo_molecular()`
  - `__str__()`
  - `__str__()`
  - `__str__()`
  - `__str__()`
  - `__str__()`
  - `__str__()`
  - `__str__()`
  **Módulos / Dependencias Relacionadas:**
  - `[os, django.db, django.contrib.auth.models]`

——————————————————————————————

### 📄 `analisis\tests.py`

- **Capa de Software:** Ecosistema de Pruebas Automatizadas (Tests)
- **Resumen Estático:** Módulo enfocado en **Ecosistema de Pruebas Automatizadas (Tests)**. Define 7 estructuras de objeto/clase. Implementa 30 funciones lógicas.

  **Estructuras de Clases:**
  - `TestVisualizationService`
  - `TestStatisticalAnalyzer`
  - `TestExportService`
  - `TestDashboardView`
  - `TestAnalysisView`
  - `TestComparisonView`
  - `TestReportesView`
  **Funciones de Procesamiento:**
  - `setUp()`
  - `test_crear_grafico_abundancia_barras()`
  - `test_crear_grafico_abundancia_pie()`
  - `test_crear_grafico_diversidad_linea()`
  - `test_crear_grafico_comparacion_heatmap()`
  - `test_exportar_grafico_json()`
  - `test_empty_dataframe()`
  - `setUp()`
  - `test_calcular_descriptivas()`
  - `test_test_t_independiente()`
  - `test_test_mann_whitney()`
  - `test_calcular_pca()`
  - `test_calcular_similitud_jaccard()`
  - `test_test_normalidad_shapiro()`
  - `setUp()`
  - `test_exportar_json()`
  - `test_exportar_csv_avanzado()`
  - `test_generar_pdf_completo()`
  - `test_generar_html_reporte()`
  - `setUp()`
  - `test_dashboard_accessible()`
  - `test_dashboard_redirect_login()`
  - `test_dashboard_context()`
  - `setUp()`
  - `test_analisis_avanzado_accessible()`
  - `test_analisis_parameters()`
  - `setUp()`
  - `test_comparar_accessible()`
  - `setUp()`
  - `test_reportes_accessible()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas, analisis.services.business.visualization_service, django.test, pytest, analisis.services.business.statistics_service, numpy, django.contrib.auth.models]`

——————————————————————————————

### 📄 `analisis\urls.py`

- **Capa de Software:** Enrutamiento del Sistema (URLs)
- **Resumen Estático:** Módulo enfocado en **Enrutamiento del Sistema (URLs)**.

  **Módulos / Dependencias Relacionadas:**
  - `[django.contrib.auth, views.auth, django.urls]`

——————————————————————————————

### 📄 `analisis\__init__.py`

- **Capa de Software:** Configuración / Infraestructura Core
- **Resumen Estático:** Módulo enfocado en **Configuración / Infraestructura Core**.


——————————————————————————————

### 📄 `analisis\migrations\0001_initial.py`

- **Capa de Software:** Modelos y Persistencia (Base de Datos)
- **Resumen Estático:** Módulo enfocado en **Modelos y Persistencia (Base de Datos)**. Define 1 estructuras de objeto/clase.

  **Estructuras de Clases:**
  - `Migration`
  **Módulos / Dependencias Relacionadas:**
  - `[django.contrib.auth.validators, django.db, django.db.models.deletion, django.utils.timezone, django.contrib.auth.models]`

——————————————————————————————

### 📄 `analisis\migrations\0002_alter_archivomolecular_archivo_and_more.py`

- **Capa de Software:** Modelos y Persistencia (Base de Datos)
- **Resumen Estático:** Módulo enfocado en **Modelos y Persistencia (Base de Datos)**. Define 1 estructuras de objeto/clase.

  **Estructuras de Clases:**
  - `Migration`
  **Módulos / Dependencias Relacionadas:**
  - `[analisis.models, django.db.models.deletion, django.db]`

——————————————————————————————

### 📄 `analisis\migrations\__init__.py`

- **Capa de Software:** Configuración / Infraestructura Core
- **Resumen Estático:** Módulo enfocado en **Configuración / Infraestructura Core**.


——————————————————————————————

### 📄 `analisis\services\__init__.py`

- **Capa de Software:** Configuración / Infraestructura Core
- **Resumen Estático:** Módulo enfocado en **Configuración / Infraestructura Core**.


——————————————————————————————

### 📄 `analisis\services\business\analysis_service.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Implementa 6 funciones lógicas.

  **Funciones de Procesamiento:**
  - `_base_queryset()`
  - `obtener_analisis_avanzado()`
  - `obtener_top_n()`
  - `obtener_diversidad()`
  - `obtener_analisis_diferencial()`
  - `_preparar_df()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas, django.db.models, analisis.models, analisis.services.processing.abundance, analisis.services.processing.diversity]`

——————————————————————————————

### 📄 `analisis\services\business\catalog_service.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Define 1 estructuras de objeto/clase. Implementa 4 funciones lógicas.

  **Estructuras de Clases:**
  - `CatalogService`
  **Funciones de Procesamiento:**
  - `obtener_catalogo_microorganismos()`
  - `buscar_microorganismos()`
  - `obtener_detalle_microorganismo()`
  - `obtener_estadisticas_catalogo()`
  **Módulos / Dependencias Relacionadas:**
  - `[analisis.models, django.db.models]`

——————————————————————————————

### 📄 `analisis\services\business\comparison_service.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Implementa 6 funciones lógicas.

  **Funciones de Procesamiento:**
  - `_obtener_mapa_catalogo()`
  - `comparar_productos()`
  - `_calcular_diferencial()`
  - `ejecutar_comparacion_clean()`
  - `obtener_microorganismos_compartidos()`
  - `obtener_microorganismos_exclusivos()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas, analisis.models, django.db.models]`

——————————————————————————————

### 📄 `analisis\services\business\export_service.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Define 1 estructuras de objeto/clase. Implementa 6 funciones lógicas.

  **Estructuras de Clases:**
  - `ExportService`
  **Funciones de Procesamiento:**
  - `exportar_json()`
  - `exportar_csv_avanzado()`
  - `generar_pdf_completo()`
  - `exportar_pdf_response()`
  - `generar_html_reporte()`
  - `exportar_zip_completo()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas, django.utils.text, reportlab.lib.styles, reportlab.platypus, reportlab.lib, reportlab.lib.enums, reportlab.lib.pagesizes]`

——————————————————————————————

### 📄 `analisis\services\business\report_service.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Define 1 estructuras de objeto/clase. Implementa 5 funciones lógicas.

  **Estructuras de Clases:**
  - `ExportService`
  **Funciones de Procesamiento:**
  - `_construir_dataframe()`
  - `generar_reporte_analisis()`
  - `obtener_historial_reportes()`
  - `obtener_reporte_por_id()`
  - `exportar_excel()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas, collections, django.db.models, datetime, analisis.models, django.http, io]`

——————————————————————————————

### 📄 `analisis\services\business\statistics_service.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Define 1 estructuras de objeto/clase. Implementa 11 funciones lógicas.

  **Estructuras de Clases:**
  - `StatisticsService`
  **Funciones de Procesamiento:**
  - `calcular_descriptivas()`
  - `test_t_independiente()`
  - `test_mann_whitney()`
  - `test_anova()`
  - `calcular_pca()`
  - `calcular_clustering_kmeans()`
  - `calcular_dendrograma_datos()`
  - `calcular_similitud_jaccard()`
  - `calcular_similitud_braycurtis()`
  - `test_normalidad_shapiro()`
  - `generar_reporte_estadistico()`
  **Módulos / Dependencias Relacionadas:**
  - `[scipy, pandas, sklearn.decomposition, warnings, numpy, scipy.cluster.hierarchy, sklearn.preprocessing]`

——————————————————————————————

### 📄 `analisis\services\business\upload_service.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Implementa 4 funciones lógicas.

  **Funciones de Procesamiento:**
  - `parse_int_or_default()`
  - `validar_archivo()`
  - `leer_archivo()`
  - `procesar_upload()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas, analisis.models, analisis.services.processing.pipeline, django.db]`

——————————————————————————————

### 📄 `analisis\services\business\visualization_service.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Define 1 estructuras de objeto/clase. Implementa 1 funciones lógicas.

  **Estructuras de Clases:**
  - `VisualizationService`
  **Funciones de Procesamiento:**
  - `obtener_paquete_graficos_avanzados()`
  **Módulos / Dependencias Relacionadas:**
  - `[plotly.graph_objects, pandas, sklearn.decomposition, plotly.express, json, sklearn.preprocessing]`

——————————————————————————————

### 📄 `analisis\services\business\__init__.py`

- **Capa de Software:** Configuración / Infraestructura Core
- **Resumen Estático:** Módulo enfocado en **Configuración / Infraestructura Core**.


——————————————————————————————

### 📄 `analisis\services\interpretation\beneficial_service.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Define 1 estructuras de objeto/clase. Implementa 4 funciones lógicas.

  **Estructuras de Clases:**
  - `BeneficialMicroorganismsService`
  **Funciones de Procesamiento:**
  - `es_benefico()`
  - `obtener_beneficos_en_muestra()`
  - `marcar_beneficos_en_catalogo()`
  - `calcular_indice_salud_suelo()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas, analisis.models, typing]`

——————————————————————————————

### 📄 `analisis\services\interpretation\microorganism_classifier.py`

- **Capa de Software:** Servicios de Datos e Interpretación
- **Resumen Estático:** Módulo enfocado en **Servicios de Datos e Interpretación**. Define 1 estructuras de objeto/clase. Implementa 3 funciones lógicas.

  **Estructuras de Clases:**
  - `MicroorganismClassificationService`
  **Funciones de Procesamiento:**
  - `clasificar_microorganismo()`
  - `clasificar_y_persistir()`
  - `reclasificar_microorganismo()`
  **Módulos / Dependencias Relacionadas:**
  - `[django.db, typing, analisis.models, pathogen_service, beneficial_service]`

——————————————————————————————

### 📄 `analisis\services\interpretation\pathogen_service.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Define 1 estructuras de objeto/clase. Implementa 4 funciones lógicas.

  **Estructuras de Clases:**
  - `PathogenService`
  **Funciones de Procesamiento:**
  - `es_fitopatogeno()`
  - `obtener_fitopatogenos_en_muestra()`
  - `marcar_fitopatogenos_en_catalogo()`
  - `calcular_carga_patogena_total()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas, analisis.models, typing]`

——————————————————————————————

### 📄 `analisis\services\interpretation\__init__.py`

- **Capa de Software:** Configuración / Infraestructura Core
- **Resumen Estático:** Módulo enfocado en **Configuración / Infraestructura Core**.


——————————————————————————————

### 📄 `analisis\services\processing\abundance.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Define 1 estructuras de objeto/clase. Implementa 5 funciones lógicas.

  **Estructuras de Clases:**
  - `AbundanceService`
  **Funciones de Procesamiento:**
  - `comparar_abundancias()`
  - `calcular_abundancia_relativa()`
  - `normalizar_abundancias()`
  - `identificar_dominantes()`
  - `identificar_raros()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas, typing]`

——————————————————————————————

### 📄 `analisis\services\processing\analytics.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Define 1 estructuras de objeto/clase. Implementa 2 funciones lógicas.

  **Estructuras de Clases:**
  - `TaxonomicInsightsService`
  **Funciones de Procesamiento:**
  - `generar_insights_muestra()`
  - `generar_insights_lote()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas]`

——————————————————————————————

### 📄 `analisis\services\processing\cleaning.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Define 1 estructuras de objeto/clase. Implementa 5 funciones lógicas.

  **Estructuras de Clases:**
  - `DataCleaningService`
  **Funciones de Procesamiento:**
  - `homologar_y_limpiar_strings()`
  - `limpiar_species()`
  - `limpiar_numericos()`
  - `normalizar_taxonomia_macro()`
  - `ejecutar_pipeline_limpieza_completo()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas]`

——————————————————————————————

### 📄 `analisis\services\processing\diversity.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Define 1 estructuras de objeto/clase. Implementa 11 funciones lógicas.

  **Estructuras de Clases:**
  - `DiversityService`
  **Funciones de Procesamiento:**
  - `calcular_riqueza()`
  - `calcular_shannon()`
  - `calcular_simpson()`
  - `calcular_equitatividad()`
  - `calcular_diversidad_alfa()`
  - `_obtener_set_taxonomico_limpio()`
  - `identificar_compartidos()`
  - `identificar_exclusivos()`
  - `calcular_similitud_jaccard()`
  - `calcular_diversidad_beta()`
  - `identify_compartidos_si_fuese_necesario()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas, math]`

——————————————————————————————

### 📄 `analisis\services\processing\pipeline.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Define 1 estructuras de objeto/clase. Implementa 3 funciones lógicas.

  **Estructuras de Clases:**
  - `PipelineProcesamiento`
  **Funciones de Procesamiento:**
  - `validar_columnas()`
  - `limpiar_datos()`
  - `procesar_archivo_df()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas, re]`

——————————————————————————————

### 📄 `analisis\services\processing\taxonomy.py`

- **Capa de Software:** Procesamiento Algorítmico y Bioinformática
- **Resumen Estático:** Módulo enfocado en **Procesamiento Algorítmico y Bioinformática**. Define 1 estructuras de objeto/clase. Implementa 2 funciones lógicas.

  **Estructuras de Clases:**
  - `TaxonomyService`
  **Funciones de Procesamiento:**
  - `agrupar_por_nivel()`
  - `filtrar_top_y_consolidar_residuo()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas, typing]`

——————————————————————————————

### 📄 `analisis\services\processing\__init__.py`

- **Capa de Software:** Configuración / Infraestructura Core
- **Resumen Estático:** Módulo enfocado en **Configuración / Infraestructura Core**.


——————————————————————————————

### 📄 `analisis\templates\__init__.py`

- **Capa de Software:** Configuración / Infraestructura Core
- **Resumen Estático:** Módulo enfocado en **Configuración / Infraestructura Core**.


——————————————————————————————

### 📄 `analisis\templatetags\custom_filters.py`

- **Capa de Software:** Configuración / Infraestructura Core
- **Resumen Estático:** Módulo enfocado en **Configuración / Infraestructura Core**. Implementa 2 funciones lógicas.

  **Funciones de Procesamiento:**
  - `get_item()`
  - `split()`
  **Módulos / Dependencias Relacionadas:**
  - `[django]`

——————————————————————————————

### 📄 `analisis\templatetags\__init__.py`

- **Capa de Software:** Configuración / Infraestructura Core
- **Resumen Estático:** Módulo enfocado en **Configuración / Infraestructura Core**.


——————————————————————————————

### 📄 `analisis\test\test_catalog.py`

- **Capa de Software:** Ecosistema de Pruebas Automatizadas (Tests)
- **Resumen Estático:** Módulo enfocado en **Ecosistema de Pruebas Automatizadas (Tests)**.


——————————————————————————————

### 📄 `analisis\test\test_comparison.py`

- **Capa de Software:** Ecosistema de Pruebas Automatizadas (Tests)
- **Resumen Estático:** Módulo enfocado en **Ecosistema de Pruebas Automatizadas (Tests)**.


——————————————————————————————

### 📄 `analisis\test\test_comparison_service.py`

- **Capa de Software:** Ecosistema de Pruebas Automatizadas (Tests)
- **Resumen Estático:** Módulo enfocado en **Ecosistema de Pruebas Automatizadas (Tests)**. Define 5 estructuras de objeto/clase. Implementa 14 funciones lógicas.

  **Estructuras de Clases:**
  - `TestCompararProductos`
  - `TestCalcularDiferencial`
  - `TestEjecutarComparacionClean`
  - `TestObtenerMicroorganismosCompartidos`
  - `TestObtenerMicroorganismosExclusivos`
  **Funciones de Procesamiento:**
  - `test_comparar_productos_basico()`
  - `test_comparar_productos_contiene_taxonomia()`
  - `test_comparar_productos_vacio()`
  - `test_dominantes_basico()`
  - `test_compartidos_basico()`
  - `test_exclusivos_basico()`
  - `test_diferencial_una_muestra()`
  - `test_diferencial_vacio()`
  - `test_comparacion_sin_muestras()`
  - `test_comparacion_tipo_invalido_default()`
  - `test_comparacion_nivel_invalido_default()`
  - `test_comparacion_top_n_fuera_rango()`
  - `test_compartidos_con_dos_muestras()`
  - `test_exclusivos_de_variedad()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas, pytest, analisis.models, analisis.services.business.comparison_service]`

——————————————————————————————

### 📄 `analisis\test\test_models.py`

- **Capa de Software:** Ecosistema de Pruebas Automatizadas (Tests)
- **Resumen Estático:** Módulo enfocado en **Ecosistema de Pruebas Automatizadas (Tests)**.


——————————————————————————————

### 📄 `analisis\test\test_models_comprehensive.py`

- **Capa de Software:** Ecosistema de Pruebas Automatizadas (Tests)
- **Resumen Estático:** Módulo enfocado en **Ecosistema de Pruebas Automatizadas (Tests)**. Define 7 estructuras de objeto/clase. Implementa 24 funciones lógicas.

  **Estructuras de Clases:**
  - `TestCultivoModel`
  - `TestVariedadClonModel`
  - `TestMuestraSueloModel`
  - `TestArchivoMolecularModel`
  - `TestResultadoTaxonomicoModel`
  - `TestCatalogoMicroorganismoModel`
  - `TestUsuarioModel`
  **Funciones de Procesamiento:**
  - `test_crear_cultivo_basico()`
  - `test_cultivo_nombre_unico()`
  - `test_cultivo_str()`
  - `test_crear_variedad()`
  - `test_variedad_relacion_cultivo()`
  - `test_variedad_unique_together()`
  - `test_variedad_mismo_nombre_distinto_cultivo()`
  - `test_crear_muestra()`
  - `test_muestra_sin_variedad()`
  - `test_muestra_cultivo_required()`
  - `test_muestra_fecha_registro_auto()`
  - `test_crear_archivo_16s()`
  - `test_crear_archivo_its()`
  - `test_archivo_tipos_analisis_validos()`
  - `test_crear_resultado_taxonomico()`
  - `test_resultado_valores_default()`
  - `test_resultado_relacion_archivo()`
  - `test_crear_catalogo_benefico()`
  - `test_crear_catalogo_patogeno()`
  - `test_clasificaciones_validas()`
  - `test_crear_usuario_admin()`
  - `test_crear_usuario_tecnico()`
  - `test_crear_usuario_agricultor()`
  - `test_usuario_str()`
  **Módulos / Dependencias Relacionadas:**
  - `[pytest, analisis.models, django.db]`

——————————————————————————————

### 📄 `analisis\test\test_pipeline.py`

- **Capa de Software:** Ecosistema de Pruebas Automatizadas (Tests)
- **Resumen Estático:** Módulo enfocado en **Ecosistema de Pruebas Automatizadas (Tests)**.


——————————————————————————————

### 📄 `analisis\test\test_pipeline_comprehensive.py`

- **Capa de Software:** Ecosistema de Pruebas Automatizadas (Tests)
- **Resumen Estático:** Módulo enfocado en **Ecosistema de Pruebas Automatizadas (Tests)**. Define 6 estructuras de objeto/clase. Implementa 23 funciones lógicas.

  **Estructuras de Clases:**
  - `TestCargarArchivo`
  - `TestValidarColumnas`
  - `TestLimpiarDatos`
  - `TestProcesarArchivoDf`
  - `TestProcesarArchivo`
  - `TestEdgeCases`
  **Funciones de Procesamiento:**
  - `test_cargar_csv_basico()`
  - `test_cargar_excel_basico()`
  - `test_cargar_archivo_invalido()`
  - `test_cargar_convierte_columnas_minusculas()`
  - `test_validar_columnas_validas()`
  - `test_validar_columnas_faltantes()`
  - `test_validar_columnas_parciales()`
  - `test_limpiar_espacios_en_blanco()`
  - `test_limpiar_valores_nulos()`
  - `test_limpiar_convierte_numericos()`
  - `test_limpiar_normaliza_species()`
  - `test_procesar_archivo_df_basico()`
  - `test_procesar_archivo_df_top_n()`
  - `test_procesar_archivo_df_preserva_taxonomia()`
  - `test_procesar_archivo_df_niveles_validos()`
  - `test_procesar_archivo_df_nivel_invalido_default()`
  - `test_procesar_archivo_df_top_n_opciones_validas()`
  - `test_procesar_archivo_df_numeros_validos()`
  - `test_procesar_archivo_csv()`
  - `test_procesar_archivo_excel()`
  - `test_procesar_dataframe_vacio()`
  - `test_procesar_un_solo_registro()`
  - `test_procesar_con_valores_nan()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas, pytest, numpy, io, analisis.services.processing.pipeline]`

——————————————————————————————

### 📄 `analisis\test\test_upload.py`

- **Capa de Software:** Ecosistema de Pruebas Automatizadas (Tests)
- **Resumen Estático:** Módulo enfocado en **Ecosistema de Pruebas Automatizadas (Tests)**.


——————————————————————————————

### 📄 `analisis\test\__init__.py`

- **Capa de Software:** Ecosistema de Pruebas Automatizadas (Tests)
- **Resumen Estático:** Módulo enfocado en **Ecosistema de Pruebas Automatizadas (Tests)**.


——————————————————————————————

### 📄 `analisis\views\analysis.py`

- **Capa de Software:** Controladores de Interfaz (Vistas/Views)
- **Resumen Estático:** Módulo enfocado en **Controladores de Interfaz (Vistas/Views)**. Implementa 3 funciones lógicas.

  **Funciones de Procesamiento:**
  - `analisis_avanzado()`
  - `resultado_analisis()`
  - `exportar_analisis()`
  **Módulos / Dependencias Relacionadas:**
  - `[services.business.visualization_service, services.business.analysis_service, pandas, services.business.statistics_service, models, django.contrib, services.business.comparison_service]`

——————————————————————————————

### 📄 `analisis\views\auth.py`

- **Capa de Software:** Controladores de Interfaz (Vistas/Views)
- **Resumen Estático:** Módulo enfocado en **Controladores de Interfaz (Vistas/Views)**. Define 2 estructuras de objeto/clase.

  **Estructuras de Clases:**
  - `CustomLoginView`
  - `CustomLogoutView`
  **Módulos / Dependencias Relacionadas:**
  - `[django.contrib.auth.views, django.urls]`

——————————————————————————————

### 📄 `analisis\views\catalogo.py`

- **Capa de Software:** Controladores de Interfaz (Vistas/Views)
- **Resumen Estático:** Módulo enfocado en **Controladores de Interfaz (Vistas/Views)**. Implementa 3 funciones lógicas.

  **Funciones de Procesamiento:**
  - `catalogo_microorganismos()`
  - `detalle_microorganismo()`
  - `actualizar_clasificacion()`
  **Módulos / Dependencias Relacionadas:**
  - `[services.business.catalog_service, django.contrib, django.views.decorators.http, django.shortcuts, django.http, django.contrib.auth.decorators, services.interpretation.microorganism_classifier]`

——————————————————————————————

### 📄 `analisis\views\comparison.py`

- **Capa de Software:** Controladores de Interfaz (Vistas/Views)
- **Resumen Estático:** Módulo enfocado en **Controladores de Interfaz (Vistas/Views)**. Implementa 2 funciones lógicas.

  **Funciones de Procesamiento:**
  - `_contar_clasificaciones()`
  - `comparar()`
  **Módulos / Dependencias Relacionadas:**
  - `[services.business.visualization_service, pandas, services.business.statistics_service, models, django.contrib, forms, services.business.comparison_service]`

——————————————————————————————

### 📄 `analisis\views\dashboard.py`

- **Capa de Software:** Controladores de Interfaz (Vistas/Views)
- **Resumen Estático:** Módulo enfocado en **Controladores de Interfaz (Vistas/Views)**. Implementa 1 funciones lógicas.

  **Funciones de Procesamiento:**
  - `dashboard()`
  **Módulos / Dependencias Relacionadas:**
  - `[services.business.visualization_service, pandas, services.business.statistics_service, models, pathlib, django.contrib, django.db.models]`

——————————————————————————————

### 📄 `analisis\views\historial.py`

- **Capa de Software:** Controladores de Interfaz (Vistas/Views)
- **Resumen Estático:** Módulo enfocado en **Controladores de Interfaz (Vistas/Views)**. Implementa 1 funciones lógicas.

  **Funciones de Procesamiento:**
  - `historial()`
  **Módulos / Dependencias Relacionadas:**
  - `[models, django.db.models, django.contrib, django.shortcuts, django.contrib.auth.decorators]`

——————————————————————————————

### 📄 `analisis\views\producto.py`

- **Capa de Software:** Controladores de Interfaz (Vistas/Views)
- **Resumen Estático:** Módulo enfocado en **Controladores de Interfaz (Vistas/Views)**. Implementa 1 funciones lógicas.

  **Funciones de Procesamiento:**
  - `ver_producto()`
  **Módulos / Dependencias Relacionadas:**
  - `[models, django.contrib.auth.decorators, django.shortcuts, django.contrib]`

——————————————————————————————

### 📄 `analisis\views\reportes.py`

- **Capa de Software:** Controladores de Interfaz (Vistas/Views)
- **Resumen Estático:** Módulo enfocado en **Controladores de Interfaz (Vistas/Views)**. Implementa 3 funciones lógicas.

  **Funciones de Procesamiento:**
  - `reportes()`
  - `generar_reporte()`
  - `detalle_reporte()`
  **Módulos / Dependencias Relacionadas:**
  - `[pandas, models, django.contrib, django.db.models, services.business.report_service, django.views.decorators.http, django.shortcuts]`

——————————————————————————————

### 📄 `analisis\views\subir_datos.py`

- **Capa de Software:** Controladores de Interfaz (Vistas/Views)
- **Resumen Estático:** Módulo enfocado en **Controladores de Interfaz (Vistas/Views)**. Implementa 1 funciones lógicas.

  **Funciones de Procesamiento:**
  - `subir_datos()`
  **Módulos / Dependencias Relacionadas:**
  - `[analisis.forms, django.contrib, analisis.services.business.upload_service, analisis.models, os, django.shortcuts, django.contrib.auth.decorators]`

——————————————————————————————

### 📄 `analisis\views\__init__.py`

- **Capa de Software:** Controladores de Interfaz (Vistas/Views)
- **Resumen Estático:** Módulo enfocado en **Controladores de Interfaz (Vistas/Views)**.

  **Módulos / Dependencias Relacionadas:**
  - `[analysis, historial, dashboard, comparison, producto, catalogo, reportes]`

——————————————————————————————

### 📄 `config\asgi.py`

- **Capa de Software:** Configuración / Infraestructura Core
- **Resumen Estático:** Módulo enfocado en **Configuración / Infraestructura Core**.

  **Módulos / Dependencias Relacionadas:**
  - `[django.core.asgi, os]`

——————————————————————————————

### 📄 `config\settings.py`

- **Capa de Software:** Controladores de Interfaz (Vistas/Views)
- **Resumen Estático:** Módulo enfocado en **Controladores de Interfaz (Vistas/Views)**.

  **Módulos / Dependencias Relacionadas:**
  - `[django.templatetags.static, os, pathlib]`

——————————————————————————————

### 📄 `config\urls.py`

- **Capa de Software:** Enrutamiento del Sistema (URLs)
- **Resumen Estático:** Módulo enfocado en **Enrutamiento del Sistema (URLs)**.

  **Módulos / Dependencias Relacionadas:**
  - `[django.contrib, django.conf.urls.static, django.views.i18n, django.conf, django.urls]`

——————————————————————————————

### 📄 `config\wsgi.py`

- **Capa de Software:** Configuración / Infraestructura Core
- **Resumen Estático:** Módulo enfocado en **Configuración / Infraestructura Core**.

  **Módulos / Dependencias Relacionadas:**
  - `[os, django.core.wsgi]`

——————————————————————————————

### 📄 `config\__init__.py`

- **Capa de Software:** Configuración / Infraestructura Core
- **Resumen Estático:** Módulo enfocado en **Configuración / Infraestructura Core**.


——————————————————————————————
