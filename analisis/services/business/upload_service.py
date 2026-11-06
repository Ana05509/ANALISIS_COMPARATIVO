import csv
import logging
import zipfile

import pandas as pd
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from typing import Dict, Any

from analisis.models import MuestraSuelo, ArchivoMolecular, ResultadoTaxonomico, Cultivo, VariedadClon
from analisis.services.processing.pipeline import PipelineProcesamiento

logger = logging.getLogger(__name__)


class MuestraDuplicadaError(ValueError):
    """Ya existe un archivo del mismo marcador molecular cargado para esta muestra."""
    def __init__(self, codigo, tipo, fecha_carga, total_taxones):
        self.codigo = codigo
        self.tipo = tipo
        self.fecha_carga = fecha_carga
        self.total_taxones = total_taxones
        super().__init__(
            f"Ya existe un archivo {tipo} cargado para la muestra {codigo}."
        )


def validar_archivo(archivo) -> None:
    if not archivo.name.lower().endswith((".csv", ".tsv", ".xlsx", ".xls")):
        raise ValueError("Formato inválido. Use CSV, TSV o Excel.")
    if archivo.size > 10 * 1024 * 1024:
        raise ValueError("Archivo demasiado grande (máximo 10 MB).")

def _detectar_separador(archivo) -> str:
    """Deduce el delimitador de un .csv a partir de sus primeros 2 KB (coma si no se puede)."""
    archivo.seek(0)
    muestra = archivo.read(2048)
    archivo.seek(0)
    if isinstance(muestra, bytes):
        muestra = muestra.decode("utf-8-sig", errors="ignore")
    try:
        return csv.Sniffer().sniff(muestra, delimiters=",;\t").delimiter
    except csv.Error:
        return ","


def leer_archivo(archivo) -> pd.DataFrame:
    nombre = archivo.name.lower()
    try:
        archivo.seek(0)
        if nombre.endswith(".xlsx"):
            with zipfile.ZipFile(archivo) as libro:
                if sum(item.file_size for item in libro.infolist()) > 100 * 1024 * 1024:
                    raise ValueError("El Excel supera 100 MB descomprimido.")
            archivo.seek(0)
        if nombre.endswith((".xlsx", ".xls")):
            df = pd.read_excel(archivo, nrows=100001)
            if len(df) > 100000:
                raise ValueError("El archivo supera 100 000 registros.")
            return df
        sep = "\t" if nombre.endswith(".tsv") else _detectar_separador(archivo)
        df = pd.read_csv(archivo, sep=sep, nrows=100001)
        if len(df) > 100000:
            raise ValueError("El archivo supera 100 000 registros.")
        return df
    except zipfile.BadZipFile as e:
        raise ValueError('No se pudo leer el archivo: el XLSX no es un libro válido.') from e
    except ImportError as e:
        raise ValueError(
            f"El servidor no tiene instalado el soporte para leer este tipo de archivo ({e.name}). "
            "Conviértalo a CSV o XLSX e inténtelo de nuevo."
        ) from e
    except ValueError as e:
        raise ValueError(
            f"No se pudo leer el archivo «{archivo.name}». Verifique que no esté dañado, que la "
            f"primera fila contenga los encabezados y que el texto esté en UTF-8. Detalle: {e}"
        ) from e

def _error_duplicado(codigo, tipo, archivo_existente):
    return MuestraDuplicadaError(
        codigo=codigo,
        tipo=tipo,
        fecha_carga=archivo_existente.fecha_carga,
        total_taxones=archivo_existente.resultados_taxonomicos.count(),
    )


ALTITUD_MIN, ALTITUD_MAX = 0, 6500  # msnm; el punto más alto de Ecuador ronda los 6263 m


def leer_altitud(valor):
    """Altitud en msnm o None si no se indicó (antes se guardaba 0, que es un valor real)."""
    texto = str(valor if valor is not None else "").strip()
    if not texto:
        return None
    try:
        altitud = int(float(texto.replace(",", ".")))
    except ValueError:
        raise ValueError("La altitud debe ser un número entero en metros sobre el nivel del mar.")
    if not ALTITUD_MIN <= altitud <= ALTITUD_MAX:
        raise ValueError(f"La altitud debe estar entre {ALTITUD_MIN} y {ALTITUD_MAX} msnm.")
    return altitud


def _diferencias_metadatos(muestra, datos):
    """Campos que el formulario cambiaría en una muestra existente.
    Un campo vacío en el formulario significa "sin cambio" y no cuenta."""
    etiquetas = {
        "cultivo": "Cultivo", "variedad_clon": "Variedad/Clon", "localidad": "Localidad",
        "finca_lote": "Finca/Lote", "altitud": "Altitud", "tipo_muestra": "Tipo de muestra",
        "observaciones": "Observaciones",
    }
    difs = []
    for campo, etiqueta in etiquetas.items():
        nuevo = datos.get(campo)
        if nuevo in (None, ""):
            continue
        actual = getattr(muestra, campo)
        if hasattr(nuevo, "pk"):
            distinto = getattr(actual, "pk", None) != nuevo.pk
        else:
            distinto = str(actual if actual is not None else "").strip().lower() != str(nuevo).strip().lower()
        if distinto:
            difs.append(f"{etiqueta}: «{actual if actual not in (None, '') else '—'}» → «{nuevo}»")
    return difs


def _borrar_del_almacenamiento(storage, nombres):
    from analisis.models import ArchivoMolecularRevision
    for nombre in nombres:
        try:
            if ArchivoMolecularRevision.objects.filter(archivo=nombre).exists():
                continue
            storage.delete(nombre)
        except Exception:
            logger.warning("No se pudo borrar el archivo %s del almacenamiento", nombre, exc_info=True)


def procesar_upload(request: HttpRequest) -> Dict[str, Any]:
    archivo = request.FILES.get("archivo")
    if not archivo:
        raise ValueError("No se ha proporcionado ningún archivo para procesar.")
    validar_archivo(archivo)

    # 1. Parámetros básicos (código en mayúsculas antes de buscar si ya existe)
    codigo_muestra = request.POST.get("nombre_producto", "").strip().upper()
    if not codigo_muestra:
        raise ValueError("El código de muestra es obligatorio.")

    tipo = request.POST.get("tipo", "16S").strip()
    confirmar_sobrescritura = request.POST.get("confirmar_sobrescritura") == "1"

    # Aviso temprano para no procesar el archivo en vano; se vuelve a comprobar
    # dentro de la transacción, con la muestra bloqueada.
    archivo_existente = ArchivoMolecular.objects.filter(
        muestra__codigo=codigo_muestra, tipo_analisis=tipo
    ).first()
    if archivo_existente and not confirmar_sobrescritura:
        raise _error_duplicado(codigo_muestra, tipo, archivo_existente)

    localidad = request.POST.get("localidad", "").strip()
    if not localidad:
        raise ValueError("La localidad es obligatoria.")

    finca_lote = request.POST.get("finca_lote", "").strip()
    altitud = leer_altitud(request.POST.get("altitud"))

    # 2. Cultivo y variedad: aquí solo se validan; los manuales se crean dentro
    #    de la transacción para no dejar registros sueltos si la carga falla.
    cultivo_id = request.POST.get("cultivo")
    cultivo_manual = request.POST.get("cultivo_manual", "").strip()
    variedad_id = request.POST.get("variedad_clon")
    variedad_manual = request.POST.get("variedad_manual", "").strip()

    cultivo = None
    if not cultivo_manual:
        if not cultivo_id:
            raise ValueError("Debe seleccionar o ingresar un Cultivo.")
        try:
            cultivo = Cultivo.objects.get(id=cultivo_id)
        except (Cultivo.DoesNotExist, ValueError):
            raise ValueError("El cultivo seleccionado no existe.")

    variedad = None
    if not variedad_manual:
        if not variedad_id:
            raise ValueError("Debe seleccionar o ingresar una Variedad/Clon.")
        try:
            # Con un cultivo nuevo ninguna variedad existente puede pertenecerle.
            variedad = VariedadClon.objects.get(id=variedad_id, cultivo=cultivo) if cultivo else None
        except (VariedadClon.DoesNotExist, ValueError):
            variedad = None
        if variedad is None:
            raise ValueError("La variedad seleccionada no existe para este cultivo.")

    # 3. Pipeline (lo costoso y lo que más falla) antes de escribir nada
    df_raw = leer_archivo(archivo)
    resultado = PipelineProcesamiento.procesar_archivo_df(df_raw)

    if not resultado or "data" not in resultado or not resultado["data"]:
        raise ValueError("El archivo no contiene registros válidos o el formato es incorrecto.")

    # 4. Persistencia. La transacción no deshace lo escrito en el almacenamiento:
    #    el archivo nuevo se borra si algo falla y el anterior solo tras el commit.
    storage = ArchivoMolecular._meta.get_field("archivo").storage
    nombre_nuevo = None
    try:
        with transaction.atomic():
            # select_for_update no bloquea filas que aún no existen: si dos cargas
            # crean a la vez la misma muestra nueva, la segunda falla por el UNIQUE
            # del código (IntegrityError, abajo) en lugar de duplicar datos.
            muestra = MuestraSuelo.objects.select_for_update().filter(codigo=codigo_muestra).first()
            anteriores = []
            if muestra is not None:
                anteriores = list(ArchivoMolecular.objects.filter(muestra=muestra, tipo_analisis=tipo))
                if anteriores and not confirmar_sobrescritura:
                    raise _error_duplicado(codigo_muestra, tipo, anteriores[0])

            if cultivo is None:
                cultivo, _ = Cultivo.objects.get_or_create(nombre=cultivo_manual)
            variedad_creada = False
            if variedad is None:
                variedad, variedad_creada = VariedadClon.objects.get_or_create(
                    nombre=variedad_manual, cultivo=cultivo,
                    defaults={"descripcion": "Creada manualmente desde la subida"},
                )

            datos_muestra = {
                "cultivo": cultivo,
                "variedad_clon": variedad,
                "tipo_muestra": request.POST.get("tipo_muestra", "Suelo").strip(),
                "observaciones": request.POST.get("observaciones", "").strip(),
                "localidad": localidad,
                "finca_lote": finca_lote,
                "altitud": altitud,
            }
            if muestra is None:
                muestra = MuestraSuelo.objects.create(codigo=codigo_muestra, **datos_muestra)
            else:
                # Si la muestra ya tiene datos de OTRO marcador, cambiar sus metadatos
                # alteraría también esos resultados: se rechaza en lugar de sobrescribir
                # en silencio. Solo se permite al reemplazar el único marcador cargado.
                otros_marcadores = ArchivoMolecular.objects.filter(muestra=muestra).exclude(tipo_analisis=tipo).exists()
                diferencias = _diferencias_metadatos(muestra, datos_muestra)
                if otros_marcadores and diferencias:
                    raise ValueError(
                        f"La muestra {codigo_muestra} ya existe con otros datos de campo y tiene resultados "
                        f"de otro marcador. Para no alterarlos, use los mismos datos o pida a un "
                        f"administrador que corrija la muestra. Diferencias: " + "; ".join(diferencias) + "."
                    )
                for campo, valor in datos_muestra.items():
                    if valor in (None, "") and campo in ("altitud", "finca_lote", "observaciones"):
                        continue  # vacío en el formulario = conservar el valor guardado
                    setattr(muestra, campo, valor)
                muestra.save()

            nombres_anteriores = [a.archivo.name for a in anteriores if a.archivo.name]
            for anterior in anteriores:
                from analisis.services.business.trazabilidad import archivar_revision
                archivar_revision(anterior)
                anterior.delete()  # CASCADE: también sus ResultadoTaxonomico

            archivo.seek(0)
            archivo_mol = ArchivoMolecular(muestra=muestra, tipo_analisis=tipo)
            archivo_mol.archivo.save(archivo.name, archivo, save=False)  # escribe en el almacenamiento
            nombre_nuevo = archivo_mol.archivo.name
            archivo_mol.save()

            # Volcado con mapeo flexible
            bulk_data = []
            for item in resultado["data"]:
                bulk_data.append(ResultadoTaxonomico(
                    archivo=archivo_mol,
                    kingdom=item.get("kingdom") or item.get("Kingdom") or "Unclassified",
                    phylum=item.get("phylum") or item.get("Phylum") or "Unclassified",
                    tax_class=item.get("tax_class") or item.get("class") or item.get("Class") or "Unclassified",
                    order=item.get("order") or item.get("Order") or "Unclassified",
                    family=item.get("family") or item.get("Family") or "Unclassified",
                    genus=item.get("genus") or item.get("Genus") or "Unclassified",
                    species=item.get("species") or item.get("Species") or "Unclassified",
                    num_hits=int(item.get("num_hits") or item.get("Num_hits") or 0),
                    porcentaje_hits=float(item.get("%_hits") or item.get("porcentaje_hits") or 0.0),
                ))
            ResultadoTaxonomico.objects.bulk_create(bulk_data, batch_size=2000)

            obsoletos = [n for n in nombres_anteriores if n != nombre_nuevo]
            transaction.on_commit(lambda: _borrar_del_almacenamiento(storage, obsoletos))
    except IntegrityError as exc:
        if nombre_nuevo:
            _borrar_del_almacenamiento(storage, [nombre_nuevo])
        logger.warning("Conflicto de integridad al guardar la muestra %s", codigo_muestra, exc_info=True)
        raise ValueError(
            "Otra carga de esta misma muestra se guardó al mismo tiempo. "
            "Revise el historial y, si hace falta, vuelva a subir el archivo."
        ) from exc
    except BaseException:
        if nombre_nuevo:
            _borrar_del_almacenamiento(storage, [nombre_nuevo])
        raise

    return {
        "total_registros": len(resultado["data"]),
        "muestra_id": muestra.id,
        "codigo": muestra.codigo,
        "variedad_creada": variedad_creada,
    }
