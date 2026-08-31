import pandas as pd
from django.db import transaction
from django.http import HttpRequest
from typing import Dict, Any

from analisis.models import MuestraSuelo, ArchivoMolecular, ResultadoTaxonomico, Cultivo, VariedadClon
from analisis.services.processing.pipeline import PipelineProcesamiento


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

def leer_archivo(archivo) -> pd.DataFrame:
    nombre = archivo.name.lower()
    if nombre.endswith((".xlsx", ".xls")):
        return pd.read_excel(archivo)
    try:
        archivo.seek(0)
        return pd.read_csv(archivo)
    except pd.errors.ParserError:
        archivo.seek(0)
        return pd.read_csv(archivo, sep="\t")

def procesar_upload(request: HttpRequest) -> Dict[str, Any]:
    archivo = request.FILES.get("archivo")
    if not archivo:
        raise ValueError("No se ha proporcionado ningún archivo para procesar.")
    validar_archivo(archivo)

    # 1. Parámetros básicos
    # .upper() acá (no solo en MuestraSuelo.save) para que el lookup de
    # "¿ya existe un archivo para esta muestra?" de abajo compare en el
    # mismo formato que se va a guardar — si no, volver a subir el mismo
    # código con distinta may/minúscula ("amazonico_16s" luego de haber
    # guardado "Amazonico_16S") no lo detectaría como la misma muestra.
    codigo_muestra = request.POST.get("nombre_producto", "").strip().upper()
    if not codigo_muestra:
        raise ValueError("El código de muestra es obligatorio.")
    
    tipo = request.POST.get("tipo", "16S").strip()
    confirmar_sobrescritura = request.POST.get("confirmar_sobrescritura") == "1"

    archivo_existente = ArchivoMolecular.objects.filter(
        muestra__codigo=codigo_muestra, tipo_analisis=tipo
    ).select_related("muestra").first()
    if archivo_existente and not confirmar_sobrescritura:
        raise MuestraDuplicadaError(
            codigo=codigo_muestra,
            tipo=tipo,
            fecha_carga=archivo_existente.fecha_carga,
            total_taxones=archivo_existente.resultados_taxonomicos.count(),
        )

    localidad = request.POST.get("localidad", "").strip()
    if not localidad:
        raise ValueError("La localidad es obligatoria.")

    finca_lote = request.POST.get("finca_lote", "").strip()
    altitud = float(request.POST.get("altitud") or 0.0)

    # 2. Lógica de Cultivo y Variedad (Manual o Selección)
    cultivo_id = request.POST.get("cultivo")
    cultivo_manual = request.POST.get("cultivo_manual", "").strip()
    variedad_id = request.POST.get("variedad_clon")
    variedad_manual = request.POST.get("variedad_manual", "").strip()

    if cultivo_manual:
        cultivo, _ = Cultivo.objects.get_or_create(nombre=cultivo_manual)
    elif cultivo_id:
        try:
            cultivo = Cultivo.objects.get(id=cultivo_id)
        except Cultivo.DoesNotExist:
            raise ValueError("El cultivo seleccionado no existe.")
    else:
        raise ValueError("Debe seleccionar o ingresar un Cultivo.")

    if variedad_manual:
        variedad, _ = VariedadClon.objects.get_or_create(nombre=variedad_manual, cultivo=cultivo)
    elif variedad_id:
        try:
            variedad = VariedadClon.objects.get(id=variedad_id, cultivo=cultivo)
        except VariedadClon.DoesNotExist:
            raise ValueError("La variedad seleccionada no existe para este cultivo.")
    else:
        raise ValueError("Debe seleccionar o ingresar una Variedad/Clon.")

    # 3. Pipeline: guarda todos los taxones, sin truncar
    df_raw = leer_archivo(archivo)
    pipeline = PipelineProcesamiento()
    resultado = pipeline.procesar_archivo_df(df_raw)

    if not resultado or "data" not in resultado or not resultado["data"]:
        raise ValueError("El archivo no contiene registros válidos o el formato es incorrecto.")

    # 4. Persistencia
    with transaction.atomic():
        muestra, _ = MuestraSuelo.objects.update_or_create(
            codigo=codigo_muestra,
            defaults={
                "cultivo": cultivo,
                "variedad_clon": variedad,
                "tipo_muestra": request.POST.get("tipo_muestra", "Suelo").strip(),
                "observaciones": request.POST.get("observaciones", "").strip(),
                "localidad": localidad,
                "finca_lote": finca_lote,
                "altitud": altitud,
            }
        )

        archivo.seek(0)
        ArchivoMolecular.objects.filter(muestra=muestra, tipo_analisis=tipo).delete()
        archivo_mol = ArchivoMolecular.objects.create(
            muestra=muestra,
            tipo_analisis=tipo,
            archivo=archivo
        )

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
        ResultadoTaxonomico.objects.bulk_create(bulk_data)

    return {
        "total_registros": len(resultado["data"]),
        "muestra_id": muestra.id,
        "codigo": muestra.codigo
    }