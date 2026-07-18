# analisis/services/business/report_generation_service.py
import io
from datetime import datetime
import pandas as pd
from django.db.models import F, Sum
from django.http import HttpResponse
from collections import deque

from analisis.models import ResultadoTaxonomico, CatalogoMicroorganismo
from analisis.constants import MARCADORES_VALIDOS, NIVELES_VALIDOS, OPCIONES_TOP_N, MAPA_NIVELES

FORMATOS_VALIDOS = ("pdf", "excel")

_historial_reportes = deque(maxlen=200)

class ReportGenerationService:
    @staticmethod
    def _construir_dataframe(tipo, variedad_id, nivel, top_n):
        campo_db = MAPA_NIVELES.get(nivel, "genus")
        qs = ResultadoTaxonomico.objects.filter(archivo__tipo_analisis=tipo)
        if variedad_id:
            qs = qs.filter(archivo__muestra__variedad_clon_id=variedad_id)
        if not qs.exists():
            return pd.DataFrame()

        # grand_total desde TODOS los taxa antes del slice
        grand_total = qs.aggregate(total=Sum("num_hits"))["total"] or 1

        data = list(
            qs.values(tax=F(campo_db))
            .annotate(total_num_hits=Sum("num_hits"))
            .order_by("-total_num_hits")[:top_n]
        )
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df.rename(columns={"total_num_hits": "num_hits"}, inplace=True)
        # porcentaje_hits recalculado sobre grand_total real (no suma de porcentajes)
        df["porcentaje_hits"] = (df["num_hits"] / grand_total * 100).round(5)
        catalogo_map = {
            obj["nombre"].lower(): obj["clasificacion"]
            for obj in CatalogoMicroorganismo.objects.filter(
                nivel=nivel, marcador=tipo
            ).values("nombre", "clasificacion")
        }
        df["clasificacion"] = df["tax"].apply(
            lambda nombre: catalogo_map.get(str(nombre).lower(), "sin_clasificar")
        )
        return df

    @staticmethod
    def generar_reporte_analisis(tipo="16S", variedad_id=None, formato="pdf",
                                 top_n=10, nivel="genus", usuario=None):
        tipo_clean = tipo if tipo in MARCADORES_VALIDOS else "16S"
        formato_clean = formato if formato in FORMATOS_VALIDOS else "pdf"
        top_n_clean = top_n if top_n in OPCIONES_TOP_N else 10
        nivel_clean = nivel if nivel in NIVELES_VALIDOS else "genus"
        df = ReportGenerationService._construir_dataframe(tipo_clean, variedad_id, nivel_clean, top_n_clean)
        if df.empty:
            raise ValueError("No hay datos biométricos disponibles para los criterios seleccionados.")
        total_beneficos = int((df["clasificacion"] == "benefico").sum())
        total_fitopatogenos = int((df["clasificacion"] == "fitopatogeno").sum())
        total_sin_clas = int((df["clasificacion"] == "sin_clasificar").sum())
        reporte_id = len(_historial_reportes) + 1
        fecha_hora = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_arch = f"reporte_{tipo_clean}_{nivel_clean}_top{top_n_clean}_{fecha_hora}.{formato_clean}"
        entrada = {
            "id": reporte_id, "nombre": nombre_arch, "tipo": tipo_clean,
            "nivel": nivel_clean, "top_n": top_n_clean, "variedad_id": variedad_id,
            "formato": formato_clean, "fecha": fecha_hora,
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

    @staticmethod
    def obtener_historial_reportes(tipo=""):
        if tipo in MARCADORES_VALIDOS:
            return [r for r in _historial_reportes if r["tipo"] == tipo]
        return list(_historial_reportes)

    @staticmethod
    def obtener_reporte_por_id(reporte_id):
        try:
            r_id = int(reporte_id)
        except (TypeError, ValueError):
            return None
        return next((r for r in _historial_reportes if r["id"] == r_id), None)

    @staticmethod
    def exportar_excel(tipo="16S", variedad_id=None, nivel="genus", top_n=10):
        tipo_clean = tipo if tipo in MARCADORES_VALIDOS else "16S"
        nivel_clean = nivel if nivel in NIVELES_VALIDOS else "genus"
        top_n_clean = top_n if top_n in OPCIONES_TOP_N else 10
        df = ReportGenerationService._construir_dataframe(tipo_clean, variedad_id, nivel_clean, top_n_clean)
        if df.empty:
            raise ValueError("No se encontraron registros moleculares para estructurar el archivo Excel.")
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=f"Analisis_{tipo_clean}")
        buffer.seek(0)
        fecha = datetime.now().strftime("%Y%m%d")
        nombre = f"analisis_{tipo_clean}_{nivel_clean}_top{top_n_clean}_{fecha}.xlsx"
        response = HttpResponse(
            buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return response