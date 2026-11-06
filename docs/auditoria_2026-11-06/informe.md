# Auditoría multidisciplinaria de BioMicro

> Este informe conserva los hallazgos del estado inicial. Consulte el [estado de las correcciones y su validación](correcciones.md) para el código actualizado.
Fecha: 6 de noviembre de 2026 (America/Bogota).
Repositorio local: ANALISIS_COMPARATIVO. Rama: correcciones/calculos-agronomicos.
HEAD observado: 76fca33, más los cambios locales de Claude sin commit.

## Dictamen y alcance
El uso previsto, confirmado por el responsable, es investigación y docencia; se excluyen decisiones diagnósticas y agronómicas operativas. El sistema tiene una estructura útil para ese propósito, pero esta revisión **no permite declararlo seguro, científicamente validado para su uso previsto, ni históricamente reproducible**. Hay defectos confirmados en autorización de originales, conservación de resultados, importación y estadísticas. Resolverlos y volver a verificar es condición previa recomendada para integrar/desplegar estos cambios. No se ha demostrado que producción haya sido explotada ni que sus muestras actuales estén incorrectas.

La auditoría cubrió documentación, configuración, dependencias instaladas, modelos/migraciones, rutas web/API/admin, procesamiento, reportes y eliminación. Se dividió en revisiones de seguridad, ciencia y arquitectura, consolidando evidencias y reproducciones. El texto adjunto termina en “Compatibilidad entre referencia, índices”; no se inventaron las secciones faltantes.

Alcance reconstruido de docs/01_resumen_proyecto.md:1 y docs/02_requisitos.md:1:
- BioMicro: análisis comparativo de comunidades microbianas de suelos agrícolas.
- Usuarios: administrador, docente/investigador y estudiante. Acceso a análisis globales según las reglas documentadas.
- Entrada molecular: tablas ya clasificadas, CSV/TSV/XLS/XLSX, 16S e ITS, hasta 10 MiB por carga habitual.
- Entrada microbiológica: PDF MAg y CIPAL, hasta 20 MiB por PDF; también ingreso manual.
- Salidas: perfiles taxonómicos, alfa/beta/gamma, Bray-Curtis, PCoA, PERMANOVA/PERMDISP, PDF y Excel.
- Django, PostgreSQL, pandas/NumPy/SciPy, Plotly/Matplotlib, ReportLab/openpyxl, allauth y Unfold.
- El responsable confirma que el sistema fue desplegado en Railway. No se verificaron la rama/revisión actualmente desplegada ni su configuración efectiva. Nginx/systemd son una alternativa suministrada en deploy/.
- Dimensionamiento comunicado por el responsable: máximo esperado de 10 MB por archivo y estimación inicial de 214 cuentas en total, con concurrencia aún desconocida (confirmado por el responsable). Pendiente definir volumen acumulado/frecuencia de cargas y medir concurrencia. El dato de 10 MB no cambia por sí solo el límite actual de 20 MiB de PDF; su aplicación a todos los formatos debe confirmarse.
- Uso previsto confirmado: investigación y docencia, sin decisiones diagnósticas ni agronómicas operativas. La evaluación no exige validación clínica; sí exige integridad de datos, métodos estadísticos correctos, trazabilidad y protección de acceso para ese uso.
- No aplican pruebas de FASTA/FASTQ, bases de calidad, R1/R2, BAM/CRAM o VCF: su procesamiento está fuera del alcance de esta versión.

No se leyó directamente .env, no se consultaron originales personales/genéticos ni se modificaron datos de producción. Las pruebas adicionales usaron datos sintéticos y directorios temporales, sin peticiones de explotación externas. El arranque habitual de Django sí carga su configuración de entorno. La suite usa su base temporal de pruebas. No se ejecutaron bombas de descompresión, saturación ni pruebas destructivas. No se realizaron capturas/browser QA de esta revisión.

## Evidencia y verificaciones
Entorno efectivo: Windows, PowerShell, Python 3.13.1, Django 6.0.9, pandas 3.0.3, NumPy 2.4.6, SciPy 1.17.1, scikit-bio 0.7.4.

Comandos ejecutados en esta sesión:
1. venv\Scripts\python.exe manage.py check — sin problemas.
2. venv\Scripts\python.exe manage.py makemigrations --check --dry-run — “No changes detected”.
3. venv\Scripts\python.exe -m pip check — “No broken requirements found”.
4. venv\Scripts\python.exe manage.py test --noinput — 124 pruebas; 46 fallos y 13 errores con redirección HTTPS activa en la configuración local. Las respuestas 301 interfieren con las expectativas de vistas.
5. Repetición con entorno de proceso DJANGO_SETTINGS_MODULE=config.settings, DEBUG=True y SECURE_SSL_REDIRECT=False — **124 pruebas, OK, 68.941 s**. No se editó .env. El resultado acredita esa configuración local, no Railway.
6. Siete pruebas aisladas sin base de datos de test_calculos — OK.
7. venv\Scripts\python.exe scripts/auditoria_sintetica.py — finalizó con código 0; resultados guardados en [evidencia_sintetica.json](evidencia_sintetica.json). Reproduce importación numérica, muestras vacías, riqueza, UFC, autorización media, markup PDF, permutaciones y asociación de aislados.

El warning de división por cero de scikit-bio en el caso degenerado de PERMANOVA es esperado en esa comparación: representa F infinito en algunas permutaciones. No es un fallo de ejecución del script.

Las pruebas existentes no bastan para afirmar ausencia de defectos: los casos sintéticos adicionales reproducen problemas mientras las 124 pruebas pasan. No se midió cobertura. pip check revisa compatibilidad de dependencias, no vulnerabilidades. No se realizó un inventario completo de CVE de todos los paquetes.

## Recorrido de los archivos
| Etapa | Implementación y controles | Brecha |
|---|---|---|
| Recepción molecular | views/subir_datos.py, SubirDatosForm y upload_service.validar_archivo: sesión, rol, formato nominal y tamaño | El admin usa otra ruta y otros controles |
| Lectura/validación | pandas read_csv/read_excel; pipeline exige columnas y limpia texto | Validación semántica numérica insuficiente; sin balance de filas rechazadas |
| Persistencia | Muestra → ArchivoMolecular → ResultadoTaxonomico; transacción y bloqueo de muestra existente | Sin unicidad muestra/marcador de BD, checksum ni versión inmutable |
| Almacenamiento | FileSystemStorage en media/; compensación al fallar carga habitual | Volumen Railway y restauración no verificados; borrado ordinario deja huérfanos |
| PDF microbiológico | pdfplumber → estructura → transacción de ensayo/recuentos/aislados | Límites de extracción y asociación/parseo incompletos |
| Consulta | vistas, API de sesión y servicios de cálculo | API muestras sin paginación; media autoriza antes de canonicalizar |
| Visualización | porcentajes desde conteos, Plotly, PCoA | Vacíos tras filtrado y discrepancias de conteos; UI no revisada en navegador |
| Exportación | PDF ReportLab y XLSX openpyxl; Excel tiene escape de fórmulas | Texto externo interpretado como markup PDF; reporte se recalcula con catálogo actual |
| Reemplazo/eliminación | upload_service valida antes de escribir y borra antiguo tras commit | Admin puede perder resultados al fallar; sin política uniforme de retención |

## Hallazgos confirmados y remediación
Severidad: alta = afecta autorización, integridad de resultados o inferencias; media = alcance condicionado, trazabilidad parcial o controles inconsistentes; baja = mantenibilidad/documentación.
“Confirmado” significa comportamiento reproducido o propiedad comprobada en código/configuración. Un impacto externo no probado se identifica expresamente.

### H01 — Alta — el control de rol de originales se puede eludir
Evidencia: config/urls.py:36–39.
Se evalúa startswith sobre la ruta recibida y luego serve_media la normaliza. Con estudiante sintético y CSV temporal: ruta directa restringida → 403; prefijo ./ o avatars/../ antes del mismo destino → 200. Evidencia JSON: media.
Afecta los prefijos moleculares y PDF. Se necesita sesión y conocer/deducir la ruta. Confirmado en handler local; normalización del proxy real no verificada.
Remediación: canonicalizar y validar una única ruta antes de autorizar y servir; mantener contención en MEDIA_ROOT. Aceptación: todas las variantes del mismo recurso respetan el rol, incluyendo codificación, puntos y separadores.

### H02 — Alta — datos externos se interpretan como markup en PDF
Evidencia: export_service.py:1242–1244,1301–1305,1727–1729; forms.py:21–30.
_safe solo convierte a str; localidad, finca y otros textos llegan a Paragraph sin escape XML. Una sonda interceptando ImageReader confirma que una etiqueta img suministrada al parser intenta resolver una URL sintética. **No se hizo la petición**, ni se demostró extracción de datos. Markup interpretado confirmado; SSRF/acceso a imágenes locales son impactos potenciales.
Remediación: escapar todos los valores no confiables antes de Paragraph; reservar markup para plantilla fija y restringir fuentes de imágenes. Aceptación: nombres/observaciones con etiquetas se muestran como texto y no activan ImageReader.

### H03 — Alta — fallo de reemplazo desde admin puede eliminar resultados válidos
Evidencia: analisis/admin.py:232–239,300–312.
_disparar_pipeline borra resultados antes de leer/validar; atomic local comienza después. save_model guarda primero y captura excepciones sin abortar la operación. Reproducción con mocks: DELETE resultados ocurre antes del error sintético de lectura. No se borraron resultados reales.
Remediación: unificar servicio web/admin, validar primero y sustituir dentro de transacción con rollback ante fallo. Aceptación: carga corrupta conserva original y resultados previos; sin archivo nuevo huérfano.

### H04 — Alta — normalización numérica altera silenciosamente la entrada
Evidencia: pipeline.py:65–70,85.
num_hits=1.9 se convierte en 1; texto no numérico y negativos desaparecen; %_hits=999 se conserva. JSON: pipeline. En carga mezclada puede existir éxito con pérdida de filas, sin enumerar rechazos.
Los análisis principales recalculan porcentajes desde conteos, por lo que no se atribuye a todas las vistas el uso directo de 999%.
Remediación: finitud, integralidad, dominio y límites; error con fila/columna o cuarentena explícita; definir si el porcentaje se recalcula o se contrasta con tolerancia. Aceptación: ningún cambio o descarte silencioso; resumen leído/aceptado/rechazado.

### H05 — Alta — muestras sin taxones producen estadísticos no finitos
Evidencia: analysis_service.py:299–320; diversity.py:143–157,307–324; visualization_service.py:172–179.
Dos vectores cero después de excluir no asignados producen NaN en Bray-Curtis. PERMANOVA acepta esa matriz: ejecutado=True, F no finito y p=0.1 con nueve permutaciones. JSON: cero.
Remediación: excluir/informar muestras sin abundancia asignada, validar matrices finitas y volver a evaluar tamaños/grupos; nunca emitir un resultado aparentemente válido con NaN. Evitar reemplazar NaN por cero sin justificación científica.

### H06 — Alta — PERMANOVA omite permutaciones extremas
Evidencia: diversity.py:307,321–324.
Cuando SS_dentro=0 devuelve None; esas permutaciones no suman al numerador, pero permanecen en el denominador. Caso sintético x=[0,0,1,1], grupos A/B/A/B, 999 permutaciones, semilla 42: F=0; sistema p=0.688; scikit-bio 0.7.4 p=1.0. JSON: permanova_permutaciones.
Remediación: definir explícitamente los casos degenerados, contar F infinito cuando corresponde y contrastar con implementación de referencia. Aceptación: casos repetidos, separaciones perfectas, todos idénticos y grupos mínimos con salida definida.

### H07 — Alta — PERMDISP no reproduce el método de referencia
Evidencia: diversity.py:430–455.
Se calculan una vez distancias a centroides y luego se permutan etiquetas sobre esas distancias fijas. scikit-bio 0.7.4 con test=centroid recalcula centroides/distancias por permutación.
Caso sintético euclidiano con 12 puntos, semilla de datos 5, 499 permutaciones y semilla 42: mismo F=7.2278; aplicación p=0.006; referencia p=0.124. Cambia la decisión al 5%. JSON: permdisp_metodo.
No se afirma que toda estrategia alternativa sea inválida: no está especificada ni validada la diferencia del método presentado al usuario.
Remediación: elegir/documentar algoritmo y contrastarlo con referencia fijada. Después reevaluar advertencias sobre PERMANOVA.

### H08 — Alta — el parser PDF cambia valores UFC
Evidencia: bioquimica/services/pdf_parser.py:15–17,61–71; bioquimica/models.py:94.
3 x 10^6 UFC/g → coeficiente 6, exponente 0; 3 x 10-2 → coeficiente 2, exponente 0. <10 y <100 coinciden con el patrón de <1 y se presentan así. JSON: ufc.
La mejora A8 de superíndices corrige presentación del modelo, no este parser.
Remediación: aceptar notaciones expresamente soportadas o rechazar sin reinterpretar fragmentos; almacenar límite de detección numérico y texto original. Aceptación con fixtures de laboratorio anonimizados y variantes sintéticas contratadas.

### H09 — Alta — varias identificaciones en una página pueden mezclar resultados
Evidencia: pdf_parser.py:194–251.
Primero se escanean todos los encabezados y después todas las tablas de la página. org_actual queda en el último organismo. Sonda con dos organismos y dos tablas: primero recibe cero pruebas; último recibe ambas. JSON: asociacion_aislados.
No se verificó que los PDF actuales tengan esa disposición.
Remediación: asociación por bloques/posición y revisión previa de lo extraído. Rechazar layouts ambiguos.

### H10 — Alta — falta garantía de un archivo vigente por muestra/marcador
Evidencia: models.py:97–113; admin.py:264–267,300–303; analysis_service.py:33–43.
ArchivoMolecular._meta.constraints está vacío. El servicio habitual evita duplicados y bloquea muestra existente, pero el admin permite otra entrada del mismo marcador. Los cálculos suman todos sus resultados.
Remediación: unicidad de BD tras revisar duplicados o modelo explícito de versiones/ejecución vigente. Aceptación: concurrencia y todas las rutas de escritura preservan la regla. No se insertaron duplicados reales.

### H11 — Alta para reproducibilidad — no se conserva una ejecución inmutable
Evidencia: models.py:97–142; upload_service.py:240–268; analysis_service.py:22–30; views/reportes.py:365–427; views/historial.py:23–47.
No se fija hash del original, revisión de código/pipeline, catálogo, referencias, parámetros y artefactos en una ejecución. El reemplazo elimina resultados y original anterior; descargar de nuevo usa catálogo actual. La auditoría de cambios no constituye por sí sola el snapshot científico completo.
Remediación: entidad de ejecución versionada con hashes, entradas, referencia externa/QC, dependencias, catálogo, parámetros/semillas, resultados y archivos derivados. Aceptación: regenerar un informe histórico tras editar catálogo sin cambiar su contenido científico original.

### H12 — Media, actualizar antes del despliegue — parche Django pendiente
Evidencia: requirements.txt:10 e introspección: Django 6.0.9.
El aviso oficial del 3-nov-2026 publica 6.0.10 y describe consumo de memoria al procesar multipart base64, independientemente del límite de memoria de uploads. El proyecto recibe multipart. Confirmada dependencia anterior al parche; no se explotó ni se midió impacto.
Remediación: actualizar a parche compatible, reinstalar/verificar y ejecutar regresión. No se atribuyen al proyecto los avisos de GIS u otros componentes que no usa.
Fuente y fecha: [aviso oficial Django, consultado 6-nov-2026](https://www.djangoproject.com/weblog/2026/nov/03/security-releases/).

### H13 — Media — el sufijo institucional no acredita posesión de cuenta
Evidencia: signup_form.py:51–63; adapter.py:55–63; views/auth.py:9; backends.py:36; configuración allauth efectiva OPTIONAL.
El registro valida dominio; el login propio comprueba contraseña/activo sin exigir verificación de correo. No se registró ninguna cuenta en esta auditoría.
Impacto condicionado: si el acceso exige pertenencia institucional, la política no queda satisfecha solo con un sufijo.
Remediación: acordar identidad requerida y verificarla también en el login personalizado; solo cambiar el ajuste allauth puede no cubrir ese login.

### H14 — Media — presupuestos insuficientes para parsers y cómputo
Evidencia: upload_service.py:27–31,51; bioquimica/views.py:414,551; pdf_parser.py:527–535; gunicorn.conf.py:18–21.
Hay límite de bytes recibidos, pero no de filas/celdas/descompresión XLSX, páginas PDF, número de documentos, CPU o RAM de extracción. Un worker síncrono y timeout 180 s no sustituyen estos controles. La config Nginx alternativa sí limita el cuerpo total a 25 MiB; no se verificó equivalente Railway.
Riesgo de indisponibilidad por diseño; no se agotaron recursos.
Remediación: presupuestos explícitos, aislamiento, cola con estados/cancelación, límites de concurrencia y observabilidad según volúmenes esperados.

### H15 — Media — eliminación lógica no limpia todos los originales
Evidencia: ArchivoMolecular FileField en models.py:108; ausencia de listeners pre/post_delete comprobada; limpieza localizada en upload_service.py:267–268 y bioquimica/views.py:504–511.
Borrado ordinario desde admin no incorpora eliminación física uniforme. Django documenta que borrar un modelo no borra automáticamente sus archivos. No se ejecutó borrado real.
Remediación: política de retención y limpieza posterior al commit, reconciliación de huérfanos y registro/reintentos. No ejecutar una purga indiscriminada: deben preservarse históricos y evidencias según política acordada.

### H16 — Media — límites de altitud inconsistentes por vía de entrada
Evidencia: forms.py:33–35; models.py:74; admin.py:146–162.
El formulario de carga restringe 0–6500; el del admin acepta -1 y 9000. Reproducción sin BD guardada en integridad_modelos.
Remediación: validadores comunes de modelo y CheckConstraint si se exige garantía de BD. Esto sí puede requerir migración. No convertir ceros históricos sin conocer su procedencia.

### H17 — Media — riqueza del diferencial incluye no asignados
Evidencia: diversity.py:14–18,121–122.
Bacillus + Unclassified produce total_taxa_reales_a/b=2 mientras compartidos devuelve solo bacillus. JSON: riqueza_diferencial.
Remediación: usar el mismo conjunto asignado y positivo para los conteos, conjuntos y etiquetas; preservar aparte las lecturas sin asignar.

### H18 — Media — clasificación funcional no informa inferencia o ambigüedad
Evidencia: constants.py:134–168; analysis_service.py:12–19.
Se permite coincidencia por epíteto aislado o género; si no hay nivel solicitado, se devuelve catálogo de otros niveles. No se presenta al consumidor qué coincidencia produjo la etiqueta.
No se demostró una clasificación biológica equivocada en muestras actuales.
Remediación: coincidencia exacta e identificador taxonómico cuando exista; informar taxón fuente, nivel, referencia y carácter inferido; no tratar un epíteto aislado como identidad inequívoca.

### H19 — Media — índice de salud emite juicio sin cobertura funcional
Evidencia: views/reportes.py:29–46,128,192; test_calculos.py:86–87.
Con benéficos=0, fitopatógenos=0 y Shannon=0 resulta 35, “EN RIESGO”. La fórmula declara pesos 70/30 y divisor 3.5 sin calibrar. Ausencia de evidencia funcional queda convertida en una etiqueta de riesgo.
Remediación: estado no estimable/cobertura insuficiente, cobertura del catálogo y fracción sin asignación visibles; calibración y validación para el uso previsto. Las etiquetas agronómicas no acreditan diagnóstico.

### H20 — Media — coherencia cultivo/variedad depende del formulario
Evidencia: models.py:61–68; admin.py:146–162,199–208; upload_service selección de variedad por cultivo.
Dos FK independientes, sin clean común que garantice pertenencia. La carga habitual filtra correctamente; el admin usa el cultivo actual al editar y no valida la relación de forma uniforme.
Riesgo por código; no se insertó una muestra incoherente.
Remediación: validación de dominio en modelo/servicio y queryset de formulario según POST, más pruebas de alta/edición.

### H21 — Baja — configuración de pruebas y documentación no describen el estado actual
Evidencia: pytest.ini:4 y requirements-dev.txt:1; README.md:14–18; docs/06_pruebas_validacion.md:10–26; docs/02_requisitos.md RN-09.
testpaths apunta a carpetas inexistentes, pytest/pytest-django no declarados; README lista versiones distintas; docs todavía hablan de 47 o 105 pruebas y de incluir no asignados en alfa.
Remediación: runner único y comando reproducible, configuración de pruebas aislada de producción/SMTP, actualizar matriz requisito-prueba y metodología antes de entregar.

## Riesgos operativos y decisiones pendientes
- **Backups/restauración no acreditados.** docs/07_operacion_mantenimiento.md:43–44 deja por confirmar Railway. El script alternativo deploy/scripts/respaldo.sh hace pg_dump y luego tar media, sin snapshot coordinado. Riesgo de instantes inconsistentes durante reemplazos; no se ejecutó.
- **Persistencia Railway no acreditada.** La documentación refiere volumen; no se comprobó montaje real, durabilidad tras redeploy ni recuperación. Mantener como no verificable, no afirmar pérdida actual.
- **Progreso de procesamiento simulado.** subir_datos.html:712–734 usa progreso real de transferencia y temporizador 75→93% para procesamiento. Mostrar fase indeterminada o telemetría de trabajo real.
- **Hilos y reportes.** gunicorn.conf.py permite gthread aunque sus comentarios advierten estado global Matplotlib. Revisar antes de aumentar hilos; no se probó mezcla concurrente de figuras.
- **API y escala.** api_muestras materializa lista sin paginación (api.py:34–69); no hay contrato de carga/SLA confirmado. No se declara fallo de rendimiento bajo volumen real sin medición.
- **Catálogo importado.** catalog_service.py normaliza nivel desconocido a genus y marcador inválido a 16S; registra errores por fila sin transacción global. Requiere confirmar política de importación parcial y reporte de cambios para evitar reclasificaciones no intencionales.
- **Diseño experimental.** analysis_service.py:286–297 elige cultivo o variedad automáticamente como grupo. No se acredita diseño, bloques, independencia o suficiencia de réplicas para cada estudio.
- **Metadatos.** MuestraSuelo no fija fecha de muestreo, GPS, profundidad, propietario/proyecto o corrida. EnsayoMicrobiologico usa nombre libre sin FK a la muestra molecular. Limita trazabilidad integrada; no se considera infracción legal automáticamente.
- **Datos compartidos.** API/vistas muestran datos globales a autenticados, según documentación. Sin requisito de segregación por proyecto no se declara IDOR por ese hecho.
- **CSP.** Por defecto reporte, con unsafe-inline/unsafe-eval. Endurecimiento pendiente; no constituye por sí solo un XSS demostrado.
- **Límites por IP.** LocMemCache no comparte estado entre workers; existe backend DB configurable. Bloqueo por cuenta sí es persistente.
- **Legales.** Textos institucionales contienen pendientes; no se verificó aprobación jurídica. No se emitió dictamen de cumplimiento ni se inventaron obligaciones. Ecuador es el contexto descrito; jurisdicciones y políticas efectivas deben confirmarse.

## Controles favorables
Separación views/business/processing; dependencias fijadas; PostgreSQL y FK PROTECT relevantes; CSRF, sesiones, HTTPS/HSTS y rechazo de clave de desarrollo en producción; permisos centralizados; bloqueo por cuenta atómico; validación de avatar con Pillow; escape de fórmulas Excel; JSON incrustado escapado; transacciones y compensación de archivos en carga habitual/PDF; pruebas de regresión y referencia existentes. Las brechas muestran aplicación desigual, especialmente en admin.

## Plan de corrección y criterios de cierre
| Orden | Trabajo | Verificación necesaria |
|---|---|---|
| Antes de integrar/desplegar | H01–H03 y parche H12 | Regresión de permisos, metadatos PDF, fallo de reemplazo conservando originales y resultados |
| Antes de inferencias científicas | H04–H09 y H17 | Casos sintéticos y fixtures anonimizados; comparación estadística documentada con referencia fijada |
| Integridad del dominio | H10, H16, H20 | Todas las rutas, concurrencia y constraints tras revisar datos existentes |
| Reproducibilidad | H11, H18, H19 | Snapshot de ejecución, catálogo y referencias; cobertura e índice no estimable cuando proceda |
| Operación | H13–H15, H21 y riesgos operativos | Identidad, límites, retención, restore ensayado y prueba Railway aislada |

Algunas correcciones propuestas requieren migraciones: unicidad/versionado, constraints, límite de detección numérico y ejecuciones. Que los cambios actuales de Claude no generen migraciones no implica que todas las remediaciones puedan hacerse sin ellas. No se hicieron migraciones ni ajustes de datos.

Información pendiente para cerrar la evaluación operativa:
1. Rama y revisión desplegadas en Railway; confirmar si existe un entorno de pruebas separado. El uso previsto ya quedó confirmado: investigación y docencia.
2. Se confirmaron 10 MB por archivo y 214 cuentas totales. Concurrencia aún desconocida; falta medirla y definir frecuencia de cargas, volumen acumulado, filas/celdas/páginas máximas y tiempos aceptables.
3. Entorno Railway de pruebas separado, almacenamiento, proxy/TLS, backup y RPO/RTO.
4. Requisitos de identidad, privacidad, segregación por proyecto, retención y borrado.
5. Formatos/layouts PDF contratados, referencias y QC externos del laboratorio, diseño experimental y criterios de validación.
6. Institución responsable, jurisdicciones y aprobación de textos/políticas aplicables.

No se modificó lógica de aplicación, dependencias, datos ni configuración de despliegue. Se añadieron únicamente este informe, evidencia sintética y el script de reproducción. No se hizo commit.

## Fuentes externas
Consulta: 6-nov-2026. Se usaron fuentes primarias; no sustituyen evidencia local.
- [Django 6.0, seguridad](https://docs.djangoproject.com/en/6.0/topics/security/): contenido subido no confiable y controles del navegador.
- [Django 6.0, FileField y eliminación](https://docs.djangoproject.com/en/6.0/ref/models/fields/): archivos no se borran automáticamente con el modelo (H15).
- [Django, parche 6.0.10 del 3-nov-2026](https://www.djangoproject.com/weblog/2026/nov/03/security-releases/): H12. No se extrapolaron avisos de GIS.
- [SciPy 1.17.0, Bray-Curtis](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.spatial.distance.braycurtis.html): definición de distancia; runtime probado 1.17.1 (H05).
- [scikit-bio 0.7.4 PERMANOVA](https://scikit.bio/docs/latest/generated/skbio.stats.distance.permanova.html): estadístico y regla de permutaciones (H06).
- [scikit-bio 0.7.4 PERMDISP](https://scikit.bio/docs/latest/generated/skbio.stats.distance.permdisp.html) e [implementación 0.7.4](https://github.com/scikit-bio/scikit-bio/blob/0.7.4/skbio/stats/distance/_permdisp.py): comparación H07. Misma versión instalada.
- [GSC, MIxS/MIMARKS](https://www.gensc.org/pages/standards/checklists.html): guía de metadatos de marcadores ambientales; se propone como referencia de trazabilidad, no requisito legal ni obligación demostrada del proyecto.





