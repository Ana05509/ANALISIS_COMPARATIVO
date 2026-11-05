# 8. Entrega y cierre

## 8.1 Inventario de entregables

| # | Entregable | Ubicación | En git | Estado |
|---|---|---|:---:|---|
| E-01 | Código fuente (apps `config`, `portal`, `analisis`, `bioquimica`) | Repositorio, rama `main` [URL: PENDIENTE DE CONFIRMAR] | ✅ | Último commit de código `86bbdd5` |
| E-02 | Cambios del 4-nov-2026: términos v1.1, dominio `@utc.edu.ec`, CSP y SRI, gráficos para celular, limpieza de código muerto y pruebas nuevas | Commit `86bbdd5` | ✅ | Desplegado |
| E-03 | Migraciones de la base de datos | `analisis/migrations/`, `bioquimica/migrations/` | ✅ | Al día (0 pendientes en local) |
| E-04 | Pruebas automatizadas | `analisis/tests.py` (47 pruebas) | ✅ | Todas correctas |
| E-05 | Dependencias | `requirements.txt`, `requirements-dev.txt` | ✅ | Versiones fijadas |
| E-06 | Configuración de despliegue en Railway | `Procfile` | ✅ | En uso |
| E-07 | Configuración para servidor propio | `deploy/nginx/`, `deploy/systemd/`, `deploy/env.produccion.ejemplo` | ✅ | Preparada |
| E-08 | Scripts de instalación, actualización y respaldo | `deploy/scripts/*.sh` | ✅ | Versionados |
| E-09 | Plantillas de variables de entorno | `.env.example`, `deploy/env.produccion.ejemplo` | ✅ | Sin secretos |
| E-10 | Textos legales | `analisis/templates/legal/` | ✅ | Campos `[RESALTADOS]` sin completar |
| E-11 | Manual del administrador (dentro del sistema) | `/admin/manual/` | ✅ | — |
| E-12 | Guía y glosario (dentro del sistema) | `/ayuda/` | ✅ | — |
| E-13 | Documentación de cierre | `docs/*.md` | ✅ | Versionada (el documento para el jurado, Word y PDF, queda solo en el equipo local) |
| E-14 | Scripts del artículo (figuras de PCoA y benchmark, versión en español) | `scripts/` | ❌ | Excluidos de git a propósito |
| E-15 | Resultados del artículo (CSV, PNG y SVG en inglés y en español) | `resultados_benchmark/`, `resultados_pcoa/`, `resultados_pcoa_its/` | ❌ | Excluidos de git a propósito; solo en el equipo local |
| E-16 | Base de datos de producción y archivos `media/` | Railway | — | Transferir el acceso al proyecto de Railway |
| E-17 | Credenciales (Google OAuth, SMTP, `SECRET_KEY`) | Variables de Railway | — | Transferir por un canal seguro, **nunca en un documento** |

## 8.2 Transferencia de conocimientos

| Tema | Material | Responsable de la entrega | Receptor | Fecha |
|---|---|---|---|---|
| Arquitectura y código | [03](03_documentacion_tecnica.md) | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |
| Despliegue y reversión en Railway | [04](04_instalacion_despliegue.md) | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |
| Operación, respaldos y accesos | [07](07_operacion_mantenimiento.md) | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |
| Métodos científicos (PCoA, PERMANOVA, índices) | `diversity.py` (docstrings con referencias), `analisis/tests.py` | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |
| Traspaso de cuentas: Railway, Google Cloud, SMTP, repositorio | — | [PENDIENTE] | [PENDIENTE] | [PENDIENTE] |

## 8.3 Riesgos pendientes

| ID | Riesgo | Impacto | Probabilidad | Mitigación |
|---|---|---|---|---|
| R-01 | ~~Scripts de despliegue sin versionar~~ | — | — | **Resuelto** el 5-nov-2026: la regla de `.git/info/exclude` ahora solo excluye `/scripts/` de la raíz |
| R-02 | No hay volumen persistente para `media/` o no tiene respaldo | Alto: se pierden los archivos originales | [PENDIENTE DE CONFIRMAR] | Verificarlo en Railway (7.3) |
| R-03 | No están confirmados los respaldos de PostgreSQL | Alto | [PENDIENTE DE CONFIRMAR] | Activar los respaldos y probar una restauración |
| R-04 | Los textos legales están incompletos y sin aprobación jurídica | Medio: incumplimiento de la LOPDP | Alta | Completar y aprobar (E-10) |
| R-05 | El conocimiento está concentrado en una sola desarrolladora | Medio | Alta | Sesiones de transferencia (8.2) |
| R-06 | El Índice de Salud del Suelo (RN-07) es una heurística propia, sin validación científica publicada | Medio: interpretación agronómica errónea | Media | Presentarlo como orientativo (ya lo dicen los términos) y validarlo con expertos |
| R-07 | Defectos D-02 a D-04 (bloqueo por worker, enumeración de cuentas, verificación de correo) | Medio | Media | [06](06_pruebas_validacion.md), 6.4 |
| R-08 | Se depende de CDN externos para los gráficos y los íconos | Bajo | Baja | Servirlos de forma local si la red institucional los bloquea |
| R-09 | Hay avatares de usuarios versionados en git (`media/avatars/`) | Bajo: datos personales en el repositorio | — | Sacar `media/avatars/` del repositorio y dejar solo las imágenes de cultivos de ejemplo |

## 8.4 Recomendaciones

1. Antes de firmar el acta: cerrar R-02 y R-03 (volumen de `media/` y respaldos en Railway).
2. Completar los textos legales y subir `TERMINOS_VERSION` para que todos los usuarios acepten la versión definitiva.
3. Configurar una caché compartida y activar `ACCOUNT_PREVENT_ENUMERATION=True` y la verificación obligatoria del correo.
4. Ampliar las pruebas automatizadas a las vistas de carga, reportes y permisos por rol.
5. Actualizar el `README.md` raíz para que remita a `docs/`.
6. Para la fase FASTQ (pendiente), evaluar tareas en segundo plano, porque el procesamiento de lecturas crudas no cabe en una petición HTTP.

## 8.5 Modelo de acta de entrega y aceptación

---

**ACTA DE ENTREGA Y ACEPTACIÓN DEL SISTEMA BIOMICRO**

| Campo | Valor |
|---|---|
| N.º de acta | [__________] |
| Lugar y fecha | [__________], [__/__/____] |
| Institución | Universidad Técnica de Cotopaxi — [UNIDAD / CARRERA] |
| Proyecto | BioMicro: Sistema web de análisis comparativo de perfiles microbianos de suelo (16S e ITS) |
| Versión entregada | Commit [__________] del repositorio [__________] |
| URL de producción | [__________] |

**1. Entrega.** El equipo de desarrollo entrega el sistema y los entregables del inventario de la sección 8.1 de la documentación de cierre, con las siguientes observaciones:

| # | Entregable | Recibido (Sí/No) | Observaciones |
|---|---|:---:|---|
| 1 | Código fuente y migraciones | | |
| 2 | Acceso al repositorio | | |
| 3 | Acceso a Railway (servicio, base de datos y volumen) | | |
| 4 | Credenciales, transferidas por canal seguro | | |
| 5 | Documentación de cierre (`docs/`) | | |
| 6 | Sesión de transferencia de conocimientos | | |

**2. Verificación.** Se verificaron los criterios de aceptación CA-01 a CA-08 de la sección 6.5:

| Criterio | Cumple (Sí/No/Parcial) | Observaciones |
|---|:---:|---|
| CA-01 … CA-08 | | |

**3. Pendientes aceptados.** Las partes reconocen como pendientes, fuera del alcance de esta entrega:

- [__________]

**4. Aceptación.** La parte receptora declara que recibe el sistema a su conformidad, con las observaciones anotadas.

| | Entrega | Recibe |
|---|---|---|
| Nombre | [__________] | [__________] |
| Cargo | [__________] | [__________] |
| Firma | | |
| Fecha | [__/__/____] | [__/__/____] |

---
