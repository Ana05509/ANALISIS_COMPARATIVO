# Correcciones de la auditoría — 6 de noviembre de 2026

Rama: `correcciones/calculos-agronomicos`. Uso: investigación y docencia.
Los cambios se apoyan en los de Claude; no se descartó su trabajo ni se hizo commit.

## Resultado comprobado
- **156 pruebas correctas**, incluidas **32 nuevas** en `analisis/test_auditoria.py`.
- Comando: `venv\Scripts\python.exe manage.py test --noinput --settings=config.settings_test`.
- Duración de la última suite completa: 34.097 s. Django 6.0.10, Python 3.13.1 y PostgreSQL.
- `manage.py check`: sin problemas; `makemigrations --check --dry-run`: sin cambios pendientes de generar; `pip check`: sin conflictos.
- Migraciones **0013 y 0014 aplicadas únicamente a PostgreSQL local**, después de verificar que HOST era local y de repetir esa comprobación dentro del comando de migración.
- No se modificó Railway, no se hizo merge ni push. No se ejecutó una prueba de carga ni una revisión visual en navegador.

## Cambios
| Hallazgo del informe inicial | Estado y comportamiento actual |
|---|---|
| H01, autorización media | Corregido: se normaliza el destino antes de comprobar rol, incluyendo separadores y mayúsculas |
| H02, markup PDF | Corregido: copia de presentación con textos externos escapados para las tres variantes de PDF; prueba intercepta cualquier intento de cargar imagen externa |
| H03, pérdida desde admin | Corregido: validación previa en formulario, sustitución atómica de resultados, rollback de la edición y limpieza del archivo nuevo; probado también fallo de persistencia |
| H04, números inválidos | Corregido: rechaza conteos negativos, fraccionarios, no finitos o fuera del entero de BD; porcentajes entre 0 y 100 y coherentes con conteos; identifica filas |
| H05, vacíos y NaN | Corregido: Bray-Curtis rechaza vacíos; PERMANOVA valida matriz; servicios excluyen muestras sin taxones positivos asignados y la comparación avisa cuáles |
| H06, PERMANOVA | Corregido: permutaciones con F infinito cuentan en la cola; F observado degenerado se informa como no ejecutable |
| H07, PERMDISP | Corregido: recalcula centroides y distancias por permutación; p sintético coincide con scikit-bio 0.7.4 |
| H08, UFC | Corregido: notación científica, signos y superíndices; conserva límites como <10 y <100 mediante coeficiente/exponente existentes; rechaza notación no reconocida |
| H09, mezcla de aislados | Corregida la asignación silenciosa: rechaza una página con varios organismos y exige ingreso manual o un organismo por página; no intenta adivinar la asociación |
| H10, duplicados | Corregido: unicidad de BD por muestra y marcador; preflight no destructivo detiene la migración si existen duplicados |
| H11, históricos | Nuevas emisiones congeladas con bytes, SHA-256 y manifiesto (datos, catálogo, hashes de código/dependencias y entradas). Reemplazos conservan original y resultados anteriores en revisión |
| H12, dependencia | Django actualizado e instalado en 6.0.10 |
| H14, presupuestos | Mitigación: 100 000 filas, XLSX hasta 100 MiB descomprimido, PDF hasta 10 MiB/100 páginas, lote hasta 10 PDF/20 MiB; sigue pendiente aislamiento de CPU/RAM y cola |
| H15, eliminación | Corregido para borrado explícito: limpieza tras commit, respeta referencias de revisiones conservadas y no elimina durante rollback |
| H16, altitud | Corregido en formulario admin, validadores de modelo y constraint de BD 0–6500 o nula; los ceros históricos no se convirtieron |
| H17, riqueza | Corregido: conjuntos y conteos excluyen no asignados y abundancia cero |
| H18, inferencias funcionales | Se eliminó la coincidencia por epíteto aislado y género; el catálogo queda limitado al nivel solicitado. Puede aumentar “sin clasificar” en especie |
| H19, índice sin cobertura | Devuelve `None, "NO ESTIMABLE"`; pantalla y reportes muestran ausencia de estimación, sin asignar “EN RIESGO” |
| H20, cultivo/variedad | Validación de modelo y formulario admin ajustado al cultivo enviado; conserva filtro de la carga habitual |
| H21, pruebas/documentación | Configuración aislada de pruebas, versiones de README y metodología actualizadas; pytest opcional declara sus plugins en requirements-dev. La ejecución validada fue el runner Django |

## Uso de los históricos
El admin incluye “Reporte archivado” y “Archivo molecular revision”, de solo lectura.
Cada respuesta de reporte añade `X-Reporte-ID`, `X-Reporte-SHA256` y `Content-Location`.
La URL autenticada `/reportes/archivo/<uuid>/` entrega exactamente los bytes guardados,
verifica la huella antes de descargarlos y aplica `Cache-Control: private, no-store`.

Los originales sustituidos se conservan mientras tengan una revisión que los referencie.
El borrado explícito de una muestra elimina sus revisiones y limpia archivos sin referencias
tras confirmar la transacción. Los reportes ya emitidos conservan su copia independiente.

El manifiesto registra ausencia del original si el archivo de una carga antigua ya faltaba;
no inventa su hash ni recupera archivos perdidos. El histórico empieza con estos cambios:
no reconstruye reportes anteriores no conservados. La procedencia/QC del laboratorio,
la referencia taxonómica externa y versiones de su pipeline siguen pendientes de incorporación.
La conservación del artefacto no equivale a una validación científica integral.

## Migraciones y despliegue
- 0013 añade validadores y constraints. Antes de cambiar esquema comprueba duplicados y altitudes inválidas; si existen, aborta y pide revisión, sin borrar registros.
- 0014 crea revisiones de archivos y reportes archivados.
- Ambas fueron comprobadas en la base temporal de pruebas y aplicadas en la base **local**.
- Railway aún requiere backup de PostgreSQL y media, ensayo en entorno separado, aplicación de migraciones y verificación de descarga, reemplazo, reportes y persistencia tras redeploy.
- Los históricos aumentan uso de disco/BD: deben entrar en el backup y la política de retención.

## Pendientes que no se resolvieron mediante cambios arbitrarios
- **H13, identidad institucional:** la verificación de correo sigue siendo opcional. Exigirla debe definir el tratamiento de cuentas existentes y el flujo de verificación/reenvío del login propio; no se bloquearon las cuentas actuales.
- Capacidad y tiempos de servicio: hay 214 cuentas previstas, concurrencia desconocida; requiere medición y prueba de carga aislada.
- CPU/RAM, procesamiento asíncrono, cancelación y reintentos de trabajos.
- Restauración, persistencia, proxy y configuración efectiva de Railway.
- Calibración y referencias del indicador exploratorio; no se ajustaron pesos sin datos.
- Metadatos de campo, diseño experimental, vínculo muestra/ensayo, políticas de acceso por proyecto y requisitos jurídicos institucionales.

La evidencia JSON del informe inicial es una fotografía **anterior** a las correcciones.
La referencia ejecutable del comportamiento corregido es la suite de regresión actual.

