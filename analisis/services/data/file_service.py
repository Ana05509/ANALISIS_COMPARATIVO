"""
file_service.py
---------------
Responsabilidad: Ser la PRIMERA puerta de entrada para cualquier archivo
molecular (.csv, .xlsx, .xls) que el usuario suba al sistema.

Su trabajo es detectar el formato, leerlo de forma segura y derivarlo
al servicio especializado (excel_service.py) o dejarlo listo para el pipeline.

Relación con README:
  - Etapa "Ingesta de Datos": carga de archivos de resultados moleculares 16S e ITS.
  - Etapa "Validación Automática": detecta formato y estructura antes de procesar.

Relación con models.py:
  - Recibe el campo `archivo` de ArchivoMolecular (FileField).
  - No crea objetos en la BD; eso le corresponde a upload_service.py.
  - El tipo_analisis ("16S" o "ITS") de ArchivoMolecular define
    qué validaciones adicionales aplicar.
"""

import os
import pandas as pd
from pathlib import Path
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile



# Extensiones y tamaño máximo permitido


EXTENSIONES_VALIDAS = {".csv", ".xlsx", ".xls"}
TAMANO_MAXIMO_MB    = 20
TAMANO_MAXIMO_BYTES = TAMANO_MAXIMO_MB * 1024 * 1024


# Detección de formato


def detectar_extension(archivo) -> str:
    """
    Obtiene la extensión del archivo subido (Django file object o ruta).
    Retorna la extensión en minúsculas, ej: ".csv", ".xlsx".
    """
    if isinstance(archivo, (str, Path)):
        return Path(archivo).suffix.lower()

    # Django UploadedFile: tiene atributo .name
    nombre = getattr(archivo, "name", "") or ""
    return Path(nombre).suffix.lower()


def es_formato_valido(archivo) -> bool:
    """
    Verifica que el archivo tenga una extensión permitida.
    """
    return detectar_extension(archivo) in EXTENSIONES_VALIDAS


def verificar_tamano(archivo) -> bool:
    """
    Verifica que el archivo no supere TAMANO_MAXIMO_MB.
    Compatible con Django UploadedFile y rutas de disco.
    """
    if isinstance(archivo, (str, Path)):
        return Path(archivo).stat().st_size <= TAMANO_MAXIMO_BYTES

    # Django UploadedFile
    tamano = getattr(archivo, "size", None)
    if tamano is None:
        # Calcular manualmente
        archivo.seek(0, 2)          # ir al final
        tamano = archivo.tell()
        archivo.seek(0)             # regresar al inicio
    return tamano <= TAMANO_MAXIMO_BYTES


# Lectura robusta (mejora del código original)


def leer_archivo(archivo) -> pd.DataFrame:
    """
    Lee un archivo molecular y devuelve un DataFrame crudo.

    Mejoras respecto al código original:
      - Soporta .xlsx y .xls además de .csv.
      - Prueba múltiples separadores para CSV (, ; \\t | espacio).
      - Hace seek(0) antes de cada intento para no fallar en archivos en memoria.
      - Lanza excepciones descriptivas en lugar de silenciarlas.

    Parámetro:
        archivo: ruta (str/Path) o Django UploadedFile (InMemoryUploadedFile /
                 TemporaryUploadedFile / FileField.file).
    """
    extension = detectar_extension(archivo)

    if extension in (".xlsx", ".xls"):
        return _leer_excel(archivo)
    elif extension == ".csv":
        return _leer_csv(archivo)
    else:
        raise ValueError(
            f"Formato '{extension}' no soportado. "
            f"Use: {', '.join(EXTENSIONES_VALIDAS)}"
        )


def _leer_excel(archivo) -> pd.DataFrame:
    """Lee archivos .xlsx / .xls con pandas."""
    try:
        return pd.read_excel(archivo, dtype=str)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo Excel: {e}")


def _leer_csv(archivo) -> pd.DataFrame:
    """
    Intenta leer un CSV con los separadores más comunes.
    Hace seek(0) antes de cada intento para soportar archivos en memoria.
    """
    separadores = [",", ";", "\t", "|", " "]
    ultimo_error = None

    for sep in separadores:
        try:
            # Regresar al inicio antes de cada intento
            if hasattr(archivo, "seek"):
                archivo.seek(0)
            df = pd.read_csv(archivo, sep=sep, dtype=str)
            # Un CSV válido tiene más de 1 columna con el separador correcto
            if df.shape[1] > 1:
                return df
        except Exception as e:
            ultimo_error = e
            continue

    raise ValueError(
        f"No se pudo leer el CSV con ningún separador estándar "
        f"({', '.join(repr(s) for s in separadores)}). "
        f"Último error: {ultimo_error}"
    )


# Validación completa antes de pasar al pipeline

def validar_archivo(archivo) -> dict:
    """
    Ejecuta todas las validaciones previas a la lectura:
      1. Extensión válida
      2. Tamaño dentro del límite
      3. Que el archivo no esté vacío
      4. Que se pueda leer sin errores

    Retorna:
        {
            "valido"    : bool,
            "errores"   : list[str],
            "extension" : str,
            "filas"     : int | None,
            "columnas"  : int | None,
        }
    """
    errores    = []
    extension  = detectar_extension(archivo)
    filas      = None
    columnas   = None

    # 1. Extensión
    if not es_formato_valido(archivo):
        errores.append(
            f"Extensión '{extension}' no permitida. "
            f"Formatos válidos: {', '.join(EXTENSIONES_VALIDAS)}"
        )
        return {"valido": False, "errores": errores,
                "extension": extension, "filas": None, "columnas": None}

    # 2. Tamaño
    if not verificar_tamano(archivo):
        errores.append(
            f"El archivo supera el tamaño máximo permitido ({TAMANO_MAXIMO_MB} MB)."
        )

    # 3 & 4. Intentar lectura
    if not errores:
        try:
            if hasattr(archivo, "seek"):
                archivo.seek(0)
            df       = leer_archivo(archivo)
            filas    = len(df)
            columnas = len(df.columns)

            if filas == 0:
                errores.append("El archivo está vacío (sin filas de datos).")
            if columnas < 2:
                errores.append(
                    "El archivo tiene menos de 2 columnas. "
                    "Verifique el separador o el formato del archivo."
                )
        except ValueError as e:
            errores.append(str(e))
        finally:
            # Regresar al inicio para lecturas posteriores
            if hasattr(archivo, "seek"):
                archivo.seek(0)

    return {
        "valido"   : len(errores) == 0,
        "errores"  : errores,
        "extension": extension,
        "filas"    : filas,
        "columnas" : columnas,
    }


# ---------------------------------------------------------------------------
# Función principal: validar + leer en un solo paso
# ---------------------------------------------------------------------------

def cargar_archivo_molecular(archivo, tipo_analisis: str = None) -> tuple[pd.DataFrame, dict]:
    """
    Punto de entrada principal para upload_service.py y pipeline.py.

    Ejecuta validación completa y, si pasa, devuelve el DataFrame listo.
    Si falla, lanza ValueError con el detalle de los errores.

    Parámetros:
        archivo        : Django UploadedFile o ruta de disco.
        tipo_analisis  : "16S" o "ITS" (opcional, para logging/contexto).

    Retorna:
        (df_crudo, reporte)

    Ejemplo de uso en upload_service.py:
        df, reporte = cargar_archivo_molecular(archivo_molecular.archivo, "16S")
        # Luego pasar df a excel_service.procesar_archivo_excel() o pipeline
    """
    reporte = validar_archivo(archivo)

    if not reporte["valido"]:
        errores_str = " | ".join(reporte["errores"])
        raise ValueError(
            f"El archivo{' de tipo ' + tipo_analisis if tipo_analisis else ''} "
            f"no pasó la validación: {errores_str}"
        )

    # Regresar al inicio antes de la lectura final
    if hasattr(archivo, "seek"):
        archivo.seek(0)

    df = leer_archivo(archivo)

    # Regresar al inicio por si algún servicio posterior necesita re-leer
    if hasattr(archivo, "seek"):
        archivo.seek(0)

    return df, reporte


# Utilidad: obtener nombre limpio del archivo


def obtener_nombre_archivo(archivo) -> str:
    """
    Retorna el nombre del archivo sin ruta, útil para logs y mensajes.
    Compatible con Django UploadedFile y rutas de disco.
    """
    if isinstance(archivo, (str, Path)):
        return Path(archivo).name
    return getattr(archivo, "name", "archivo_desconocido")