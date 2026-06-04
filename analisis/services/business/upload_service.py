import pandas as pd
from django.db import transaction

from analisis.models import MuestraSuelo, ArchivoMolecular, ResultadoTaxonomico, Cultivo, VariedadClon
from analisis.services.processing.pipeline import PipelineProcesamiento

NIVELES_VALIDOS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]


def parse_int_or_default(value, default=10, minimum=1, maximum=100):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def validar_archivo(archivo):
    if not archivo.name.endswith((".csv", ".tsv", ".xlsx", ".xls")):
        raise ValueError("Formato inválido. Use CSV, TSV o Excel.")
    if archivo.size > 5 * 1024 * 1024:
        raise ValueError("Archivo demasiado grande (máximo 5MB).")


def leer_archivo(archivo):
    nombre = archivo.name.lower()
    if nombre.endswith((".xlsx", ".xls")):
        return pd.read_excel(archivo)
    try:
        return pd.read_csv(archivo)
    except pd.errors.ParserError:
        archivo.seek(0)
        return pd.read_csv(archivo, sep="\t")


def procesar_upload(request):
    """
    Pipeline con validación científica estricta.
    Bloquea la creación automática de cultivos/variedades y exige metadatos de origen completos.
    """
    archivo         = request.FILES.get("archivo")
    tipo           = request.POST.get("tipo_analisis", "16S")
    codigo_muestra = request.POST.get("codigo", "").strip()
    
    # IDs enviados desde los select del formulario frontend
    cultivo_id     = request.POST.get("cultivo", None)
    variedad_id    = request.POST.get("variedad_clon", None)
    
    # 🌍 Datos geográficos
    localidad      = request.POST.get("localidad", "").strip()
    finca_lote     = request.POST.get("finca_lote", "").strip()
    altitud_raw    = request.POST.get("altitud", None)

    # 🛑 VALIDACIONES PREVIAS OBLIGATORIAS
    if not archivo:
        raise ValueError("No se ha proporcionado ningún archivo molecular.")
    if not codigo_muestra:
        raise ValueError("El código identificador de la muestra es obligatorio.")
    if not cultivo_id:
        raise ValueError("Debe seleccionar un Cultivo válido de la lista. Este campo es obligatorio.")
    if not variedad_id:
        raise ValueError("Debe seleccionar una Variedad o Clon específico. Este campo es obligatorio.")
    if not localidad:
        raise ValueError("El campo 'Localidad' (Región/Provincia) es obligatorio para el análisis biogeográfico.")
    if not finca_lote:
        raise ValueError("El campo 'Finca / Lote' es obligatorio para la trazabilidad de la muestra.")

    # Conversión segura de la altitud
    if not altitud_raw or not altitud_raw.strip():
        raise ValueError("El campo 'Altitud' (msnm) es obligatorio para los cálculos de ecología microbiana.")
    
    try:
        altitud = int(altitud_raw)
    except ValueError:
        raise ValueError("La altitud debe ser un número entero válido (metros sobre el nivel del mar).")

    # Validación de archivo y procesamiento bioinformático
    validar_archivo(archivo)
    df_raw = leer_archivo(archivo)

    nivel = request.POST.get("nivel", "genus")
    if nivel not in NIVELES_VALIDOS:
        nivel = "genus"

    # ✅ CORREGIDO: Ahora llamamos al método estático usando la clase correspondiente
    resultado = PipelineProcesamiento.procesar_archivo_df(df_raw, nivel=nivel)

    if not resultado or not resultado.get("data"):
        raise ValueError("El archivo subido no contiene datos taxonómicos válidos o el formato interno es incorrecto.")

    # Bloque transaccional atómico seguro
    with transaction.atomic():
        
        # 1. Validar existencia real del Cultivo en base de datos
        try:
            cultivo = Cultivo.objects.get(id=cultivo_id)
        except Cultivo.DoesNotExist:
            raise ValueError("El cultivo seleccionado no existe en el catálogo del sistema.")

        # 2. Validar existencia real de la Variedad y verificar que pertenezca a ese Cultivo
        try:
            variedad = VariedadClon.objects.get(id=variedad_id, cultivo=cultivo)
        except VariedadClon.DoesNotExist:
            raise ValueError("La variedad/clon seleccionada no existe o no corresponde al cultivo elegido.")

        # 3. Crear el objeto MuestraSuelo con todos los campos rigurosamente llenos
        muestra = MuestraSuelo.objects.create(
            codigo=codigo_muestra,
            cultivo=cultivo,
            variedad_clon=variedad,
            tipo_muestra=request.POST.get("tipo_muestra", "Suelo"),
            observaciones=request.POST.get("observaciones", ""),
            localidad=localidad,
            finca_lote=finca_lote,
            altitud=altitud
        )

        # 4. Registrar el Archivo Molecular de origen
        archivo_mol = ArchivoMolecular.objects.create(
            muestra=muestra,
            tipo_analisis=tipo,
            archivo=archivo,
        )

        # 5. Carga masiva (Bulk Create) de resultados taxonómicos
        ResultadoTaxonomico.objects.bulk_create([
            ResultadoTaxonomico(
                archivo=archivo_mol,
                kingdom=item.get("kingdom", ""),
                phylum=item.get("phylum", ""),
                tax_class=item.get("tax_class", ""),  # Alineado con 'tax_class' del pipeline original
                order=item.get("order", ""),
                family=item.get("family", ""),
                genus=item.get("genus", item.get(nivel, "")),
                species=item.get("species", ""),
                num_hits=item.get("num_hits", 0),
                porcentaje_hits=item.get("%_hits", 0.0),
            )
            for item in resultado["data"]
        ])

    return {
        "total_registros": resultado.get("total_registros", len(resultado["data"])),
        "muestra_id": muestra.id,
        "archivo_molecular_id": archivo_mol.id
    }