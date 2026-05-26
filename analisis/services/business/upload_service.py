import pandas as pd
from django.db import transaction

from analisis.models import MuestraSuelo, ArchivoMolecular, ResultadoTaxonomico, Cultivo
from analisis.services.processing.pipeline import procesar_archivo_df

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
    archivo        = request.FILES.get("archivo")
    codigo_muestra = request.POST.get("nombre_producto", "").strip()
    tipo           = request.POST.get("tipo", "16S")
    cultivo_id     = request.POST.get("cultivo_id") or request.POST.get("cultivo")
    variedad_id    = request.POST.get("variedad_id") or request.POST.get("variedad")

    if not archivo:
        raise ValueError("Debe subir un archivo.")
    if not codigo_muestra:
        raise ValueError("Debe ingresar un código de muestra.")
    if tipo not in ("16S", "ITS"):
        tipo = "16S"

    validar_archivo(archivo)

    top_n = parse_int_or_default(request.POST.get("top_n"), default=10)
    nivel = request.POST.get("nivel", "genus")
    if nivel not in NIVELES_VALIDOS:
        nivel = "genus"

    df = leer_archivo(archivo)
    resultado = procesar_archivo_df(df, top_n=top_n, nivel=nivel)

    if not resultado["data"]:
        raise ValueError("El archivo no generó resultados tras el procesamiento.")

    with transaction.atomic():
        # Si no se seleccionó cultivo, usar o crear uno genérico
        if cultivo_id:
            cultivo = Cultivo.objects.get(id=cultivo_id)
        else:
            cultivo, _ = Cultivo.objects.get_or_create(
                nombre="Sin especificar",
                defaults={"descripcion": "Cultivo creado automáticamente"}
            )

        muestra_kwargs = {
            "codigo":  codigo_muestra,
            "cultivo": cultivo,
        }
        if variedad_id:
            muestra_kwargs["variedad_clon_id"] = variedad_id

        muestra = MuestraSuelo.objects.create(**muestra_kwargs)

        archivo_mol = ArchivoMolecular.objects.create(
            muestra=muestra,
            tipo_analisis=tipo,
            archivo=archivo,
        )

        ResultadoTaxonomico.objects.bulk_create([
            ResultadoTaxonomico(
                archivo=archivo_mol,
                kingdom=item.get("kingdom", ""),
                phylum=item.get("phylum", ""),
                tax_class=item.get("class", ""),
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
        "nivel":           nivel,
        "top_n":           top_n,
        "muestra_id":      muestra.id,
    }