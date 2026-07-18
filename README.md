# Sistema Web de Análisis Comparativo de Perfiles Microbianos (16S & ITS)

Plataforma bioinformática desarrollada en Django para el análisis, visualización e interpretación de datos metagenómicos de suelos agrícolas. Transforma resultados de secuenciación molecular (16S rRNA y ITS) en reportes interpretativos para la toma de decisiones en agricultura de precisión.

## Descripción

El sistema está orientado a investigadores, docentes y estudiantes que trabajan con comunidades microbianas del suelo. Permite cargar archivos de secuenciación, procesar la jerarquía taxonómica, comparar la biodiversidad microbiana entre muestras de distintos cultivos o variedades (ej. Cacao CCN51 vs. otros clones) y generar reportes descargables.


## Tecnologías

| Capa | Tecnología |
|---|---|
| Backend | Django 5.1.6 |
| Autenticación | django-allauth 65.2.0 |
| Admin UI | django-unfold 0.94.0 |
| Base de datos | PostgreSQL (psycopg2-binary 2.9.10) |
| Procesamiento | pandas 2.2.2 · numpy 2.0.2 · scipy 1.14.1 |
| Machine Learning | scikit-learn 1.5.2 |
| Gráficos | Plotly 5.24.1 · Matplotlib 3.9.2 |
| Reportes | ReportLab 4.2.2 · openpyxl 3.1.5 |
| Import/Export | django-import-export 4.3.1 · tablib[xlsx] |

---

## Funcionalidades

### Autenticación y Roles
- Login / Logout con soporte para recuperación de contraseña por correo.
- Tres niveles de acceso: **Administrador**, **Docente / Investigador** y **Estudiante**.
- Vistas del catálogo protegidas con `@login_required`.

### Carga de Datos
- Interfaz con **drag & drop** interactivo y barra de progreso en tiempo real.
- Soporte para archivos CSV y Excel (`.xlsx`).
- Validación automática de columnas taxonómicas: `Kingdom`, `Phylum`, `Class`, `Order`, `Family`, `Genus`, `Species`.
- Curación, normalización y cálculo de abundancias (`num_hits` y `%_hits`).
- Las muestras se asocian a un cultivo, variedad/clon, localidad, finca/lote y altitud.

### Análisis Avanzado
- Perfil taxonómico con rankings Top 5, 10, 25 y 50 microorganismos.
- Selección multi-muestra para análisis agregado.
- Cuatro gráficos interactivos (Plotly): composición taxonómica, abundancia relativa, diversidad y comparativa.
- Índices de diversidad (Shannon, Simpson y equitatividad de Pielou) calculados con `DiversityService`.
- Análisis diferencial: microorganismos **Dominantes**, **Compartidos** (Core) y **Exclusivos**.
- Exportación de resultados en Excel.

### Comparación entre Muestras
- Comparativa directa entre muestras de una misma especie o variedad.
- Identificación de taxa exclusivos y compartidos entre grupos seleccionados.

### Catálogo de Microorganismos
- Base de conocimiento con nombre científico, nivel taxonómico y marcador molecular (16S / ITS).
- Clasificación funcional: **Benéfico**, **Potencial fitopatógeno**, **Neutral** o **Sin clasificar**.
- Importación masiva desde archivo CSV/Excel con detección de duplicados.
- Vista de detalle con reclasificación en línea.
- Referencia bibliográfica asociada a cada entrada.

### Reportes
- Generación de reportes interpretativos a partir de los resultados de análisis.
- Visualización de detalle por reporte con ID único.
- Historial completo de análisis realizados por muestra.

---

## Estructura del Proyecto

```
ANALISIS_COMPARATIVO/
├── analisis/
│   ├── models.py               # Cultivo, VariedadClon, MuestraSuelo, ArchivoMolecular,
│   │                           # ResultadoTaxonomico, CatalogoMicroorganismo, Usuario
│   ├── views/
│   │   ├── auth.py             # Login / Logout personalizados
│   │   ├── dashboard.py        # Vista principal
│   │   ├── subir_datos.py      # Carga de archivos moleculares
│   │   ├── analysis.py         # Análisis avanzado y exportación
│   │   ├── comparison.py       # Comparación entre muestras
│   │   ├── catalogo.py         # Catálogo de microorganismos
│   │   ├── reportes.py         # Generación y detalle de reportes
│   │   ├── historial.py        # Historial de análisis
│   │   └── producto.py         # Detalle de producto/muestra
│   ├── services/
│   │   ├── business/
│   │   │   ├── analysis_service.py       # Análisis taxonómico avanzado y diferencial
│   │   │   ├── visualization_service.py  # Generación de gráficos Plotly
│   │   │   ├── comparison_service.py     # Lógica de comparación entre muestras
│   │   │   ├── report_generation_service.py  # Construcción de reportes
│   │   │   ├── upload_service.py         # Pipeline de carga y validación
│   │   │   ├── catalog_service.py        # Gestión del catálogo
│   │   │   └── export_service.py         # Exportación a Excel
│   │   └── processing/
│   │       ├── pipeline.py     # Pipeline bioinformático principal
│   │       ├── abundance.py    # Cálculo de abundancias y comparativas
│   │       └── diversity.py    # Índices de diversidad (Shannon, Simpson, Pielou)
│   ├── templates/analisis/     # HTML de todas las vistas
│   ├── admin.py                # Admin personalizado (django-unfold)
│   └── urls.py                 # Rutas de la aplicación
├── manage.py
└── requirements.txt
```

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone <url-del-repositorio>
cd ANALISIS_COMPARATIVO

# 2. Crear y activar entorno virtual
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # Linux / macOS

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno (BASE DE DATOS, SECRET_KEY, etc.)
# Copiar .env.example a .env y editar los valores

# 5. Aplicar migraciones
python manage.py migrate

# 6. Crear superusuario
python manage.py createsuperuser

# 7. Iniciar servidor
python manage.py runserver
```

---

## Rutas Principales

| Ruta | Descripción |
|---|---|
| `/` | Dashboard principal |
| `/subir/` | Carga de archivos de secuenciación |
| `/comparar/` | Comparación entre muestras |
| `/analisis-avanzado/` | Análisis taxonómico con gráficos interactivos |
| `/historial/` | Historial de análisis |
| `/catalogo/` | Catálogo de microorganismos |
| `/catalogo/importar/` | Importación masiva al catálogo |
| `/reportes/` | Generación y descarga de reportes |
| `/admin/` | Administración (django-unfold) |
