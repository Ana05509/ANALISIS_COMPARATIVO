"""
metadata_service.py
-------------------
Responsabilidad: Gestionar los metadatos de las muestras agrícolas antes y
después de cargar los archivos moleculares (16S / ITS).

Relación con README:
  - Cubre "Gestión de Muestras Agrícolas" y "Registro Estructurado".
  - Soporta la segmentación por Cultivo + VariedadClon (Cacao CCN51, Clon 100, etc.).
  - El CSV de referencia es data/metadata/muestras.csv.

Relación con models.py:
  - Opera sobre: Cultivo, VariedadClon, MuestraSuelo, ArchivoMolecular.
  - No toca ResultadoTaxonomico ni CatalogoMicroorganismo.
"""

import csv
import io
from pathlib import Path
from django.core.exceptions import ValidationError
from analisis.models import Cultivo, VariedadClon, MuestraSuelo, ArchivoMolecular


# ---------------------------------------------------------------------------
# Cultivo
# ---------------------------------------------------------------------------

def obtener_o_crear_cultivo(nombre: str, descripcion: str = "") -> Cultivo:
    """
    Devuelve un Cultivo existente o lo crea si no existe.
    Nombre se normaliza a Title Case para consistencia.

    Ejemplo:
        cultivo = obtener_o_crear_cultivo("Cacao", "Cultivo principal del proyecto")
    """
    nombre = nombre.strip().title()
    cultivo, _ = Cultivo.objects.get_or_create(
        nombre=nombre,
        defaults={"descripcion": descripcion},
    )
    return cultivo


def listar_cultivos() -> list[dict]:
    """
    Retorna todos los cultivos registrados como lista de dicts.
    Útil para poblar selects en formularios (forms.py).
    """
    return list(Cultivo.objects.values("id", "nombre", "descripcion"))


# ---------------------------------------------------------------------------
# VariedadClon
# ---------------------------------------------------------------------------

def obtener_o_crear_variedad(
    cultivo: Cultivo,
    nombre_variedad: str,
    descripcion: str = "",
) -> VariedadClon:
    """
    Devuelve o crea una VariedadClon asociada al Cultivo dado.

    Ejemplo:
        variedad = obtener_o_crear_variedad(cultivo_cacao, "CCN51")
    """
    nombre_variedad = nombre_variedad.strip()
    variedad, _ = VariedadClon.objects.get_or_create(
        cultivo=cultivo,
        nombre=nombre_variedad,
        defaults={"descripcion": descripcion},
    )
    return variedad


def listar_variedades(cultivo_id: int) -> list[dict]:
    """
    Retorna todas las variedades/clones de un cultivo específico.
    Útil para cargar opciones dependientes en el formulario de subida.
    """
    return list(
        VariedadClon.objects.filter(cultivo_id=cultivo_id)
        .values("id", "nombre", "descripcion")
    )


# ---------------------------------------------------------------------------
# MuestraSuelo
# ---------------------------------------------------------------------------

def registrar_muestra(
    codigo: str,
    cultivo: Cultivo,
    variedad_clon: VariedadClon | None = None,
    tipo_muestra: str = "Suelo",
    observaciones: str = "",
) -> MuestraSuelo:
    """
    Crea y guarda una nueva MuestraSuelo en la base de datos.

    Parámetros:
        codigo          : Identificador único de la muestra (ej. "CCN51-M01").
        cultivo         : Instancia de Cultivo.
        variedad_clon   : Instancia de VariedadClon (opcional).
        tipo_muestra    : Por defecto "Suelo" según el modelo.
        observaciones   : Notas libres del técnico agrícola.

    Relación con roles (README):
        Este método es invocado por el Técnico Agrícola / Usuario Final,
        quien solo registra metadatos sin acceder al pipeline.
    """
    if not codigo.strip():
        raise ValidationError("El código de muestra no puede estar vacío.")

    muestra = MuestraSuelo.objects.create(
        codigo=codigo.strip(),
        cultivo=cultivo,
        variedad_clon=variedad_clon,
        tipo_muestra=tipo_muestra,
        observaciones=observaciones,
    )
    return muestra


def obtener_muestra_por_codigo(codigo: str) -> MuestraSuelo | None:
    """
    Busca una MuestraSuelo por su código. Retorna None si no existe.
    """
    try:
        return MuestraSuelo.objects.select_related("cultivo", "variedad_clon").get(
            codigo=codigo.strip()
        )
    except MuestraSuelo.DoesNotExist:
        return None


def listar_muestras_por_cultivo(cultivo_id: int) -> list[dict]:
    """
    Retorna todas las muestras de un cultivo, con datos de variedad incluidos.
    Útil para el dashboard y el historial.
    """
    return list(
        MuestraSuelo.objects.filter(cultivo_id=cultivo_id)
        .select_related("variedad_clon")
        .values(
            "id",
            "codigo",
            "variedad_clon__nombre",
            "tipo_muestra",
            "fecha_registro",
            "observaciones",
        )
    )


# ---------------------------------------------------------------------------
# Importación masiva desde CSV (data/metadata/muestras.csv)
# ---------------------------------------------------------------------------

def importar_muestras_desde_csv(ruta_csv: str | Path) -> dict:
    """
    Importa muestras masivamente desde el archivo CSV de metadatos.
    Formato esperado del CSV (encabezados):
        codigo, cultivo, variedad_clon, tipo_muestra, observaciones

    Retorna:
        {
            "creadas": int,
            "omitidas": int,      # ya existían
            "errores": list[str], # filas con problemas
        }
    """
    ruta_csv = Path(ruta_csv)
    if not ruta_csv.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {ruta_csv}")

    creadas  = 0
    omitidas = 0
    errores  = []

    with open(ruta_csv, newline="", encoding="utf-8") as f:
        lector = csv.DictReader(f)
        for i, fila in enumerate(lector, start=2):  # fila 1 = encabezados
            try:
                codigo = fila.get("codigo", "").strip()
                if not codigo:
                    errores.append(f"Fila {i}: código vacío, se omite.")
                    continue

                # Evitar duplicados
                if MuestraSuelo.objects.filter(codigo=codigo).exists():
                    omitidas += 1
                    continue

                cultivo = obtener_o_crear_cultivo(fila.get("cultivo", "Desconocido"))

                nombre_var = fila.get("variedad_clon", "").strip()
                variedad   = obtener_o_crear_variedad(cultivo, nombre_var) if nombre_var else None

                registrar_muestra(
                    codigo=codigo,
                    cultivo=cultivo,
                    variedad_clon=variedad,
                    tipo_muestra=fila.get("tipo_muestra", "Suelo"),
                    observaciones=fila.get("observaciones", ""),
                )
                creadas += 1

            except Exception as e:
                errores.append(f"Fila {i}: {str(e)}")

    return {"creadas": creadas, "omitidas": omitidas, "errores": errores}


# ---------------------------------------------------------------------------
# ArchivoMolecular: registro de metadatos del archivo subido
# ---------------------------------------------------------------------------

def registrar_archivo_molecular(
    muestra: MuestraSuelo,
    tipo_analisis: str,
    archivo_django_file,
) -> ArchivoMolecular:
    """
    Crea el registro del archivo molecular asociado a la muestra.

    Parámetros:
        muestra            : Instancia de MuestraSuelo ya registrada.
        tipo_analisis      : "16S" o "ITS" (validado contra choices del modelo).
        archivo_django_file: Objeto InMemoryUploadedFile / TemporaryUploadedFile
                             proveniente del formulario de subida.

    Relación con roles (README):
        Invocado por el Analista Especialista al cargar los archivos 16S/ITS.
    """
    tipos_validos = [choice[0] for choice in ArchivoMolecular.TIPOS_ANALISIS]
    if tipo_analisis not in tipos_validos:
        raise ValidationError(
            f"Tipo de análisis inválido: '{tipo_analisis}'. "
            f"Opciones válidas: {tipos_validos}"
        )

    archivo = ArchivoMolecular.objects.create(
        muestra=muestra,
        tipo_analisis=tipo_analisis,
        archivo=archivo_django_file,
    )
    return archivo


def obtener_archivos_de_muestra(muestra_id: int) -> list[dict]:
    """
    Lista los archivos moleculares registrados para una muestra.
    Retorna info útil para el historial y la vista de detalle.
    """
    return list(
        ArchivoMolecular.objects.filter(muestra_id=muestra_id)
        .values("id", "tipo_analisis", "archivo", "fecha_carga")
        .order_by("-fecha_carga")
    )


# ---------------------------------------------------------------------------
# Resumen de metadatos para el dashboard
# ---------------------------------------------------------------------------

def resumen_metadatos() -> dict:
    """
    Estadísticas rápidas para poblar el dashboard principal.

    Retorna:
        {
            "total_muestras"  : int,
            "total_cultivos"  : int,
            "total_variedades": int,
            "total_archivos"  : int,
            "por_tipo_analisis": {"16S": int, "ITS": int},
        }
    """
    from django.db.models import Count

    por_tipo = (
        ArchivoMolecular.objects.values("tipo_analisis")
        .annotate(total=Count("id"))
    )
    tipo_dict = {item["tipo_analisis"]: item["total"] for item in por_tipo}

    return {
        "total_muestras"   : MuestraSuelo.objects.count(),
        "total_cultivos"   : Cultivo.objects.count(),
        "total_variedades" : VariedadClon.objects.count(),
        "total_archivos"   : ArchivoMolecular.objects.count(),
        "por_tipo_analisis": {
            "16S": tipo_dict.get("16S", 0),
            "ITS": tipo_dict.get("ITS", 0),
        },
    }