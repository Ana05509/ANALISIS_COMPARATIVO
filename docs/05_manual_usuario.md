# 5. Manual de usuario

Manual operativo, organizado por rol, para que el equipo técnico pueda atender a los usuarios. Dentro del sistema hay además una guía para el usuario final (`/ayuda/`, «Guía y glosario») y un manual del administrador (`/admin/manual/`). El dashboard incluye un **recorrido guiado** de 8 pasos, que se puede repetir desde el menú del usuario → «Recorrer la plataforma».

## 5.1 Acceso al sistema

| Paso | Acción |
|---|---|
| 1 | Entrar en la URL del sistema [PENDIENTE DE CONFIRMAR] → «Iniciar sesión» |
| 2 | Escribir el correo y la contraseña, o usar «Continuar con Google» |
| 3 | La primera vez, y cada vez que cambie la versión de los términos: leer los textos en la pantalla «Antes de continuar», marcar la casilla y pulsar «Aceptar y continuar» |
| 4 | El sistema muestra el **Dashboard** |

**Crear una cuenta:** en «Crear cuenta», escribir el nombre, el apellido, un correo `@utc.edu.ec` y la contraseña, y aceptar los términos. La cuenta se crea con el rol **Estudiante**. Para tener otro rol, se lo debe asignar un administrador (5.5).

**Recuperar la contraseña:** en «¿Olvidaste tu contraseña?», el sistema envía un enlace al correo. Para eso SMTP tiene que estar configurado.

> 📷 Captura sugerida: pantalla de login y pantalla «Antes de continuar».

## 5.2 Tareas comunes (todos los roles)

### Analizar una o varias muestras: «Análisis Avanzado»
1. Elegir el **marcador** (16S Bacterias o ITS Hongos), el **nivel taxonómico** y la **profundidad** (Top 5, 10, 25 o 50).
2. Marcar una o más muestras en la lista. Se puede buscar por código.
3. Pulsar **Analizar**.
4. Resultado: tabla del Top N con su clasificación funcional, gráfico de distribución, diversidad alfa, barras apiladas, mapa de calor y PCoA.
5. Con **Color / Escala de grises** se cambia la paleta. Con **PNG / SVG** se descarga cada gráfico.

### Comparar muestras: «Comparar Perfiles»
1. Elegir el marcador, el nivel y el Top N, y marcar **al menos 2 muestras**.
2. Pulsar **Comparar**.
3. Resultado: abundancia comparada, mapa de calor, Shannon por muestra, métricas alfa, diversidad beta y gamma, PERMANOVA, y taxones compartidos y exclusivos.
4. Si las profundidades de secuenciación son muy distintas, aparece un aviso: en ese caso la riqueza no es directamente comparable.

### Generar un reporte: «Reportes»
1. Elegir las muestras (si no se elige ninguna, el reporte es global para el marcador), el marcador y el nivel, y pulsar **Filtrar**.
2. Revisar la vista previa: Índice de Salud del Suelo, clasificación y tabla.
3. Descargar en **PDF** o **Excel**.
4. **Informe General:** con una sola muestra, genera los 7 niveles taxonómicos en un único documento.

### Consultar el catálogo y el historial
- **Catálogo** (`/catalogo/`): buscar y filtrar por marcador y clasificación.
- **Muestras registradas** (`/historial/`): lista de muestras; cada una tiene su detalle.

### Bioquímica
- **Bioquímica** (`/bioquimica/`): lista de ensayos con sus gráficos de recuento, series CIPAL y mapa de calor de pruebas.

> 📷 Captura sugerida: resultados de Análisis Avanzado, de Comparar y la vista previa del reporte.

## 5.3 Docente / Investigador

Puede hacer todo lo anterior y además:

### Cargar una muestra con su archivo de secuenciación: «Cargar Muestra»
1. Escribir el **código de la muestra** (único), la **localidad**, la **finca o lote** y la altitud (opcional).
2. Elegir o crear el **cultivo** y la **variedad o clon**.
3. Elegir el marcador **16S** o **ITS** y adjuntar el archivo (**CSV, TSV, XLSX o XLS, de hasta 10 MB**).
4. El archivo debe tener en la primera fila estas columnas:
   `kingdom, phylum, class, order, family, genus, species, num_hits, %_hits`
5. Pulsar el botón para cargar. Una barra muestra el progreso y, al terminar, aparece un resumen con el total de taxones.

### Registrar un ensayo de bioquímica
- **Subir PDF** (`/bioquimica/subir/`): se pueden elegir varios PDF a la vez. El sistema reconoce el formato propio del laboratorio y el formato CIPAL, y omite los códigos que ya existen.
- **Ingreso manual** (`/bioquimica/manual/`): formulario para recuentos UFC (coeficiente × 10ⁿ) o para aislamientos con pruebas bioquímicas.
- Solo los docentes y administradores pueden descargar el PDF original de cada ensayo.

## 5.4 Estudiante

Solo puede consultar (5.2). No puede cargar muestras ni ensayos, ni descargar los archivos originales del laboratorio. Si intenta cargar, el sistema muestra: *«Su nivel de cuenta no dispone de permisos…»*.

## 5.5 Administrador

Puede hacer todo lo del docente y además usar el **Panel de administración** (`/admin/`, enlace en el menú lateral):

| Tarea | Ubicación en el admin |
|---|---|
| Cambiar el rol de un usuario | Usuarios → editar → *Rol en la plataforma* (al elegir «Administrador» obtiene acceso al panel) |
| Desactivar una cuenta | Usuarios → desmarcar *Activo* |
| Editar o borrar muestras, archivos y resultados | Análisis → Muestras / Archivos / Resultados (borrar una muestra borra en cascada sus archivos y resultados) |
| Reclasificar o importar el catálogo | Catálogo de microorganismos (importar desde CSV o Excel con las columnas `nombre, nivel, marcador, clasificacion`) |
| Exportar el catálogo | Catálogo → botón de exportación (pregunta el formato: Excel o CSV) |
| Ver el historial de cambios de un registro | Pestaña **Historial** del registro (cultivos, muestras, catálogo, usuarios) |
| Revisar accesos | Auditoría → Eventos de acceso (inicios y cierres de sesión, intentos fallidos con su IP) |
| Revisar acciones y aceptaciones de términos | Auditoría → Registro de acciones |

> 📷 Captura sugerida: lista de usuarios con las insignias de rol y el dashboard de Eventos de acceso.

## 5.6 Errores frecuentes

| Mensaje o síntoma | Causa | Solución |
|---|---|---|
| «Columnas faltantes: …» | Al archivo le faltan columnas obligatorias o tienen otro nombre | Renombrar los encabezados según 5.3, paso 4 |
| «Formato inválido. Use CSV, TSV o Excel.» | Extensión no admitida | Convertir el archivo a CSV o XLSX |
| «Archivo demasiado grande (máximo 10 MB).» | El archivo supera el límite | Quitar columnas sobrantes o exportarlo a CSV |
| «No se pudo leer el archivo…» | El archivo está dañado, la primera fila no tiene los encabezados o el texto no está en UTF-8 | Volver a guardarlo como CSV UTF-8 |
| El código de la muestra ya existe | El código es único (RN-02) | Usar otro código o revisar la muestra existente |
| «Seleccione al menos dos muestras para comparar.» | Se eligió una sola muestra | Marcar 2 o más |
| El análisis no muestra resultados | La muestra no tiene un archivo del marcador elegido (por ejemplo, ITS en una muestra solo 16S) | Cambiar el marcador o cargar el archivo |
| «Su nivel de cuenta no dispone de permisos…» | La cuenta tiene el rol Estudiante | Un administrador debe cambiarle el rol |
| Acceso bloqueado 15 minutos | 3 intentos fallidos con el mismo correo | Esperar 15 min o recuperar la contraseña |
| «Solo se pueden crear cuentas con un correo institucional…» | El registro se hizo con un correo que no es `@utc.edu.ec` | Registrarse con el correo institucional |
| No llega el correo de recuperación | SMTP no está configurado o el mensaje está en spam | Revisar las variables `EMAIL_*` ([04](04_instalacion_despliegue.md)) |
| Los gráficos no aparecen | El navegador no tiene acceso al CDN de Plotly | Comprobar la conexión a internet o si un bloqueador está activo |
