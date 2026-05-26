import io
from datetime import datetime

import pandas as pd
from django.db.models import F, Sum
from django.http import HttpResponse

from analisis.models import ResultadoTaxonomico, CatalogoMicroorganismo

MARCADORES_VALIDOS = ("16S", "ITS")
FORMATOS_VALIDOS   = ("pdf", "excel")
NIVELES_VALIDOS    = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
OPCIONES_TOP_N     = [5, 10, 25, 50]
MAPA_NIVELES = {
    "kingdom": "kingdom", "phylum": "phylum", "class": "tax_class",
    "order": "order", "family": "family", "genus": "genus", "species": "species"
}

_historial_reportes: list[dict] = []


def _construir_dataframe(tipo, variedad_id, nivel, top_n):
    campo_db = MAPA_NIVELES.get(nivel, "genus")
    qs = ResultadoTaxonomico.objects.filter(archivo__tipo_analisis=tipo)
    if variedad_id:
        qs = qs.filter(archivo__muestra__variedad_clon_id=variedad_id)

    if not qs.exists():
        return pd.DataFrame()

    data = list(
        qs.values(tax=F(campo_db))
        .annotate(num_hits=Sum("num_hits"), porcentaje_hits=Sum("porcentaje_hits"))
        .order_by("-porcentaje_hits")[:top_n]
    )

    df = pd.DataFrame(data)
    df["porcentaje_hits"] = df["porcentaje_hits"].round(5)

    # Enriquecer con clasificación funcional del catálogo
    df["clasificacion"] = df["tax"].apply(
        lambda nombre: CatalogoMicroorganismo.objects.filter(
            nombre__iexact=nombre, nivel=nivel
        ).values_list("clasificacion", flat=True).first() or "sin_clasificar"
    )

    return df


def generar_reporte_analisis(tipo="16S", producto_id=None, formato="pdf",
                              top_n=10, nivel="genus", usuario=None):
    """
    README: "Salida de Resultados: reportes interpretativos para usuarios finales"
    """
    if tipo not in MARCADORES_VALIDOS:   tipo = "16S"
    if formato not in FORMATOS_VALIDOS:  formato = "pdf"
    if top_n not in OPCIONES_TOP_N:      top_n = 10
    if nivel not in NIVELES_VALIDOS:     nivel = "genus"

    df = _construir_dataframe(tipo, producto_id, nivel, top_n)
    if df.empty:
        raise ValueError("No hay datos disponibles para generar el reporte.")

    total_beneficos     = int((df["clasificacion"] == "benefico").sum())
    total_fitopatogenos = int((df["clasificacion"] == "fitopatogeno").sum())
    total_sin_clas      = int((df["clasificacion"] == "sin_clasificar").sum())

    reporte_id  = len(_historial_reportes) + 1
    fecha_hora  = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_arch = f"reporte_{tipo}_{nivel}_top{top_n}_{fecha_hora}.{formato}"

    entrada = {
        "id": reporte_id, "nombre": nombre_arch, "tipo": tipo,
        "nivel": nivel, "top_n": top_n, "producto_id": producto_id,
        "formato": formato, "fecha": fecha_hora,
        "usuario": str(usuario) if usuario else "Sistema",
        "total_beneficos": total_beneficos,
        "total_fitopatogenos": total_fitopatogenos,
        "total_sin_clas": total_sin_clas,
        "total_registros": len(df),
        "datos": df.to_dict(orient="records"),
        "url": f"/media/reportes/{nombre_arch}",
    }
    _historial_reportes.append(entrada)
    return {"url": entrada["url"], "reporte_id": reporte_id}


def obtener_historial_reportes(tipo=""):
    if tipo in MARCADORES_VALIDOS:
        return [r for r in _historial_reportes if r["tipo"] == tipo]
    return list(_historial_reportes)


def obtener_reporte_por_id(reporte_id):
    try:
        reporte_id = int(reporte_id)
    except (TypeError, ValueError):
        return None
    return next((r for r in _historial_reportes if r["id"] == reporte_id), None)


def exportar_excel(tipo="16S", variedad_id=None, nivel="genus", top_n=10):
    """README: "Salida de Resultados: tablas dinámicas" """
    df = _construir_dataframe(tipo, variedad_id, nivel, top_n)
    if df.empty:
        raise ValueError("No hay datos para exportar.")

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=f"Análisis_{tipo}")

    buffer.seek(0)
    fecha   = datetime.now().strftime("%Y%m%d")
    nombre  = f"analisis_{tipo}_{nivel}_top{top_n}_{fecha}.xlsx"
    response = HttpResponse(
        buffer,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return response