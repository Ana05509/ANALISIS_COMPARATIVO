"""Los errores inesperados se registran en el log y no muestran detalles internos al usuario."""
from unittest import mock

from django.urls import reverse

from analisis.utilidades_pruebas import PruebaConMedia, crear_muestra, crear_usuario

SECRETO = 'relation "tabla_interna" does not exist'


class ErroresSinDetalleInternoTests(PruebaConMedia):

    def setUp(self):
        super().setUp()
        self.docente = crear_usuario("docente", "docente")
        self.muestra = crear_muestra("M-ERR", self.cultivo, self.variedad)
        self.client.force_login(self.docente)

    def test_generar_reporte_oculta_el_detalle_y_lo_registra(self):
        with mock.patch("analisis.views.reportes._construir_datos_reporte", side_effect=RuntimeError(SECRETO)), \
                self.assertLogs("analisis.views.reportes", level="ERROR") as logs:
            resp = self.client.post(reverse("analisis:generar_reporte"),
                                    {"formato": "pdf", "muestra_id": self.muestra.pk})
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn(SECRETO, resp.content.decode())
        self.assertIn("No se pudo generar el reporte", resp.json()["error"])
        self.assertIn(SECRETO, "\n".join(logs.output))  # el traceback sí queda en el log

    def test_dashboard_oculta_el_detalle(self):
        with mock.patch("analisis.views.dashboard.obtener_diversidad", side_effect=RuntimeError(SECRETO)), \
                self.assertLogs("analisis.views.dashboard", level="ERROR"):
            resp = self.client.get(reverse("analisis:dashboard"))
        self.assertNotIn(SECRETO, resp.content.decode())

    def test_subida_con_error_inesperado_oculta_el_detalle(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from analisis.utilidades_pruebas import CSV_VALIDO
        archivo = SimpleUploadedFile("datos.csv", CSV_VALIDO.encode(), content_type="text/csv")
        with mock.patch("analisis.views.subir_datos.procesar_upload", side_effect=RuntimeError(SECRETO)), \
                self.assertLogs("analisis.views.subir_datos", level="ERROR"):
            resp = self.client.post(
                reverse("analisis:subir_datos"),
                {"nombre_producto": "M-NUEVA", "localidad": "Cotopaxi", "finca_lote": "L1",
                 "cultivo": self.cultivo.pk, "variedad_clon": self.variedad.pk, "tipo": "16S",
                 "archivo": archivo},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn(SECRETO, resp.content.decode())

    def test_pdf_bioquimica_ilegible_no_muestra_el_traceback(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        pdf = SimpleUploadedFile("informe.pdf", b"%PDF-1.4 roto", content_type="application/pdf")
        with mock.patch("bioquimica.services.pdf_parser.parsear_pdf", side_effect=RuntimeError(SECRETO)), \
                self.assertLogs("bioquimica.views", level="ERROR"):
            resp = self.client.post(reverse("bioquimica:subir_pdf"), {"archivos": [pdf]}, follow=True)
        contenido = resp.content.decode()
        self.assertNotIn(SECRETO, contenido)
        self.assertIn("informe.pdf", contenido)
