"""Bioquímica: los PDF guardados no quedan huérfanos si el ensayo no se guarda."""
import os
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from analisis.utilidades_pruebas import PruebaConMedia, crear_usuario
from bioquimica.models import EnsayoMicrobiologico, RecuentoUFC


def _pdfs_en_disco():
    raiz = settings.MEDIA_ROOT
    return sorted(f for _, _, fs in os.walk(raiz) for f in fs if f.lower().endswith(".pdf"))


def _pdf(nombre="informe.pdf"):
    return SimpleUploadedFile(nombre, b"%PDF-1.4 contenido", content_type="application/pdf")


RESULTADO_PARSER = {
    "tipo": "recuento",
    "formato": "mag",
    "header": {"codigo": "MAG-001-2026", "nombre_muestra": "Suelo 1"},
    "datos": [{"tipo_organismo": "bacteria", "nombre": "Bacillus spp.", "coeficiente": 2.5, "exponente": 6}],
}


class PdfImportadoTests(PruebaConMedia):

    def setUp(self):
        super().setUp()
        self.client.force_login(crear_usuario("docente", "docente"))

    def _subir(self):
        return self.client.post(reverse("bioquimica:subir_pdf"), {"archivos": [_pdf()]}, follow=True)

    def test_importacion_valida(self):
        with mock.patch("bioquimica.services.pdf_parser.parsear_pdf", return_value=RESULTADO_PARSER):
            self._subir()
        self.assertEqual(EnsayoMicrobiologico.objects.get().codigo, "MAG-001-2026")
        self.assertEqual(len(_pdfs_en_disco()), 1)

    def test_fallo_al_guardar_filas_no_deja_pdf_huerfano(self):
        with mock.patch("bioquimica.services.pdf_parser.parsear_pdf", return_value=RESULTADO_PARSER), \
                mock.patch.object(RecuentoUFC, "save", side_effect=RuntimeError("fallo simulado")), \
                self.assertLogs("bioquimica.views", level="ERROR"):
            self._subir()
        self.assertFalse(EnsayoMicrobiologico.objects.exists())
        self.assertEqual(_pdfs_en_disco(), [])

    def test_codigo_guardado_en_paralelo_se_informa_como_duplicado(self):
        # Simula que otro proceso creó el mismo código después de la comprobación exists()
        from django.db.models.query import QuerySet
        EnsayoMicrobiologico.objects.create(codigo="MAG-001-2026", tipo="recuento", nombre_muestra="Otra")
        exists_original = QuerySet.exists

        def exists_que_no_ve_el_otro(qs):
            return False if qs.model is EnsayoMicrobiologico else exists_original(qs)

        with mock.patch("bioquimica.services.pdf_parser.parsear_pdf", return_value=RESULTADO_PARSER), \
                mock.patch.object(QuerySet, "exists", autospec=True, side_effect=exists_que_no_ve_el_otro):
            resp = self._subir()
        self.assertIn("ya existente", resp.content.decode())
        self.assertEqual(EnsayoMicrobiologico.objects.count(), 1)
        self.assertEqual(_pdfs_en_disco(), [])


class IngresoManualTests(PruebaConMedia):

    def setUp(self):
        super().setUp()
        self.client.force_login(crear_usuario("docente", "docente"))

    def _datos(self, **extra):
        datos = {"codigo": "MAN-001", "tipo": "recuento", "nombre_muestra": "Suelo", "archivo_pdf": _pdf("respaldo.pdf")}
        datos.update(extra)
        return datos

    def test_sin_filas_no_guarda_ensayo_ni_pdf(self):
        resp = self.client.post(reverse("bioquimica:ingreso_manual"), self._datos())
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(EnsayoMicrobiologico.objects.exists())
        self.assertEqual(_pdfs_en_disco(), [])

    def test_ingreso_valido_guarda_pdf(self):
        datos = self._datos(rec_nombre_0="Bacillus", rec_tipo_0="bacteria", rec_coeficiente_0="2.5", rec_exponente_0="6")
        resp = self.client.post(reverse("bioquimica:ingreso_manual"), datos)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(EnsayoMicrobiologico.objects.get().recuentos.count(), 1)
        self.assertEqual(len(_pdfs_en_disco()), 1)
