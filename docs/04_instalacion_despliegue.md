# 4. Manual de instalación y despliegue

Hay tres entornos posibles:

| Entorno | Estado | Base |
|---|---|---|
| Local (desarrollo) | Probado el 4-nov-2026 | `runserver`, PostgreSQL local |
| Railway (producción actual) | En uso | `Procfile`, variables en el panel de Railway |
| Servidor propio Ubuntu 24.04 | **Preparado, sin uso confirmado** | `deploy/nginx`, `deploy/systemd` y `deploy/scripts` |

## 4.1 Requisitos previos

| Requisito | Versión |
|---|---|
| Python | 3.13 (desarrollo con 3.13.1) |
| PostgreSQL | [PENDIENTE DE CONFIRMAR la versión de producción] |
| Git | cualquiera reciente |
| Acceso a internet en el navegador | para los CDN de Plotly, las fuentes y los íconos |

Las dependencias de Python están en `requirements.txt` (producción) y `requirements-dev.txt`, que añade scikit-bio 0.7.4 para las pruebas de validación de PCoA y PERMANOVA.

## 4.2 Variables de entorno

Plantillas: `.env.example` (local) y `deploy/env.produccion.ejemplo` (producción). **No versionar nunca el `.env` real.**

| Variable | Obligatoria | Local | Producción | Notas |
|---|:---:|---|---|---|
| `SECRET_KEY` | Sí | cualquier valor | clave aleatoria | Con `DEBUG=False` el sistema **no arranca** si se deja la clave de desarrollo |
| `DEBUG` | Sí (en local) | `True` | `False` | Si no se define, vale `False`. Con `False` se activan HTTPS, HSTS y cookies `secure` |
| `ALLOWED_HOSTS` | No | `127.0.0.1,localhost` (valor por defecto) | dominio propio | Railway añade `RAILWAY_PUBLIC_DOMAIN` automáticamente |
| `CSRF_TRUSTED_ORIGINS` | Solo con dominio propio | — | `https://<dominio>` | Railway lo añade solo para su dominio |
| `DATABASE_URL` | Producción | **no definir** | la inyecta Railway | Si existe, tiene prioridad sobre `DB_*` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Local | `Proyect`, `postgres`, …, `localhost`, `5432` | — | |
| `ALLAUTH_TRUSTED_PROXY_COUNT` | No | `0` | `1` si hay `RAILWAY_PUBLIC_DOMAIN` | Número de proxies que hay delante, para obtener la IP real |
| `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` | No | — | `True` / `31536000` | Cambiar solo si todavía no hay HTTPS |
| `REGISTRO_DOMINIOS_PERMITIDOS` | No | — | `utc.edu.ec` (valor por defecto) | Separados por comas; si se deja vacío, cualquier dominio puede registrarse |
| `CSP_MODO` | No | `reporte` (valor por defecto) | `reporte` → `bloquear` | Content Security Policy: `reporte` solo registra los avisos en el log, `bloquear` los aplica y `off` la desactiva (7.2) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Para el login con Google | | | Google Cloud Console |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | Para enviar correos | | | Sin usuario y contraseña, los correos van a la consola |

## 4.3 Instalación local (Windows, PowerShell)

```powershell
# 1. Base de datos (una vez)
psql -U postgres -c "CREATE DATABASE \"Proyect\";"

# 2. Entorno virtual y dependencias
python -m venv venv
venv\Scripts\activate          # si se bloquea: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements-dev.txt

# 3. Copiar .env.example a .env y completar: DEBUG=True, SECRET_KEY, DB_*

# 4. Migraciones y administrador
python manage.py migrate
python manage.py createsuperuser

# 5. Arranque
python manage.py runserver      # http://127.0.0.1:8000/
```

Después de crear el superusuario, en `/admin/` hay que asignarle el rol **Administrador** para que el panel lo trate como admin de BioMicro.

## 4.4 Despliegue en Railway (producción actual)

Railway construye el servicio desde el repositorio y ejecuta el `Procfile`:

```
web: python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn config.wsgi --log-file - --access-logfile - --bind 0.0.0.0:$PORT --timeout 180
```

Cada despliegue **aplica las migraciones automáticamente** antes de arrancar Gunicorn.

**Configuración del servicio** [PENDIENTE DE CONFIRMAR cada punto en el panel de Railway]:

| Elemento | Requisito |
|---|---|
| Servicio PostgreSQL | Vinculado, con `DATABASE_URL` disponible para el servicio web |
| Volumen persistente | Montado en la ruta de `media/` del contenedor. **Sin volumen, los archivos subidos se pierden en cada redespliegue** |
| Variables | Las de producción de la tabla 4.2 |
| Rama de despliegue | `main` |
| Workers de Gunicorn | El `Procfile` no indica `--workers`, así que se usa `WEB_CONCURRENCY` o el valor por defecto de Gunicorn (1) |

**Procedimiento para publicar un cambio:**

1. Probar en local: `python manage.py test analisis.tests`.
2. Si hay migraciones nuevas, **hacer antes un respaldo de la base** ([07](07_operacion_mantenimiento.md), 7.3).
3. Hacer commit y push a `main`. Railway despliega solo.
4. Verificar el despliegue (4.6).

## 4.5 Servidor propio (alternativa preparada)

Para un servidor Ubuntu 24.04 en la UTC (dominio previsto: `biomicro.utc.edu.ec`):

| Archivo | Función | ¿Versionado? |
|---|---|:---:|
| `deploy/nginx/biomicro.conf` | HTTP→HTTPS, certificado ACME, `client_max_body_size 25M`, proxy al socket de Gunicorn. `/media/` pasa por Django para respetar los permisos | ✅ |
| `deploy/systemd/biomicro.service` | Gunicorn con 3 workers, `--timeout 180` y socket `unix:/run/biomicro/gunicorn.sock` | ✅ |
| `deploy/env.produccion.ejemplo` | Plantilla de variables | ✅ |
| `deploy/scripts/instalar.sh` | Instalación inicial (Python 3.13 desde deadsnakes, usuario `biomicro`, `/opt/biomicro`) | ✅ |
| `deploy/scripts/actualizar.sh` | Respaldo → `git pull --ff-only` → `pip install` → `migrate` → `collectstatic` → reinicio del servicio | ✅ |
| `deploy/scripts/respaldo.sh` | `pg_dump` + `tar` de `media/` en `/var/backups/biomicro`, con 28 días de retención | ✅ |


Uso documentado en los propios scripts:

```bash
sudo bash instalar.sh https://github.com/USUARIO/REPO.git biomicro.utc.edu.ec
sudo bash /opt/biomicro/app/deploy/scripts/actualizar.sh
```

## 4.6 Verificación del despliegue

| # | Comprobación | Resultado esperado |
|---|---|---|
| 1 | Revisar los logs del despliegue en Railway | `migrate` termina sin errores y Gunicorn escucha en `$PORT` |
| 2 | Abrir `/` | Portal público |
| 3 | Abrir `/login/` e iniciar sesión | Redirección al dashboard (o a aceptar los términos) |
| 4 | Abrir `/static/analisis/js/chart_theme.js` | 200 (WhiteNoise funciona) |
| 5 | Abrir una imagen de `/media/` sin sesión | Redirección al login |
| 6 | Abrir `/admin/` como administrador | Panel Unfold |
| 7 | Abrir `/api/v1/estadisticas/` con sesión | `{"ok": true, ...}` con conteos coherentes |
| 8 | Generar un reporte PDF y uno Excel | Se descargan sin error |
| 9 | Ver *Eventos de acceso* en el admin | La última entrada muestra una IP pública real y no la del proxy |

Para correr las comprobaciones de seguridad de Django antes de publicar, en local y con las variables de producción: `python manage.py check --deploy`.

## 4.7 Procedimiento de reversión

| Situación | Acción |
|---|---|
| El código nuevo falla y **no** tenía migraciones | En Railway, abrir **Deployments**, elegir el despliegue anterior y usar **Redeploy**. Luego hacer `git revert` del commit en `main` para que el próximo push no vuelva a publicarlo |
| El código nuevo tenía migraciones | 1) Revertir las migraciones en una shell de Railway: `python manage.py migrate <app> <migración_anterior>`. 2) Volver a desplegar la versión anterior |
| Hubo pérdida o corrupción de datos | Restaurar el respaldo ([07](07_operacion_mantenimiento.md), 7.3) |
| Servidor propio | Hacer `git checkout <commit_anterior>` en `/opt/biomicro/app`, revertir las migraciones si corresponde y ejecutar `systemctl restart biomicro` |

Las migraciones de datos `analisis/0003_catalogo_nivel_choices` (normaliza los niveles del catálogo) y `bioquimica/0003_limpiar_filas_fantasma_recuento` (borra filas vacías) tienen como reversa `noop`. Revertirlas permite volver atrás en el esquema, pero **no deshace** los cambios de datos: para recuperar los datos originales hay que restaurar un respaldo.
