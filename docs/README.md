# Documentación de cierre — BioMicro

Sistema web de análisis comparativo de perfiles microbianos de suelo (16S e ITS).

| Campo | Valor |
|---|---|
| Destinatario | Equipo técnico que recibe el mantenimiento del sistema |
| Fecha de corte | 4 de noviembre de 2026 |
| Repositorio | Rama `main`, último commit `d037b67` [URL DEL REPOSITORIO: PENDIENTE DE CONFIRMAR] |
| Producción | Railway [URL PÚBLICA: PENDIENTE DE CONFIRMAR] |
| Institución | Universidad Técnica de Cotopaxi (UTC) [PENDIENTE DE CONFIRMAR: unidad responsable] |

Todo lo que aparece aquí se verificó en el código del repositorio a la fecha de corte. Cuando un dato no se pudo comprobar en el código, aparece como **[PENDIENTE DE CONFIRMAR]**.

## Índice

| N.º | Documento | Contenido |
|---|---|---|
| 1 | [Resumen del proyecto](01_resumen_proyecto.md) | Problema, objetivos, alcance, entregado, exclusiones y pendientes |
| 2 | [Requisitos del sistema](02_requisitos.md) | Requisitos funcionales y no funcionales, roles, reglas de negocio y trazabilidad |
| 3 | [Documentación técnica](03_documentacion_tecnica.md) | Arquitectura, módulos, tecnologías, modelo de datos y API |
| 4 | [Instalación y despliegue](04_instalacion_despliegue.md) | Entorno local, Railway, servidor propio, verificación y reversión |
| 5 | [Manual de usuario](05_manual_usuario.md) | Tareas por rol y errores frecuentes |
| 6 | [Pruebas y validación](06_pruebas_validacion.md) | Pruebas automatizadas, verificaciones manuales, incidencias y defectos conocidos |
| 7 | [Operación y mantenimiento](07_operacion_mantenimiento.md) | Auditoría, respaldos, dependencias, accesos e incidencias |
| 8 | [Entrega y cierre](08_entrega_cierre.md) | Inventario, riesgos, recomendaciones y acta de entrega |

## Estado del código a la fecha de corte

Todos los cambios están en `main` y desplegados en Railway (último commit de código: `86bbdd5`, 4-nov-2026).

## Lista de verificación para formalizar el cierre

### Completo

- [x] Inventario de funcionalidades verificado en el código.
- [x] Modelo de datos y diccionario de datos generados a partir de `models.py`.
- [x] Documentación de la API REST de solo lectura (`/api/v1/`).
- [x] Procedimiento de instalación local probado en esta sesión.
- [x] 47 pruebas automatizadas que pasan (`python manage.py test analisis.tests`).
- [x] Revisión de adaptabilidad en 6 anchos de pantalla (360–1280 px).

### Falta (bloquea el cierre)

- [x] Cambios del 4-nov-2026 con commit y desplegados (`86bbdd5`).
- [ ] Completar los campos `[RESALTADOS]` de los Términos de uso y la Política de privacidad (institución, RUC, dirección, correo, delegado de datos, plazos, ciudad) y obtener la aprobación del área jurídica.
- [x] Scripts de despliegue y documentación versionados en git.
- [ ] Confirmar la URL del repositorio, la URL de producción y los responsables de la recepción.
- [ ] Firmar el acta de entrega ([08](08_entrega_cierre.md)).

### Debe validarse

- [ ] Confirmar en Railway que existe un volumen persistente para `media/` y que hay respaldos de PostgreSQL ([07](07_operacion_mantenimiento.md)).
- [ ] Revisar que *Eventos de acceso* registre las IP reales de los clientes en producción (`ALLAUTH_TRUSTED_PROXY_COUNT`).
- [ ] Confirmar la versión de Python que usa Railway (no hay `runtime.txt` ni `.python-version`).
- [ ] Hacer la prueba de aceptación con usuarios reales de cada rol ([06](06_pruebas_validacion.md), criterios de aceptación).
- [ ] Hacer validar científicamente el «Índice de Salud del Suelo», que es una heurística propia del sistema ([08](08_entrega_cierre.md), riesgo R-06).
