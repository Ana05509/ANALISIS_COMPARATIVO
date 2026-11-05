# 2. Requisitos del sistema

En este documento se recogen los requisitos **implementados**, reconstruidos a partir del código. No se encontró un documento de requisitos original con el que contrastarlos [PENDIENTE DE CONFIRMAR: si existe, adjuntarlo y conciliarlo con esta lista].

## 2.1 Requisitos funcionales

| ID | Requisito | Implementación |
|---|---|---|
| RF-01 | Autenticarse con correo y contraseña o con una cuenta de Google | `analisis/views/auth.py`, django-allauth |
| RF-02 | Aceptar los Términos de uso y la Política de privacidad vigentes antes de usar el sistema, leyendo los textos completos en la misma pantalla | `analisis/middleware.py` (`TerminosMiddleware`), `analisis/views/legal.py` |
| RF-03 | Registrar muestras de suelo con cultivo, variedad o clon, localidad, finca o lote y altitud | `analisis/views/subir_datos.py`, `upload_service.procesar_upload` |
| RF-04 | Cargar un archivo 16S o ITS (CSV, TSV, XLSX o XLS de hasta 10 MB) y validar sus columnas obligatorias | `upload_service.validar_archivo`, `pipeline.PipelineProcesamiento` |
| RF-05 | Normalizar el perfil taxonómico y guardarlo por taxón (`num_hits`, `%_hits`) | `pipeline.limpiar_datos`, modelo `ResultadoTaxonomico` |
| RF-06 | Mostrar el Top N (5, 10, 25 o 50) de taxones por nivel taxonómico para una o varias muestras | `views/analysis.py`, `constants.OPCIONES_TOP_N` |
| RF-07 | Calcular la diversidad alfa: riqueza, Shannon H′, Simpson (1−D) y Pielou J′ | `processing/diversity.py` |
| RF-08 | Comparar muestras: diversidad beta (Jaccard, Bray-Curtis), gamma, PCoA, PERMANOVA y PERMDISP | `diversity.py`, `views/comparison.py` |
| RF-09 | Identificar taxones dominantes, compartidos (core) y exclusivos | `comparison_service._calcular_diferencial` |
| RF-10 | Clasificar los taxones por función (benéfico, potencial fitopatógeno, neutral o sin clasificación) usando el catálogo | `CatalogoMicroorganismo`, `catalog_service.py` |
| RF-11 | Mantener el catálogo: reclasificar entradas e importarlas en masa desde CSV o Excel | `views/catalogo.py`, admin |
| RF-12 | Exportar el catálogo a Excel o CSV desde el panel de administración | `analisis/admin.py` |
| RF-13 | Generar reportes en PDF o Excel por nivel taxonómico (de una muestra, comparativo o global) y un Informe General de 7 niveles | `views/reportes.py`, `export_service.py` |
| RF-14 | Calcular el Índice de Salud del Suelo (0–100) | `reportes.calcular_indice_salud` |
| RF-15 | Registrar ensayos de microbiología clásica (recuento UFC y aislamiento) desde un PDF o con ingreso manual | `bioquimica/views.py`, `bioquimica/services/pdf_parser.py` |
| RF-16 | Visualizar los ensayos con gráficos (recuentos, series CIPAL, mapa de calor de pruebas) | `bioquimica/views.py` |
| RF-17 | Consultar los datos mediante la API REST de solo lectura | `analisis/views/api.py` |
| RF-18 | Auditar los inicios de sesión (exitosos y fallidos), los cierres de sesión y los cambios en los datos | `EventoAcceso`, `LogEntry`, django-simple-history |
| RF-19 | Gestionar los usuarios y sus roles desde el panel de administración | `UsuarioAdmin` |
| RF-20 | Descargar los gráficos en PNG (300 DPI) o SVG, en color o en escala de grises | `static/analisis/js/chart_theme.js` |

## 2.2 Requisitos no funcionales

| ID | Requisito | Implementación verificada |
|---|---|---|
| RNF-01 | Seguridad de las sesiones | La sesión expira tras 8 h de inactividad y al cerrar el navegador (`SESSION_COOKIE_AGE`, `SESSION_EXPIRE_AT_BROWSER_CLOSE`). |
| RNF-02 | HTTPS en producción | Con `DEBUG=False`: redirección a HTTPS, cookies `secure` y HSTS. El sistema no arranca si la `SECRET_KEY` es la de desarrollo. |
| RNF-03 | Protección contra fuerza bruta | 3 intentos fallidos con el mismo correo bloquean el acceso 15 min (`analisis/seguridad.py`), además del limitador de allauth (`10/m/ip`). |
| RNF-10 | Seguridad del navegador | Content Security Policy (`CSP_MODO`) y huellas de integridad (SRI) en todas las librerías que se cargan desde CDN, con la versión fijada |
| RNF-04 | Control de acceso a los archivos | `/media/` exige sesión. Los estudiantes no pueden descargar `archivos_moleculares/` ni `bioquimica_pdfs/`. Lo que no es imagen se sirve como descarga y no se abre en el navegador (`config/urls.py`). |
| RNF-05 | Idioma y zona horaria | Español (`LANGUAGE_CODE='es'`), `America/Guayaquil`. |
| RNF-06 | Adaptabilidad | La interfaz funciona entre 360 y 1280 px de ancho. Los gráficos se adaptan por debajo de 576 px. |
| RNF-07 | Exactitud científica | La PCoA se valida contra scikit-bio y Bray-Curtis contra SciPy en las pruebas automatizadas ([06](06_pruebas_validacion.md)). |
| RNF-08 | Rendimiento | Bray-Curtis vectorizado y PCoA por descomposición espectral, con mediciones en `resultados_benchmark/`. No hay un umbral de rendimiento definido [PENDIENTE DE CONFIRMAR]. |
| RNF-09 | Protección de datos personales | Política de privacidad basada en la LOPDP del Ecuador y registro de la aceptación con fecha, versión e IP. Los textos están por completar ([01](01_resumen_proyecto.md), 1.5). |

## 2.3 Roles y permisos

Los roles son los valores de `Usuario.rol`: `admin`, `docente` y `estudiante`. Al guardar un usuario desde el admin, `is_staff` se sincroniza con el rol: solo `admin` tiene acceso al panel.

| Acción | Administrador | Docente / Investigador | Estudiante |
|---|:---:|:---:|:---:|
| Ver el dashboard, análisis, comparación, historial, catálogo y reportes | ✅ | ✅ | ✅ |
| Generar reportes en PDF o Excel | ✅ | ✅ | ✅ |
| Consultar la API `/api/v1/` | ✅ | ✅ | ✅ |
| Cargar muestras y archivos 16S/ITS (`/subir/`) | ✅ | ✅ | ❌ |
| Registrar ensayos de bioquímica (PDF o manual) | ✅ | ✅ | ❌ |
| Ver los ensayos de bioquímica ya cargados | ✅ | ✅ | ✅ |
| Descargar los archivos originales (secuenciación y PDF de laboratorio) | ✅ | ✅ | ❌ |
| Reclasificar o importar el catálogo | ✅ | ❌ | ❌ |
| Acceder al panel `/admin/` (usuarios, auditoría, edición y borrado de datos) | ✅ | ❌ | ❌ |

Los permisos de staff se comprueban con `is_staff`, y los de carga y ensayos con `rol == 'estudiante'`.

## 2.4 Reglas de negocio

| ID | Regla | Ubicación |
|---|---|---|
| RN-01 | Las cuentas nuevas se crean con el rol `estudiante` y solo se aceptan correos del dominio `@utc.edu.ec` o de sus subdominios, tanto en el formulario como con Google. Las cuentas existentes de otros dominios no se ven afectadas. El dominio se configura con `REGISTRO_DOMINIOS_PERMITIDOS`. | `signup_form.py`, `adapter.py`, `settings.py` |
| RN-02 | El código de cada muestra es único. Cargar un código que ya existe se rechaza (`MuestraDuplicadaError`). | `MuestraSuelo.codigo`, `upload_service` |
| RN-03 | Una muestra puede tener archivos 16S e ITS. | `ArchivoMolecular.tipo_analisis` |
| RN-04 | Un cultivo o una variedad con muestras asociadas no se puede borrar (`on_delete=PROTECT`). Al borrar una muestra se borran en cascada sus archivos y resultados. | `models.py` |
| RN-05 | El nombre y el nivel del catálogo son únicos en conjunto (`unique_nombre_nivel`). | `CatalogoMicroorganismo` |
| RN-06 | La comparación exige al menos 2 muestras. Las estadísticas multimuestra (beta, gamma, PERMANOVA) solo aparecen en «Comparar». | `views/comparison.py`, `views/analysis.py` |
| RN-07 | Índice de Salud del Suelo = 70 % × benéficos / (benéficos + fitopatógenos) + 30 % × min(H′/3.5, 1), redondeado de 0 a 100. Niveles: ≥80 ÓPTIMO, ≥65 FAVORABLE, ≥50 MODERADO, ≥30 EN RIESGO y menor de 30 CRÍTICO. | `reportes.calcular_indice_salud` |
| RN-08 | Al cambiar `TERMINOS_VERSION`, todos los usuarios deben volver a aceptar los términos. | `analisis/seguridad.py` |
| RN-09 | La diversidad alfa se calcula sobre el perfil completo, incluida la categoría «sin clasificar», y no solo sobre el Top N. | `diversity.py`, `views/comparison.py` |

## 2.5 Trazabilidad entre requisitos, funcionalidades y pruebas

| Requisito | Prueba automatizada (`analisis/tests.py`) | Verificación manual |
|---|---|---|
| RF-01, RNF-03 | `BloqueoLoginTests` (5) | Bloqueo tras 3 intentos [PENDIENTE DE CONFIRMAR en producción] |
| RN-01 | `RegistroDominioTests` (6) | Registro con Gmail y con `@utc.edu.ec` [PENDIENTE] |
| RF-02 | — | Pantalla de aceptación revisada visualmente el 4-nov-2026 |
| RF-04 | `LecturaArchivoTests` (4) | — |
| RF-07, RN-09 | `DiversidadAlfaTests` (4), `AvisoProfundidadTests` (3) | — |
| RF-08 | `PCoATests` (7), `BrayCurtisVectorizadoTests` (1), `PermanovaTests` (8), `GraficoPCoATests` (2) | — |
| RF-12 | `ExportacionCatalogoTests` (3) | — |
| RNF-06 | — | Revisión automatizada con Playwright en 6 anchos (4-nov-2026) |
| RF-03, RF-05, RF-06, RF-09–RF-11, RF-13–RF-20 | **Sin prueba automatizada** | Requieren una prueba de aceptación ([06](06_pruebas_validacion.md), 6.4) |
