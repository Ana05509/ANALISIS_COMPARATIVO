# 7. Operación y mantenimiento

## 7.1 Administración diaria

| Tarea | Dónde | Frecuencia sugerida |
|---|---|---|
| Asignar roles a las cuentas nuevas (se crean como Estudiante) | Admin → Usuarios | Cuando lo pidan |
| Revisar los intentos fallidos de inicio de sesión y las IP repetidas | Admin → Auditoría → Eventos de acceso (incluye un dashboard con gráficos) | Semanal |
| Revisar las acciones administrativas y las aceptaciones de términos | Admin → Auditoría → Registro de acciones | Mensual |
| Revisar los cambios en muestras, catálogo o usuarios | Pestaña «Historial» de cada registro | Cuando haya una incidencia |
| Mantener el catálogo funcional | Admin → Catálogo (importar o reclasificar) | Cuando se agreguen taxones nuevos |
| Detectar taxones sin clasificar | `python manage.py diagnosticar_catalogo --tipo 16S` (y `ITS`) | Después de cargas grandes |

## 7.2 Monitoreo y registros

| Fuente | Contenido | Acceso |
|---|---|---|
| Logs de Railway (servicio web) | Salida de `migrate` y `collectstatic`, log de acceso de Gunicorn (`--access-logfile -`) y excepciones | Panel de Railway → servicio → *Logs* |
| `EventoAcceso` | Inicios de sesión exitosos y fallidos, y cierres de sesión, con IP y navegador | Admin |
| `django_admin_log` | Acciones en el admin y aceptación de términos (versión, fecha, IP) | Admin |
| Tablas `historical*` | Versión anterior de cada cambio y su autor | Admin → Historial |
| Servidor propio | `journalctl -u biomicro`, logs de nginx | Shell |

**Content Security Policy (CSP).** Con `CSP_MODO=reporte`, que es el valor por defecto, el navegador no bloquea nada: avisa a `/csp-report/` y cada aviso queda en el log como una línea `CSP {"document-uri": …, "violated-directive": …, "blocked-uri": …}`. Procedimiento:
1. Desplegar y revisar el log durante unos días, buscando `CSP {`.
2. Si solo aparecen avisos esperables (extensiones del navegador, por ejemplo `chrome-extension://`), cambiar la variable a `CSP_MODO=bloquear` en Railway y redesplegar.
3. Si una página deja de funcionar, volver a `CSP_MODO=reporte` y agregar el origen que falte en `_CSP` (`config/settings.py`).

Las librerías que se cargan desde CDN (Plotly, Chart.js, Tabler Icons) tienen la versión fijada y una huella de integridad (`integrity="sha384-…"`). **Si se cambia la versión de una de ellas, hay que recalcular su huella**: si no, el navegador se niega a cargarla.

Al arrancar, el sistema escribe en el log una línea `=== DIAGNOSTICO EMAIL ===` con el backend de correo y si hay credenciales (no muestra los valores). Sirve para diagnosticar fallos de envío.

**No hay** alertas automáticas, monitoreo de disponibilidad ni rastreo de errores (Sentry o similar) [PENDIENTE: decidir si se incorporan].

## 7.3 Copias de seguridad y restauración

Hay que respaldar dos cosas: **la base PostgreSQL** y **la carpeta `media/`** (archivos de secuenciación, PDF de laboratorio, imágenes de cultivos y avatares). Si se pierde `media/`, los resultados ya procesados siguen en la base, pero los archivos originales no se pueden recuperar.

### Railway

| Elemento | Estado |
|---|---|
| Respaldos automáticos de PostgreSQL en Railway | [PENDIENTE DE CONFIRMAR: activados, frecuencia y retención] |
| Respaldo del volumen de `media/` | [PENDIENTE DE CONFIRMAR] |

**Respaldo manual de la base** (desde un equipo con el cliente de PostgreSQL, usando la URL pública de conexión de Railway, que nunca debe guardarse en el repositorio):

```bash
pg_dump --format=custom --no-owner --dbname="$DATABASE_URL" --file=biomicro_AAAA-MM-DD.dump
```

**Restauración:**

```bash
pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL" biomicro_AAAA-MM-DD.dump
```

Restaurar primero en una base de prueba y comprobar que funciona antes de tocar producción. Después de restaurar, ejecutar `python manage.py migrate` si el código es más nuevo que el respaldo.

### Servidor propio

`deploy/scripts/respaldo.sh` hace el `pg_dump` y un `tar` de `media/` en `/var/backups/biomicro`, y borra los respaldos de más de 28 días. Se programa con cron:

```bash
echo "0 2 * * * root bash /opt/biomicro/app/deploy/scripts/respaldo.sh" | sudo tee /etc/cron.d/biomicro-respaldo
```

`actualizar.sh` ejecuta este respaldo antes de cada actualización. Recomendación: copiar `/var/backups/biomicro` a otro equipo, porque los respaldos guardados en el mismo servidor no protegen si se pierde el disco.

## 7.4 Actualización de dependencias

1. En local: `pip list --outdated` para ver qué dependencias tienen versiones nuevas.
2. Actualizar una o pocas dependencias a la vez en `requirements.txt` (todas las versiones están fijadas con `==`).
3. Ejecutar `python manage.py test analisis.tests` y `python manage.py check --deploy`.
4. Revisar a mano: la carga, Comparar, un reporte PDF y uno Excel, y el admin.
5. Prestar especial atención a:
   - **django-allauth**: el bloqueo de Google y la regla de dominio dependen de `is_open_for_signup` y `ImmediateHttpResponse`.
   - **django-unfold**: el admin está muy personalizado (`admin.py` tiene unas 2100 líneas, más las plantillas en `templates/admin/`).
   - **pandas, numpy y scipy**: lo cubren las pruebas científicas.
   - **Plotly.js**: se carga desde un CDN con la versión fijada en las plantillas (2.35.2 y 2.32.0). Si se actualiza, revisar `chart_theme.js`.
6. Hacer los parches de seguridad de Django en cuanto se publiquen.

## 7.5 Gestión de accesos

| Operación | Procedimiento |
|---|---|
| Dar acceso de docente | Admin → Usuarios → *Rol* = Docente / Investigador |
| Dar acceso de administrador | *Rol* = Administrador (activa `is_staff` automáticamente) |
| Revocar el acceso | Desmarcar *Activo*. No borrar el usuario, para conservar la autoría de los ensayos y la auditoría |
| Desbloquear una cuenta antes de los 15 min | El bloqueo vive en la caché del proceso: se libera al vencer o al reiniciar el servicio |
| Cambiar los dominios que pueden registrarse | Variable `REGISTRO_DOMINIOS_PERMITIDOS` en Railway |
| Forzar a todos a aceptar de nuevo los términos | Subir `TERMINOS_VERSION` y `TERMINOS_FECHA` en `analisis/seguridad.py` y desplegar |
| Rotar secretos (`SECRET_KEY`, Google, SMTP) | Cambiarlos en las variables de Railway y volver a desplegar. Cambiar `SECRET_KEY` cierra todas las sesiones |

## 7.6 Atención de incidencias

| Síntoma | Primer diagnóstico |
|---|---|
| Error 500 después de un despliegue | Logs de Railway: ¿falló una migración o falta una variable? Revertir según [04](04_instalacion_despliegue.md), 4.7 |
| El sitio no arranca y aparece `ImproperlyConfigured: SECRET_KEY…` | Falta `SECRET_KEY` con `DEBUG=False` |
| «CSRF verification failed» en los formularios | El dominio no está en `CSRF_TRUSTED_ORIGINS` |
| Desaparecen los archivos subidos después de un despliegue | No hay un volumen persistente montado en `media/` |
| Todos los accesos aparecen con la misma IP o el bloqueo afecta a todos | Revisar `ALLAUTH_TRUSTED_PROXY_COUNT` |
| El login con Google falla con `redirect_uri_mismatch` | Falta registrar la URI de callback del dominio en Google Cloud |
| No se envían correos | Revisar la línea `DIAGNOSTICO EMAIL` del log y las variables `EMAIL_*` |
| Un reporte tarda o da *timeout* | Muchas muestras o nivel especie: reducir la selección. Ver el defecto D-07 |

Canal y responsable de soporte: [PENDIENTE DE CONFIRMAR].
