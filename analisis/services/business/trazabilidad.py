"""Conservación de entradas sustituidas y artefactos emitidos para investigación/docencia."""
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
import hashlib
from pathlib import Path
from django.conf import settings
from django.db.models import Model
from analisis.models import ArchivoMolecular, ArchivoMolecularRevision, ReporteArchivado, CatalogoMicroorganismo

def _snapshot(valor):
    if isinstance(valor, Model):
        # No guardar credenciales, correos ni otros campos del usuario.
        if valor._meta.label_lower == settings.AUTH_USER_MODEL.lower():
            return {"id": valor.pk}
        return {campo.attname: _snapshot(getattr(valor, campo.attname))
                for campo in valor._meta.concrete_fields}
    if isinstance(valor, dict):
        return {str(k): _snapshot(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_snapshot(v) for v in valor]
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)

@lru_cache(maxsize=1)
def _version_procesamiento():
    raiz = Path(settings.BASE_DIR)
    digest = hashlib.sha256()
    for ruta in sorted((raiz / "analisis" / "services").rglob("*.py")):
        digest.update(ruta.relative_to(raiz).as_posix().encode())
        digest.update(ruta.read_bytes())
    digest.update((raiz / "analisis" / "constants.py").read_bytes())
    digest.update((raiz / "analisis" / "views" / "reportes.py").read_bytes())
    return {"codigo_sha256": digest.hexdigest(),
            "dependencias_sha256": hashlib.sha256((raiz / "requirements.txt").read_bytes()).hexdigest()}

def archivar_revision(archivo):
    huella = ""
    try:
        with archivo.archivo.open("rb") as original:
            digest = hashlib.sha256()
            for bloque in original.chunks():
                digest.update(bloque)
            huella = digest.hexdigest()
    except FileNotFoundError:
        # Datos antiguos cuyo original ya faltaba: preservar resultados, sin inventar una huella.
        pass
    muestra = archivo.muestra
    return ArchivoMolecularRevision.objects.create(
        muestra=muestra, tipo_analisis=archivo.tipo_analisis, archivo=archivo.archivo.name,
        sha256=huella,
        metadatos={"muestra": _snapshot(muestra), "fecha_carga": archivo.fecha_carga.isoformat(),
                   "original_disponible": bool(huella), **_version_procesamiento()},
        resultados=list(archivo.resultados_taxonomicos.values(
            "kingdom", "phylum", "tax_class", "order", "family", "genus", "species",
            "num_hits", "porcentaje_hits")),
    )

def archivar_reporte(response, datos, formato):
    from django.urls import reverse
    cuerpo = bytes(response.content)
    nombre = response.get("Content-Disposition", "").split('filename="')[-1].rstrip('"')
    catalogo = list(CatalogoMicroorganismo.objects.order_by("pk").values(
        "nombre", "nivel", "marcador", "clasificacion", "descripcion", "referencia"))
    muestras = datos.get("muestras") or ([datos["muestra"]] if datos.get("muestra") else [])
    entradas = []
    for archivo in ArchivoMolecular.objects.filter(
            muestra_id__in=[m.pk for m in muestras], tipo_analisis=datos.get("tipo")):
        huella = None
        try:
            with archivo.archivo.open("rb") as original:
                digest = hashlib.sha256()
                for bloque in original.chunks():
                    digest.update(bloque)
                huella = digest.hexdigest()
        except FileNotFoundError:
            pass
        entradas.append({"archivo_id": archivo.pk, "muestra_id": archivo.muestra_id,
                         "marcador": archivo.tipo_analisis, "ruta": archivo.archivo.name,
                         "sha256": huella, "original_disponible": bool(huella)})
    reporte = ReporteArchivado.objects.create(
        formato=formato, nombre=nombre[:255], sha256=hashlib.sha256(cuerpo).hexdigest(),
        contenido=cuerpo,
        manifiesto={"datos": _snapshot(datos), "catalogo": catalogo, "entradas": entradas,
                    "semilla_estadistica": 42, **_version_procesamiento()},
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Reporte-ID"] = str(reporte.pk)
    response["X-Reporte-SHA256"] = reporte.sha256
    response["Content-Location"] = reverse("analisis:reporte_archivado", args=[reporte.pk])
    return response
