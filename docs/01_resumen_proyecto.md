# 1. Resumen del proyecto

## 1.1 Problema que resuelve

Los laboratorios entregan los resultados de secuenciación de suelo (marcadores 16S rRNA para bacterias e ITS para hongos) como tablas de abundancia por taxón, sin interpretación. Para comparar cultivos, variedades o localidades hay que limpiar esas tablas, calcular índices de diversidad, cruzar los taxones con su función agronómica (benéfico, fitopatógeno, neutral) y producir gráficos y reportes. Este trabajo se hacía a mano en hojas de cálculo.

BioMicro centraliza ese flujo: recibe el archivo del laboratorio, lo normaliza, lo guarda asociado a la muestra y genera análisis, comparaciones y reportes descargables. Además incorpora los ensayos de microbiología clásica (recuentos UFC y aislamientos con pruebas bioquímicas), que se leen desde los PDF del laboratorio.

## 1.2 Objetivos

| Objetivo | Estado |
|---|---|
| Cargar y normalizar perfiles taxonómicos 16S/ITS desde CSV, TSV o Excel | Implementado |
| Calcular diversidad alfa, beta y gamma, Bray-Curtis, PCoA, PERMANOVA y PERMDISP | Implementado |
| Clasificar los taxones según su función agronómica mediante un catálogo editable | Implementado |
| Comparar muestras e identificar taxones dominantes, compartidos y exclusivos | Implementado |
| Generar reportes interpretativos en PDF y Excel | Implementado |
| Registrar ensayos de microbiología clásica desde PDF o con ingreso manual | Implementado |
| Controlar el acceso por roles, con auditoría de accesos y cambios | Implementado |
| Procesar lecturas crudas FASTQ (R1/R2) | **No implementado** (propuesto, ver 1.5) |

## 1.3 Alcance

- **Usuarios:** comunidad de la UTC (administradores, docentes/investigadores y estudiantes).
- **Datos de entrada:** tablas taxonómicas ya clasificadas por el laboratorio, con las columnas `kingdom, phylum, class, order, family, genus, species, num_hits, %_hits` (formato BaseSpace), y PDF de ensayos microbiológicos (formato propio del laboratorio y formato CIPAL).
- **Plataforma:** aplicación web Django desplegada en Railway, con PostgreSQL.

## 1.4 Funcionalidades entregadas

| Módulo | Funcionalidad | Ruta principal |
|---|---|---|
| Portal | Página pública de inicio con acceso al login | `/` |
| Autenticación | Login con correo y contraseña, login con Google, registro, recuperación de contraseña, bloqueo de 15 min tras 3 intentos fallidos | `/login/`, `/accounts/` |
| Legal | Términos de uso y Política de privacidad, aceptación obligatoria con registro en auditoría | `/terminos/`, `/privacidad/`, `/aceptar-terminos/` |
| Dashboard | Indicadores generales, muestras por cultivo y recorrido guiado de la plataforma | `/dashboard/` |
| Carga de datos | Alta de muestra (cultivo, variedad, localidad, finca, altitud) y archivo 16S/ITS, con validación de columnas | `/subir/` |
| Análisis avanzado | Top N taxones, diversidad alfa, barras apiladas, mapa de calor y PCoA de una o varias muestras | `/analisis-avanzado/` |
| Comparación | Comparativa entre muestras: abundancias, mapa de calor, Shannon, diversidad beta/gamma, PERMANOVA, taxones compartidos y exclusivos | `/comparar/` |
| Historial | Muestras registradas y detalle por muestra | `/historial/`, `/producto/<id>/` |
| Catálogo | Catálogo de microorganismos con clasificación funcional, reclasificación e importación masiva (solo staff) | `/catalogo/` |
| Reportes | Reporte por nivel taxonómico (individual o comparativo) e Informe General de 7 niveles, en PDF o Excel | `/reportes/` |
| Bioquímica | Ensayos de recuento UFC y aislamiento, desde PDF o con ingreso manual, con gráficos | `/bioquimica/` |
| API | API REST de solo lectura en JSON (requiere sesión) | `/api/v1/` |
| Administración | Panel Unfold con historial de cambios, dashboards de auditoría, exportación del catálogo y manual del administrador | `/admin/` |
| Ayuda | Guía y glosario | `/ayuda/` |

## 1.5 Exclusiones y pendientes

| Elemento | Situación |
|---|---|
| Procesamiento de lecturas FASTQ (R1+R2) | Planificado en dos fases, **no iniciado**. El sistema solo acepta tablas ya clasificadas. |
| Rarefacción o normalización por profundidad | No implementado. El sistema muestra un aviso cuando las profundidades de las muestras comparadas difieren mucho. |
| Verificación obligatoria de correo al registrarse | No configurada: `ACCOUNT_EMAIL_VERIFICATION` usa el valor por defecto de allauth (`optional`), así que se puede entrar sin confirmar el correo. |
| `ACCOUNT_PREVENT_ENUMERATION = True` | Pendiente: hoy el registro revela si un correo ya tiene cuenta. |
| Textos legales definitivos | Pendientes: los campos `[RESALTADOS]` están sin completar y falta la aprobación jurídica. |

## 1.6 Resultados

- El sistema está en producción en Railway desde julio de 2026 [FECHA EXACTA: PENDIENTE DE CONFIRMAR].
- Base de datos local de referencia al 4-nov-2026: 24 muestras registradas, 12 con resultados taxonómicos (6 de 16S y 6 de ITS) y ensayos de bioquímica cargados. Los volúmenes de producción están [PENDIENTE DE CONFIRMAR].
- Las mediciones de rendimiento del cálculo de distancias y la ordenación se encuentran en `resultados_benchmark/` (fuera del repositorio, ver [08](08_entrega_cierre.md)).
