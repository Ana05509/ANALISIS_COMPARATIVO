# services/data/file_service.py
# Primera Línea de Defensa: Validación de Integridad, Peso y Formato de Archivos Subidos.

import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Tuple, Union

EXTENSIONES_VALIDAS = {".csv", ".xlsx", ".xls"}
TAMANO_MAXIMO_MB    = 20
TAMANO_MAXIMO_BYTES = TAMANO_MAXIMO_MB * 1024 * 1024


def detectar_extension(archivo: Any) -> str:
    """Resuelve la extensión real del archivo, compatible con rutas de disco u objetos InMemoryUploadedFile."""
    if isinstance(archivo, (str, Path)):
        return Path(archivo).suffix.lower()
    nombre = getattr(archivo, "name", "") or ""
    return Path(nombre).suffix.lower()


def es_formato_valido(archivo: Any) -> bool:
    """Valida la extensión contra la lista blanca del ecosistema analítico."""
    return detectar_extension(archivo) in EXTENSIONES_VALIDAS


def verificar_tamano(archivo: Any) -> bool:
    """Evita ataques de denegación de servicio controlando el peso máximo de la secuencia binaria."""
    if isinstance(archivo, (str, Path)):
        return Path(archivo).stat().st_size <= TAMANO_MAXIMO_BYTES
    tamano = getattr(archivo, "size", None)
    if tamano is None:
        if hasattr(archivo, "seek") and hasattr(archivo, "tell"):
            archivo.seek(0, 2)
            tamano = archivo.tell()
            archivo.seek(0)
        else:
            return False
    return tamano <= TAMANO_MAXIMO_BYTES


def leer_archivo(archivo: Any) -> pd.DataFrame:
    """Despacha la lectura al motor especializado según la extensión analizada."""
    extension = detectar_extension(archivo)
    if extension in (".xlsx", ".xls"):
        return _leer_excel(archivo)
    elif extension == ".csv":
        return _leer_csv(archivo)
    else:
        raise ValueError(f"Formato '{extension}' no soportado. Use: {', '.join(EXTENSIONES_VALIDAS)}")


def _leer_excel(archivo: Any) -> pd.DataFrame:
    """Lee hojas de cálculo forzando tipos string iniciales para evitar truncados taxonómicos."""
    try:
        if hasattr(archivo, "seek"):
            archivo.seek(0)
        return pd.read_excel(archivo, dtype=str)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo Excel de forma consistente: {e}")


def _leer_csv(archivo: Any) -> pd.DataFrame:
    """Prueba de forma iterativa delimitadores comunes protegiendo los punteros de memoria."""
    separadores = [",", ";", "\t", "|", " "]
    ultimo_error = None

    for sep in separadores:
        try:
            if hasattr(archivo, "seek"):
                archivo.seek(0)
            df = pd.read_csv(archivo, sep=sep, dtype=str)
            if df.shape[1] > 1:
                return df
        except Exception as e:
            ultimo_error = e
            continue

    raise ValueError(f"Estructura CSV incompatible con los delimitadores estándar del sistema. Último error: {ultimo_error}")


def validar_archivo(archivo: Any) -> Dict[str, Any]:
    """Audita de extremo a extremo las condiciones de seguridad antes de dar luz verde al pipeline."""
    errores: List[str] = []
    extension = detectar_extension(archivo)
    filas = None
    columnas = None

    if not es_formato_valido(archivo):
        errores.append(f"Extensión '{extension}' no permitida. Formatos válidos: {', '.join(EXTENSIONES_VALIDAS)}")
        return {"valido": False, "errores": errores, "extension": extension, "filas": None, "columnas": None}

    if not verificar_tamano(archivo):
        errores.append(f"El archivo supera el límite crítico establecido de ({TAMANO_MAXIMO_MB} MB).")

    if not errores:
        try:
            df = leer_archivo(archivo)
            filas = len(df)
            columnas = len(df.columns)

            if filas == 0:
                errores.append("El archivo molecular no contiene registros de datos.")
            if columnas < 2:
                errores.append("Matriz incompleta. El archivo posee menos de 2 columnas de información.")
        except ValueError as e:
            errores.append(str(e))
        finally:
            if hasattr(archivo, "seek"):
                archivo.seek(0)

    return {
        "valido": len(errores) == 0,
        "errores": errores,
        "extension": extension,
        "filas": filas,
        "columnas": columnas,
    }


def cargar_archivo_molecular(archivo: Any, tipo_analisis: str = "") -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Punto de entrada unificado. Resguarda punteros y entrega la matriz limpia lista para el pipeline."""
    reporte = validar_archivo(archivo)

    if not reporte["valido"]:
        errores_str = " | ".join(reporte["errores"])
        prefijo = f" de tipo {tipo_analisis}" if tipo_analisis else ""
        raise ValueError(f"El archivo{prefijo} falló los controles de calidad: {errores_str}")

    if hasattr(archivo, "seek"):
        archivo.seek(0)

    df = leer_archivo(archivo)

    if hasattr(archivo, "seek"):
        archivo.seek(0)

    return df, reporte


def obtener_nombre_archivo(archivo: Any) -> str:
    """Extrae la firma nominal del archivo para trazabilidad de logs."""
    if isinstance(archivo, (str, Path)):
        return Path(archivo).name
    return str(getattr(archivo, "name", "archivo_secuenciacion_anonimo"))