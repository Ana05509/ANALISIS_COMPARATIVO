import pandas as pd
from django.db import transaction

from analisis.models import MuestraSuelo, ArchivoMolecular, ResultadoTaxonomico, Cultivo, VariedadClon
from analisis.services.processing.pipeline import PipelineProcesamiento

NIVELES_VALIDOS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]


def validar_archivo(archivo):
    if not archivo.name.lower().endswith((".csv", ".tsv", ".xlsx", ".xls")):
        raise ValueError("Formato inválido. Use CSV, TSV o Excel.")
    if archivo.size > 10 * 1024 * 1024:
        raise ValueError("Archivo demasiado grande (máximo 10 MB).")


def leer_archivo(archivo):
    nombre = archivo.name.lower()
    if nombre.endswith((".xlsx", ".xls")):
        return pd.read_excel(archivo)
    try:
        archivo.seek(0)
        return pd.read_csv(archivo)
    except pd.errors.ParserError:
        archivo.seek(0)
        return pd.read_csv(archivo, sep="\t")


def procesar_upload(request):
    """
    Pipeline unificado desde la vista web pública. 
    Aplica seek(0) para resguardar la persistencia íntegra del archivo en el FileField.
    """
    archivo         = request.FILES.get("archivo")
    tipo            = request.POST.get("tipo_analisis", "16S")
    codigo_muestra  = request.POST.get("codigo", "").strip()
    cultivo_id      = request.POST.get("cultivo", None)
    variedad_id     = request.POST.get("variedad_clon", None)
    localidad       = request.POST.get("localidad", "").strip()
    finca_lote      = request.POST.get("finca_lote", "").strip()
    altitud_raw     = request.POST.get("altitud", None)

    # Validaciones obligatorias de campos
    if not archivo:
        raise ValueError("No se ha proporcionado ningún archivo molecular.")
    if not codigo_muestra:
        raise ValueError("El código identificador de la muestra es obligatorio.")
    if not cultivo_id:
        raise ValueError("Debe seleccionar un Cultivo válido de la lista.")
    if not variedad_id:
        raise ValueError("Debe seleccionar una Variedad o Clon específico.")
    if not localidad:
        raise ValueError("El campo 'Localidad' es obligatorio para el análisis biogeográfico.")
    if not finca_lote:
        raise ValueError("El campo 'Finca / Lote' es obligatorio para la trazabilidad.")
    if not altitud_raw or not str(altitud_raw).strip():
        raise ValueError("El campo 'Altitud' (msnm) es obligatorio.")

    try:
        altitud = int(altitud_raw)
    except ValueError:
        raise ValueError("La altitud debe ser un número entero válido.")

    validar_archivo(archivo)
    df_raw = leer_archivo(archivo)

    nivel = request.POST.get("nivel", "genus")
    if nivel not in NIVELES_VALIDOS:
        nivel = "genus"

    resultado = PipelineProcesamiento.procesar_archivo_df(df_raw, nivel=nivel)

    if not resultado or not resultado.get("data"):
        raise ValueError("El archivo no contiene datos taxonómicos válidos estructurados.")

    with transaction.atomic():
        try:
            cultivo = Cultivo.objects.get(id=cultivo_id)
        except Cultivo.DoesNotExist:
            raise ValueError("El cultivo seleccionado no existe en el catálogo.")

        try:
            variedad = VariedadClon.objects.get(id=variedad_id, cultivo=cultivo)
        except VariedadClon.DoesNotExist:
            raise ValueError("La variedad/clon no corresponde al cultivo elegido.")

        # Crear registro de la Muestra
        muestra = MuestraSuelo.objects.create(
            codigo=codigo_muestra,
            cultivo=cultivo,
            variedad_clon=variedad,
            tipo_muestra=request.POST.get("tipo_muestra", "Suelo"),
            observaciones=request.POST.get("observaciones", ""),
            localidad=localidad,
            finca_lote=finca_lote,
            altitud=altitud,
        )

        # FIX: Devolver el cursor binario a cero para que Django guarde el archivo completo
        archivo.seek(0)
        archivo_mol = ArchivoMolecular.objects.create(
            muestra=muestra,
            tipo_analisis=tipo,
            archivo=archivo,
        )

        # Volcado masivo de resultados taxonómicos procesados
        ResultadoTaxonomico.objects.bulk_create([
            ResultadoTaxonomico(
                archivo=archivo_mol,
                kingdom=item.get("kingdom", "Unclassified"),
                phylum=item.get("phylum", "Unclassified"),
                tax_class=item.get("tax_class", "Unclassified"),
                order=item.get("order", "Unclassified"),
                family=item.get("family", "Unclassified"),
                genus=item.get("genus", "Unclassified"),
                species=item.get("species", "Unclassified"),
                num_hits=item.get("num_hits", 0),
                porcentaje_hits=item.get("%_hits", 0.0),
            )
            for item in resultado["data"]
        ])

    return {
        "total_registros":      resultado.get("total_registros", len(resultado["data"])),
        "muestra_id":           muestra.id,
        "archivo_molecular_id": archivo_mol.id,
    }