# Rama `mejoras/seguridad-estabilidad`

Correcciones de seguridad, estabilidad y rendimiento de BioMicro, basadas en la revisión de código de noviembre de 2026.
Parte de `main` en `ac5592b`. **No está desplegada.** Producción sigue con `main` hasta que se haga el merge.

## 1. Qué cambia para quienes usan la web

| Cambio | Lo que nota el usuario |
|---|---|
| Mensajes y avisos sin HTML ejecutable | Nada visible. Un nombre de archivo, una columna, un código o una variedad con HTML ahora se muestran como texto. |
| Errores sin detalles internos | Ante un fallo inesperado aparece un mensaje claro en lugar de un texto técnico. El detalle queda en los logs de Railway. |
| Permisos por lista blanca | Igual que antes para estudiante, docente y administrador. Un rol desconocido ya no puede cargar datos. Un superusuario creado con `createsuperuser` (rol "estudiante" por defecto) ahora sí puede, como ya indicaba su menú. Los docentes ven el botón "Nueva Muestra" del dashboard, que antes dependía del rol inexistente "tecnico". |
| Bloqueo de login | Misma regla: 3 fallos en 15 minutos bloquean 15 minutos. Ahora se cumple aunque haya intentos simultáneos o varios procesos. |
| "Olvidé mi contraseña" | Responde igual exista o no la cuenta, y no envía correos a direcciones no registradas. |
| Cargas de archivos | Un archivo inválido no deja cultivos ni variedades creados. Un reemplazo borra del disco el archivo anterior. Un fallo a medias no deja archivos huérfanos. |
| Comparación y reportes | Mismos resultados, con menos consultas a la base de datos. |
| Ficha de muestra y API | Clasifican los géneros igual que los reportes y el dashboard. |

## 2. Verificación de los hallazgos de la revisión

Estados: **Confirmado** (reproducido con código o prueba), **Parcial**, **No reproducido**, **Pendiente** (falta información externa).

| # | Hallazgo | Estado | Evidencia | Acción |
|---|---|---|---|---|
| 1 | Un solo worker de Gunicorn | Confirmado en código; valor real pendiente | El `Procfile` no fija workers. Si `WEB_CONCURRENCY` no está definida en Railway, Gunicorn usa 1 | Configuración preparada (sección 5), **no aplicada** |
| 2 | Archivos subidos que se pierden en cada redespliegue | Pendiente | `docs/04` indica un volumen montado en `media/`; un comentario de `ver_pdf` sugiere pérdidas en el pasado | Verificar en Railway (sección 5.3). No se cambió el almacenamiento |
| 3 | XSS por `innerHTML` | Confirmado | En Chromium, contra `main`, se ejecutaron 3 `alert()` (columnas del archivo, toast, código de muestra); contra la rama, ninguno | Corregido |
| 4 | Enumeración de cuentas | Parcial | La recuperación de contraseña revelaba si la cuenta existía. En allauth 65.17 el registro sigue avisando "ya existe" salvo que la verificación de correo sea obligatoria | Recuperación corregida; registro pendiente de decisión |
| 5 | Errores con detalles internos | Confirmado | `str(exc)` llegaba al usuario. Además, con `DEBUG=False` Django **no registraba los errores 500** en ningún log | Corregido, con `LOGGING` |
| 6 | Cultivo o variedad sueltos tras una carga fallida | Confirmado | Pruebas de `analisis/test_cargas.py` | Corregido |
| 7 | Archivos huérfanos (reemplazo, fallo a medias, bioquímica) | Confirmado | Pruebas de carga molecular y de bioquímica; las 3 de bioquímica fallan con el código anterior | Corregido |
| 8a | Carrera en el bloqueo de login | Confirmado | Con 3 fallos, 2 de ellos simultáneos, la cuenta no se bloqueaba. `DatabaseCache` tampoco es atómico (`incr` = `get` + `set`) | Corregido con una tabla y una sentencia atómica |
| 8b | Carrera en cargas | Parcial | `update_or_create` ya bloqueaba la muestra; el hueco era la comprobación de duplicado fuera de la transacción | Corregido |
| 9 | Permisos por lista negra | Confirmado | El backend usaba `rol == "estudiante"` y las plantillas `is_staff or rol == "docente"` | Corregido |
| 10 | `cargar_variedades` responde 500 con un id no numérico | Confirmado | Prueba | Corregido |
| 11 | Recalculos y consultas por muestra | Confirmado | Reportes 34 → 21 consultas, comparar 42 → 16, Excel 62 → 41 (6 muestras) | Corregido |
| 12 | `iterrows()` en el pipeline | Confirmado | 50 000 filas: 3,09 s → 0,75 s, registros idénticos | Corregido |
| 13 | Clasificación distinta en la ficha y la API | Parcial | 0 diferencias con los datos locales; divergencia demostrada con un nombre repetido en dos niveles del catálogo | Corregido |
| 14 | Jaccard (similitud) mostrado junto a Bray-Curtis (disimilitud) | No reproducido | La interfaz rotula "Similitud" y "Disimilitud" | Sin cambios |
| 15 | PDFs procesados dentro de la petición | Confirmado | Diseño actual | Pendiente: requiere una cola de tareas, fuera de este alcance |
| 16 | `api_muestras` sin paginación | Confirmado | — | Sin cambios, para no romper el contrato de la API |
| 17 | Contraseña de BD por defecto `'ABCDE'` en `settings.py` | Confirmado | Solo para desarrollo local | Sin cambios: quitarla rompe el entorno local actual. Recomendado: `DB_PASSWORD` en `.env` |
| 18 | Bloque "DIAGNOSTICO EMAIL" temporal | Confirmado | No registra secretos | Sin cambios (decisión pendiente) |
| 19 | `_ip_cliente` usa una API interna de allauth | Confirmado | Funciona en 65.17 | Sin cambios; revisar al actualizar allauth |
| 20 | Módulos grandes (`export_service.py`, `admin.py`) | Confirmado | — | Sin dividir: no hacía falta para estas correcciones |

## 3. Commits

1. `78e316c` Datos no confiables como texto (toast, carga, vista previa, lista de PDFs).
2. `8e406de` Errores sin detalles internos y `LOGGING`.
3. `41db6ba` Permisos por lista blanca (`analisis/permisos.py`) y validación de parámetros.
4. `618d441` Bloqueo de login atómico (`BloqueoLogin`) y prevención de enumeración.
5. `de4dbee` Cargas atómicas y limpieza de archivos (moleculares y bioquímica); pipeline vectorizado.
6. `7570469` Menos consultas en comparación y reportes, con resultados idénticos.
7. `483288d` Clasificación unificada en la ficha de muestra y la API.
8. `a30eef7` Pruebas de PDF y Excel.
9. `b8ad9c5` `gunicorn.conf.py`, caché configurable y `Procfile`.

## 4. Migraciones, ajustes y variables

**Migración `analisis.0012_bloqueo_login`**: solo crea la tabla `analisis_bloqueologin`. No modifica datos existentes y se aplica sola con el `migrate` del `Procfile`.
Al aplicarla, los contadores de intentos fallidos empiezan de cero, porque antes vivían en memoria.

**Nueva app instalada**: `django.contrib.postgres` (necesaria para `ArrayField`). No tiene modelos.

**Variables de entorno nuevas** (todas opcionales; sin ellas el comportamiento es el actual):

| Variable | Por defecto | Uso |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Nivel de los logs |
| `WEB_CONCURRENCY` | `1` | Workers de Gunicorn |
| `GUNICORN_THREADS` | `1` | Hilos por worker; **dejar en 1** (ver 5.1) |
| `GUNICORN_TIMEOUT` | `180` | Segundos |
| `GUNICORN_MAX_REQUESTS` | `0` | Reciclar el worker tras N peticiones (0 = nunca) |
| `CACHE_BACKEND` | `local` | `db` para compartir el caché entre workers |

**`Procfile`**: ahora usa `gunicorn.conf.py` y ejecuta `createcachetable`, que no hace nada mientras `CACHE_BACKEND` sea `local`.

## 5. Infraestructura (preparada, no aplicada)

### 5.1 Concurrencia

- Medido en local (Windows, 6 muestras): cada worker ocupa unos **160 MB en reposo** y llega a unos **280 MB** al generar un Excel con gráficos (Kaleido abre Chromium). En Linux y con más muestras puede ser más.
- **Hilos: 1.** Los reportes usan `matplotlib.pyplot`, que tiene estado global (`plt.rcParams`, y `plt.tight_layout()` actúa sobre la figura "actual"), así que dos hilos podrían mezclar figuras. Para atender más peticiones a la vez hay que usar **procesos** (`WEB_CONCURRENCY`). Además, los cálculos son de CPU: los hilos tampoco los acelerarían por el GIL de Python.
- Regla orientativa: `WEB_CONCURRENCY ≤ (RAM del plan − 300 MB de margen) / 350 MB`, y no más que el número de vCPU + 1. Por ejemplo, con 1 GB serían 2 workers.
- Con más de un worker, define también `CACHE_BACKEND=db`. El bloqueo de login ya no depende del caché; lo que lo necesita es el limitador por IP de allauth.

### 5.2 Caché compartido

- `LocMemCache` no se comparte entre procesos (es memoria de cada worker).
- `DatabaseCache` sí se comparte, pero su `incr()` no es atómico. Por eso el bloqueo por cuenta usa su propia tabla con `INSERT … ON CONFLICT DO UPDATE`, probado con dos conexiones simultáneas.

### 5.3 Almacenamiento de `media/` (verificar antes de cambiar nada)

1. En Railway → servicio web → *Settings* → *Volumes*: confirmar que existe un volumen montado en la ruta de `media/` del contenedor (`/app/media` si el código está en `/app`).
2. Subir un archivo de prueba en el entorno de pruebas, redesplegar y comprobar que se sigue descargando.
3. Si **no** hay volumen: crearlo antes de cualquier otra cosa. Los archivos que ya se perdieron no se recuperan; los datos extraídos siguen en PostgreSQL.

Esta rama no cambia el almacenamiento, así que no requiere migrar archivos.

## 6. Cómo probar en un entorno independiente

**Local** (usa tu PostgreSQL local, nunca el de producción):

```
git switch mejoras/seguridad-estabilidad
venv\Scripts\python.exe manage.py migrate
venv\Scripts\python.exe manage.py test
venv\Scripts\python.exe manage.py runserver
```

Resultado esperado: 105 pruebas OK.

**Railway, entorno de pruebas** (recomendado antes de producción):

1. Crear un *Environment* nuevo en el proyecto (por ejemplo, `pruebas`) **con su propia base PostgreSQL y su propio volumen**. No reutilizar `DATABASE_URL` ni el volumen de producción.
2. Desplegar la rama `mejoras/seguridad-estabilidad` en ese entorno.
3. Comprobar:
   - los logs de arranque: `migrate` aplica `0012_bloqueo_login` y Gunicorn arranca con `gunicorn.conf.py`;
   - login correcto, y bloqueo tras 3 fallos;
   - un docente sube un CSV; un estudiante no puede;
   - generar un PDF y un Excel, individual y comparativo;
   - "Olvidé mi contraseña" con un correo inexistente muestra la misma pantalla.
4. Si se quiere probar concurrencia: `WEB_CONCURRENCY=2` y `CACHE_BACKEND=db`, y vigilar la memoria en *Metrics*.

## 7. Despliegue y reversión

**Desplegar** (cuando el entorno de pruebas esté bien):

```
git switch main
git merge --no-ff mejoras/seguridad-estabilidad
git push origin main
```

Railway redespliega `main`. Después del despliegue, repetir las comprobaciones del paso 6.3 en producción.

**Revertir si algo falla:**

- Lo más rápido: en Railway → *Deployments*, hacer *Redeploy* del despliegue anterior.
- En Git: `git revert -m 1 <commit del merge>` y `git push origin main`.
- La tabla `analisis_bloqueologin` puede quedarse aunque se vuelva al código anterior, que la ignora. Para quitarla, **antes** de revertir el código: `python manage.py migrate analisis 0011`. Solo se pierden los contadores de intentos.
- Si se activaron `WEB_CONCURRENCY` o `CACHE_BACKEND`, borrarlas para volver a 1 worker con caché local.

## 8. Decisiones pendientes

1. ¿Verificación de correo obligatoria en el registro? Es lo único que cierra la enumeración en el alta, pero cambia el flujo de registro.
2. El bloqueo por correo permite que alguien bloquee a propósito una cuenta ajena durante 15 minutos. Es el equilibrio habitual; se puede revisar si llega a ser un problema.
3. En la ficha de muestra, los porcentajes por categoría se calculan sobre los 50 taxones mostrados, no sobre el total.
4. En la lista de bioquímica, "Registrar primer ensayo" apunta a `/admin/…/add/`, que los docentes no pueden abrir.
5. Paginación de `api_muestras` (cambiaría el contrato de la API).
6. Retirar el bloque "DIAGNOSTICO EMAIL".

## 9. Consulta de solo lectura para revisar el catálogo de producción

Muestra los nombres que aparecen en más de un nivel. Son los únicos casos en que el commit 7 cambia la clasificación de la ficha o de la API:

```sql
SELECT marcador, lower(nombre) AS nombre, array_agg(nivel || ':' || clasificacion) AS entradas
FROM analisis_catalogomicroorganismo
GROUP BY marcador, lower(nombre)
HAVING count(DISTINCT nivel) > 1
ORDER BY 1, 2;
```
