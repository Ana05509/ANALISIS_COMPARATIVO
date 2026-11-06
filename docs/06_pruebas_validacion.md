> Actualización 6-nov-2026: la suite completa actual pasa 156 pruebas con `--settings=config.settings_test`. Véase [correcciones de auditoría](auditoria_2026-11-06/correcciones.md). Las cifras anteriores de este documento describen la validación histórica.

# 6. Pruebas y validación

## 6.1 Pruebas automatizadas

Se ejecutan con el runner de Django:

```powershell
python manage.py test analisis.tests
```

**Resultado al 4-nov-2026: 47 pruebas, todas correctas (`OK`).** Las pruebas de validación contra scikit-bio se ejecutan solo si está instalado `requirements-dev.txt`; en esa ejecución estaba instalado y no se omitió ninguna.

> `pytest.ini` apunta a `analisis/test` y `tests`, que no existen, y ni `pytest` ni `pytest-django` están en los requirements. Hoy **no se puede usar pytest**: hay que usar `manage.py test` (defecto D-01).

| Clase | N.º | Qué valida |
|---|:---:|---|
| `PCoATests` | 7 | Las coordenadas reproducen las distancias; % de variación válidos; rechazo de matrices no cuadradas, asimétricas o con menos de 3 muestras; coincidencia con `skbio.stats.ordination.pcoa`, incluso con valores propios negativos |
| `BrayCurtisVectorizadoTests` | 1 | La matriz vectorizada es igual a la de la versión anterior (`scipy.spatial.distance.braycurtis` con bucles) |
| `LecturaArchivoTests` | 4 | CSV con coma, CSV con punto y coma, TSV, y error claro con un archivo ilegible |
| `PermanovaTests` | 8 | Estadísticos F iguales a los de scikit-bio; PERMDISP con dispersiones iguales o distintas, valor p mínimo y exclusión de grupos de una muestra; enumeración de reparticiones; potencia con grupos de 3 y de 5 |
| `DiversidadAlfaTests` | 4 | Shannon, Simpson y Pielou, con proporciones iguales y desiguales |
| `GraficoPCoATests` | 2 | El gráfico usa PCoA (y no MDS) y exige al menos 3 muestras |
| `AvisoProfundidadTests` | 3 | Aviso solo cuando la profundidad supera el doble; las muestras sin lecturas se ignoran |
| `ExportacionCatalogoTests` | 3 | Excel con hojas y contenido; CSV reimportable y protegido contra inyección de fórmulas |
| `BloqueoLoginTests` | 5 | Bloqueo tras 3 fallos, normalización del correo, reinicio del contador, expiración y correo vacío |
| `ContentSecurityPolicyTests` | 4 | Cabecera CSP en modo de solo aviso, directivas esenciales (`object-src`, `frame-ancestors`, `form-action`) y endpoint `/csp-report/` (registra el aviso, rechaza GET y cuerpos enormes) |
| `RegistroDominioTests` | 6 | Dominio `@utc.edu.ec` y sus subdominios, formulario, Google, y que la recuperación de contraseña no se restrinja |

**Sin cobertura automatizada:** las vistas completas (carga, análisis, comparación, reportes), la generación de PDF y Excel, el parser de PDF de bioquímica, la API y los permisos por rol. La cobertura no está medida [PENDIENTE DE CONFIRMAR].

## 6.2 Verificaciones manuales y semiautomatizadas (4-nov-2026, entorno local)

| Verificación | Método | Resultado |
|---|---|---|
| Instalación local | `manage.py check`, conexión a la base, migraciones pendientes | Sin problemas, 0 migraciones pendientes |
| Arranque del servidor | `runserver`, petición a `/` | HTTP 200 |
| Pantalla de aceptación de términos | Render y captura con Chromium sin interfaz | Textos completos visibles y desplegables |
| Adaptabilidad | Playwright: 26 rutas en anchos de 360, 375, 414, 768, 1024 y 1280 px, con un usuario temporal que se borró al terminar | Ninguna página desborda la pantalla. Se detectaron y corrigieron los defectos I-01 e I-02 |
| Gráficos en celular | Capturas de cada gráfico Plotly a 375 px y a 1280 px | Legibles en celular; en escritorio, sin cambios |
| Content Security Policy en modo bloqueo | Playwright: 32 páginas, descarga PNG y redirección del login con Google, registrando las violaciones de CSP, los fallos de SRI y los errores de JavaScript | 0 violaciones, 14 gráficos dibujados, iconos y descarga correctos |
| Figuras del artículo en español | Regeneradas desde los CSV; comparación de huellas MD5 de las figuras en inglés | Las figuras en inglés no cambiaron |

Las evidencias (capturas) quedaron en el directorio temporal de la sesión y **no forman parte de la entrega** [PENDIENTE: volver a capturarlas para el anexo, si se requieren].

## 6.3 Incidencias resueltas

| ID | Fecha | Incidencia | Solución |
|---|---|---|---|
| I-01 | 4-nov-2026 | En celular, una altura fija de 300 px aplastaba los gráficos Plotly con la leyenda y las etiquetas | Se sustituyó por `ChartTheme.adaptarLayoutMovil` (leyenda abajo, altura calculada) |
| I-02 | 4-nov-2026 | En Reportes, en celular, los nombres largos de taxón se cortaban | `overflow-wrap:anywhere` |
| I-03 | 4-nov-2026 | La pantalla de aceptación de términos no mostraba qué se aceptaba | Textos completos dentro de la misma pantalla |
| I-04 | 4-nov-2026 | El registro estaba abierto a cualquier correo | Restricción a `@utc.edu.ec` (RN-01) |
| I-05 | oct-2026 | XSS almacenado en plantillas de reportes y admin (`|safe` sobre JSON) | Filtro `json_embed` |
| I-06 | oct-2026 | `/media/` se servía sin control de acceso | Vista `media_protegida` |
| I-07 | oct-2026 | Detrás del proxy de Railway, el limitador de login veía una única IP para todos | `ALLAUTH_TRUSTED_PROXY_COUNT` |
| I-08 | oct-2026 | Si faltaba la variable, `DEBUG` quedaba en `True` | Ahora vale `False` por defecto |

## 6.4 Defectos conocidos y limitaciones

| ID | Severidad | Descripción | Recomendación |
|---|---|---|---|
| D-01 | Baja | `pytest.ini` está mal configurado (ver 6.1) | Corregir `testpaths` y añadir `pytest-django` a `requirements-dev.txt`, o eliminar el archivo |
| D-02 | Media | El contador de bloqueo de login usa la caché en memoria (no hay `CACHES` configurado): **cada worker de Gunicorn lleva su propio conteo**. Con varios workers (3 en el servidor propio) se pueden hacer más de 3 intentos antes del bloqueo | Configurar una caché compartida (base de datos o Redis) |
| D-03 | Media | El registro revela si un correo ya tiene cuenta (`ACCOUNT_PREVENT_ENUMERATION=False`) | Cambiar a `True` |
| D-04 | Media | La verificación del correo no es obligatoria | `ACCOUNT_EMAIL_VERIFICATION="mandatory"` cuando SMTP esté estable |
| D-05 | Baja | El `README.md` raíz muestra versiones antiguas (Django 5.1.6, etc.) | Actualizarlo o enlazarlo a esta documentación |
| D-06 | Baja | En celular, el gráfico de Reportes recorta la etiqueta del valor más alto, y el de barras comparativas deja un espacio en blanco entre el eje y la leyenda | Ajuste estético |
| D-07 | Baja | El análisis, la comparación y los reportes son síncronos: con muchas muestras pueden acercarse al `--timeout 180` | Medir con datos de producción y pasar a tareas en segundo plano si hace falta |

## 6.5 Criterios de aceptación

No se encontraron criterios de aceptación formales en el material [PENDIENTE DE CONFIRMAR]. Se proponen estos, para validarlos con usuarios reales en producción:

| # | Criterio | Rol | Estado |
|---|---|---|---|
| CA-01 | Un docente carga un archivo 16S y otro ITS reales y ve sus resultados en Análisis Avanzado | Docente | [PENDIENTE] |
| CA-02 | La comparación de 3 o más muestras muestra la PCoA y la PERMANOVA sin errores | Docente | [PENDIENTE] |
| CA-03 | Los reportes PDF y Excel se descargan y abren correctamente | Todos | [PENDIENTE] |
| CA-04 | Un estudiante no puede cargar datos ni descargar originales | Estudiante | Cubierto por el código (2.3); [PENDIENTE de prueba en producción] |
| CA-05 | Un PDF de bioquímica (propio y CIPAL) se registra con sus recuentos y aislamientos | Docente | [PENDIENTE] |
| CA-06 | 3 intentos fallidos bloquean el acceso 15 min | Todos | Cubierto por pruebas (lógica); [PENDIENTE en producción] |
| CA-07 | El registro con un correo que no es `@utc.edu.ec` se rechaza | Público | Cubierto por pruebas; [PENDIENTE de verificar en producción] |
| CA-08 | El sistema se usa en un celular sin desplazamiento horizontal y con gráficos legibles | Todos | Verificado en local; [PENDIENTE de verificar en producción] |
