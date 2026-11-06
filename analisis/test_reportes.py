"""Generación de PDF y Excel (individual, comparativo e informe general) de punta a punta."""
import io

from openpyxl import load_workbook
from django.urls import reverse

from analisis.utilidades_pruebas import PruebaConMedia, crear_muestra, crear_usuario

TAXA_2 = [("Bacillus", "cereus", 20), ("Pseudomonas", "putida", 50), ("Rhizobium", "etli", 30)]
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class GeneracionDeReportesTests(PruebaConMedia):

    def setUp(self):
        super().setUp()
        self.client.force_login(crear_usuario("estudiante", "estudiante"))  # los reportes son para todos
        self.m1 = crear_muestra("M-R1", self.cultivo, self.variedad)
        self.m2 = crear_muestra("M-R2", self.cultivo, self.variedad, taxa=TAXA_2)

    def _post(self, url, **datos):
        datos = {"tipo": "16S", "nivel": "genus", "top_n": 10, **datos}
        return self.client.post(reverse(url), datos)

    def _cuerpo(self, resp):
        return b"".join(resp.streaming_content) if resp.streaming else resp.content

    def _assert_pdf(self, resp, nombre_contiene):
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn(nombre_contiene, resp["Content-Disposition"])
        cuerpo = self._cuerpo(resp)
        self.assertTrue(cuerpo.startswith(b"%PDF"))
        self.assertGreater(len(cuerpo), 5_000)

    def _hojas_excel(self, resp):
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertTrue(resp["Content-Type"].startswith(TIPO_XLSX), resp["Content-Type"])
        return load_workbook(io.BytesIO(self._cuerpo(resp)), read_only=True).sheetnames

    def test_pdf_individual(self):
        self._assert_pdf(self._post("analisis:generar_reporte", formato="pdf", muestra_id=self.m1.pk), "M-R1")

    def test_pdf_comparativo(self):
        resp = self._post("analisis:generar_reporte", formato="pdf", muestra_id=[self.m1.pk, self.m2.pk])
        self._assert_pdf(resp, "reporte_comparativo")

    def test_excel_individual(self):
        hojas = self._hojas_excel(self._post("analisis:generar_reporte", formato="excel", muestra_id=self.m1.pk))
        self.assertGreaterEqual(len(hojas), 5)
        self.assertIn("Índice", " ".join(hojas))

    def test_excel_comparativo(self):
        hojas = self._hojas_excel(self._post("analisis:generar_reporte", formato="excel",
                                             muestra_id=[self.m1.pk, self.m2.pk]))
        self.assertGreaterEqual(len(hojas), 5)

    def test_informe_general_pdf_y_excel(self):
        self._assert_pdf(self._post("analisis:generar_reporte_general", formato="pdf", muestra_id=self.m1.pk),
                         "informe_general")
        hojas = self._hojas_excel(self._post("analisis:generar_reporte_general", formato="excel",
                                             muestra_id=self.m1.pk))
        self.assertIn("Resumen", hojas)

    def test_parametros_invalidos(self):
        resp = self._post("analisis:generar_reporte", formato="docx", muestra_id=self.m1.pk)
        self.assertEqual(resp.status_code, 400)
        resp = self._post("analisis:generar_reporte_general", formato="pdf", muestra_id="abc")
        self.assertEqual(resp.status_code, 400)
        resp = self._post("analisis:generar_reporte_general", formato="pdf", muestra_id="999999")
        self.assertEqual(resp.status_code, 404)
        # tipo/nivel/top_n inválidos se normalizan y el reporte se genera igual
        resp = self._post("analisis:generar_reporte", formato="pdf", muestra_id=self.m1.pk,
                          tipo="XX", nivel="drop", top_n="abc")
        self._assert_pdf(resp, "reporte_16S_genus")

    def test_get_no_permitido(self):
        self.assertEqual(self.client.get(reverse("analisis:generar_reporte")).status_code, 405)
