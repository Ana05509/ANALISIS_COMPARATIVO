"""Regresión de los defectos confirmados en la auditoría; solo datos sintéticos."""
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import io
import unittest
import warnings

import numpy as np
import pandas as pd
from scipy.spatial.distance import pdist, squareform
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, RequestFactory, override_settings
from django.urls import reverse

from analisis.admin import _disparar_pipeline, ArchivoMolecularForm, MuestraSueloForm
from analisis.models import ArchivoMolecular, Cultivo, ResultadoTaxonomico, VariedadClon
from analisis.services.processing.pipeline import PipelineProcesamiento as Pipeline
from analisis.services.processing.diversity import DiversityService as Diversity
from analisis.services.business.upload_service import leer_archivo
from analisis.services.business.analysis_service import obtener_permanova
from analisis.utilidades_pruebas import PruebaConMedia, crear_muestra, crear_usuario, CSV_VALIDO
from bioquimica.models import RecuentoUFC
from bioquimica.services.pdf_parser import _parsear_ufc, _parsear_aislamiento
from config.urls import media_protegida

try:
    from skbio.stats.distance import DistanceMatrix, permanova, permdisp
    SKBIO = True
except ImportError:
    SKBIO = False


class ValidacionImportacionTests(SimpleTestCase):
    def _df(self):
        return pd.read_csv(io.StringIO(CSV_VALIDO))

    def test_conteos_no_se_truncan_ni_descartan(self):
        for valor in (1.9, "abc", -1, float("inf"), float("nan"), 2147483648):
            with self.subTest(valor=valor):
                df = self._df().astype({"num_hits": object})
                df.loc[0, "num_hits"] = valor
                with self.assertRaisesRegex(ValueError, "num_hits.*filas 2"):
                    Pipeline.procesar_archivo_df(df)

    def test_porcentajes_invalidos_se_rechazan(self):
        for valor in (-1, 999, float("inf"), "abc"):
            with self.subTest(valor=valor):
                df = self._df().astype({"%_hits": object})
                df.loc[0, "%_hits"] = valor
                with self.assertRaises(ValueError):
                    Pipeline.procesar_archivo_df(df)

    def test_discrepancia_conteo_porcentaje_se_informa(self):
        df = self._df()
        df.loc[0, "%_hits"] = 20
        with self.assertRaisesRegex(ValueError, "porcentajes no corresponden"):
            Pipeline.procesar_archivo_df(df)

    def test_excel_falso_no_se_acepta_por_extension(self):
        with self.assertRaisesRegex(ValueError, "No se pudo leer"):
            leer_archivo(SimpleUploadedFile("falso.xlsx", b"no es un excel"))

    def test_excel_expandido_se_rechaza_antes_del_parser(self):
        item = SimpleNamespace(file_size=101 * 1024 * 1024)
        with mock.patch("analisis.services.business.upload_service.zipfile.ZipFile") as libro:
            libro.return_value.__enter__.return_value.infolist.return_value = [item]
            with self.assertRaisesRegex(ValueError, "100 MB"):
                leer_archivo(SimpleUploadedFile("grande.xlsx", b"synthetic"))


class EstadisticaAuditoriaTests(SimpleTestCase):
    def test_bray_curtis_no_produce_nan_por_vacios(self):
        with self.assertRaisesRegex(ValueError, "sin lecturas"):
            Diversity.matriz_bray_curtis([[0, 0], [0, 0], [1, 0]])

    def test_permanova_rechaza_matrices_invalidas(self):
        for matriz in (
            [[0, np.nan, 1], [np.nan, 0, 1], [1, 1, 0]],
            [[0, 1, 1], [2, 0, 1], [1, 1, 0]],
            [[0, -1, 1], [-1, 0, 1], [1, 1, 0]],
        ):
            with self.assertRaises(ValueError):
                Diversity.calcular_permanova(matriz, ["A", "A", "B"])

    def test_separacion_perfecta_no_se_publica_como_f_finito(self):
        x = np.array([0, 0, 1, 1])
        r = Diversity.calcular_permanova(abs(x[:, None] - x[None, :]), ["A", "A", "B", "B"])
        self.assertFalse(r["ejecutado"])
        self.assertIn("intragrupo", r["razon"])

    @unittest.skipUnless(SKBIO, "Requiere scikit-bio de desarrollo")
    def test_permanova_cuenta_permutaciones_con_f_infinito(self):
        x = np.array([0, 0, 1, 1])
        m = abs(x[:, None] - x[None, :])
        g = ["A", "B", "A", "B"]
        r = Diversity.calcular_permanova(m, g, n_permutaciones=999, semilla=42)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            ref = permanova(DistanceMatrix(m), g, permutations=999, seed=42)
        self.assertEqual(r["p_value"], 1.0)
        self.assertEqual(r["p_value"], ref["p-value"])

    @unittest.skipUnless(SKBIO, "Requiere scikit-bio de desarrollo")
    def test_permdisp_p_valor_coincide_con_referencia(self):
        rng = np.random.default_rng(5)
        x = np.vstack([rng.normal(size=(4, 3)), rng.normal(size=(4, 3))*3,
                       rng.normal(size=(4, 3))*2])
        m = squareform(pdist(x))
        g = ["A"]*4 + ["B"]*4 + ["C"]*4
        r = Diversity.calcular_permdisp(m, g, n_permutaciones=499, semilla=42)
        ref = permdisp(DistanceMatrix(m), g, test="centroid", permutations=499, seed=42)
        self.assertAlmostEqual(r["p_value"], ref["p-value"], places=4)
        self.assertFalse(r["significativo"])

    def test_riqueza_y_conjuntos_excluyen_no_asignados_y_ceros(self):
        df = pd.DataFrame({"genus": ["Bacillus", "Unclassified", "Pseudomonas"],
                           "%_hits": [50, 50, 0]})
        r = Diversity.calcular_diversidad_beta(df, df)
        self.assertEqual(r["total_taxa_reales_a"], 1)
        self.assertEqual(r["compartidos_lista"], ["bacillus"])


class ParserUFCRegressionTests(SimpleTestCase):
    def test_notaciones_cientificas_y_superindices(self):
        for texto, coef, exp in (
            ("3 x 10^6 UFC/g", "3", 6),
            ("3 x 106 UFC/g", "3", 6),
            ("2,5 × 10¹² UFC/g", "2.5", 12),
            ("4 × 10⁻² UFC/g", "4", -2),
            ("3 x 10-2 UFC/g", "3", -2),
        ):
            with self.subTest(texto=texto):
                self.assertEqual(_parsear_ufc(texto), (Decimal(coef), exp, False))

    def test_limite_de_deteccion_se_conserva(self):
        for limite in (10, 100):
            coef, exp, menor = _parsear_ufc(f"<{limite} UFC/g")
            r = RecuentoUFC(coeficiente=coef, exponente=exp, menor_que_limite=menor)
            self.assertEqual(r.valor_display, f"<{limite} UFC/g")
        self.assertEqual(_parsear_ufc("<1 UFC/g"), (None, None, True))

    def test_notacion_incompatible_no_se_interpreta_por_fragmentos(self):
        with self.assertRaises(ValueError):
            _parsear_ufc("3 x 10^? UFC/g")

    def test_pagina_ambigua_no_mezcla_organismos(self):
        page = SimpleNamespace(
            extract_text=lambda: "Bacteria aislada: Bacillus\nBacteria aislada: Pseudomonas",
            extract_tables=lambda: [[["N", "PRUEBA", "RESULTADO"], ["1", "Catalasa", "+"]]],
        )
        with self.assertRaisesRegex(ValueError, "varios organismos"):
            _parsear_aislamiento(SimpleNamespace(pages=[page]))


class IntegridadYSeguridadTests(PruebaConMedia):
    def setUp(self):
        super().setUp()
        self.usuario = crear_usuario("auditoria", "admin", is_staff=True, is_superuser=True)
        self.client.force_login(self.usuario)
        self.muestra = crear_muestra("AUD-1", self.cultivo, self.variedad)
        self.archivo = self.muestra.archivos_moleculares.get()
        self.archivo.archivo.save("original.csv", SimpleUploadedFile("original.csv", CSV_VALIDO.encode()))

    def test_media_autoriza_destino_canonico(self):
        req = RequestFactory().get("/media/prueba")
        req.user = SimpleNamespace(is_authenticated=True, is_active=True, is_staff=False,
                                   is_superuser=False, rol="estudiante")
        nombre = self.archivo.archivo.name
        for ruta in (nombre, "./"+nombre, "avatars/../"+nombre, nombre.replace("/", "\\")):
            with self.subTest(ruta=ruta), self.assertRaises(PermissionDenied):
                media_protegida(req, ruta)

    def test_admin_archivo_invalido_conserva_original_y_resultados(self):
        nombre = self.archivo.archivo.name
        url = reverse("admin:analisis_archivomolecular_change", args=[self.archivo.pk])
        respuesta = self.client.post(url, {
            "muestra": self.muestra.pk, "tipo_analisis": "16S",
            "archivo": SimpleUploadedFile("corrupto.csv", b"genus,num_hits\nBacillus,10"),
            "_save": "Guardar",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.archivo.refresh_from_db()
        self.assertEqual(self.archivo.archivo.name, nombre)
        self.assertEqual(self.archivo.resultados_taxonomicos.count(), 3)
        self.assertTrue(self.archivo.archivo.storage.exists(nombre))

    def test_admin_fallo_bulk_hace_rollback_de_resultados(self):
        with mock.patch("analisis.admin.ResultadoTaxonomico.objects.bulk_create",
                        side_effect=RuntimeError("fallo sintetico")):
            with self.assertRaises(RuntimeError):
                _disparar_pipeline(self.archivo, RequestFactory().get("/"))
        self.assertEqual(self.archivo.resultados_taxonomicos.count(), 3)

    def test_unicidad_marcador_en_base_de_datos(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ArchivoMolecular.objects.create(muestra=self.muestra, tipo_analisis="16S", archivo="otro.csv")

    def test_altitud_admin_y_base_de_datos(self):
        with self.assertRaises(ValidationError):
            MuestraSueloForm.base_fields["altitud"].clean("9000")
        with self.assertRaises(IntegrityError), transaction.atomic():
            type(self.muestra).objects.filter(pk=self.muestra.pk).update(altitud=-1)

    def test_variedad_de_otro_cultivo_rechazada(self):
        otro = Cultivo.objects.create(nombre="Otro")
        variedad = VariedadClon.objects.create(nombre="Otra", cultivo=otro)
        self.muestra.variedad_clon = variedad
        with self.assertRaises(ValidationError):
            self.muestra.clean()

    def test_borrado_fisico_solo_despues_de_commit(self):
        storage, nombre = self.archivo.archivo.storage, self.archivo.archivo.name
        with self.captureOnCommitCallbacks(execute=True):
            self.archivo.delete()
            self.assertTrue(storage.exists(nombre))
        self.assertFalse(storage.exists(nombre))

    def test_borrado_con_rollback_conserva_original(self):
        storage, nombre = self.archivo.archivo.storage, self.archivo.archivo.name
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    self.archivo.delete()
                    raise ValueError("cancelar")
            except ValueError:
                pass
        self.assertTrue(storage.exists(nombre))

    def test_pdf_no_interpreta_metadata_como_imagen(self):
        texto = '<img src="http://audit.invalid/sintetico.png"/>'
        self.muestra.localidad = texto
        self.muestra.observaciones = texto
        self.muestra.save()
        ResultadoTaxonomico.objects.filter(archivo=self.archivo).update(genus=texto)
        with mock.patch("reportlab.platypus.paraparser.ImageReader",
                        side_effect=AssertionError("Se intentó interpretar una imagen externa")):
            resp = self.client.post(reverse("analisis:generar_reporte"), {
                "tipo": "16S", "nivel": "genus", "top_n": 10, "formato": "pdf",
                "muestra_id": self.muestra.pk,
            })
        self.assertEqual(resp.status_code, 200, resp.content[:200])
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_permanova_omite_muestras_sin_asignacion(self):
        b = crear_muestra("AUD-2", self.cultivo, self.variedad, taxa=[("Unclassified", "Unclassified", 100)])
        c = crear_muestra("AUD-3", self.cultivo, self.variedad, taxa=[("Unclassified", "Unclassified", 100)])
        self.assertIsNone(obtener_permanova(muestra_ids=[self.muestra.pk, b.pk, c.pk]))



    def test_reporte_archivado_no_cambia_al_editar_catalogo(self):
        from analisis.models import CatalogoMicroorganismo, ReporteArchivado
        resp = self.client.post(reverse("analisis:generar_reporte"), {
            "tipo": "16S", "nivel": "genus", "top_n": 10, "formato": "excel",
            "muestra_id": self.muestra.pk,
        })
        self.assertEqual(resp.status_code, 200)
        original = resp.content
        CatalogoMicroorganismo.objects.update(clasificacion="neutral")
        congelado = self.client.get(resp["Content-Location"])
        self.assertEqual(congelado.status_code, 200)
        self.assertEqual(congelado.content, original)
        registro = ReporteArchivado.objects.get(pk=resp["X-Reporte-ID"])
        self.assertTrue(registro.manifiesto["catalogo"])
        import hashlib
        self.assertEqual(registro.manifiesto["entradas"][0]["sha256"],
                         hashlib.sha256(CSV_VALIDO.encode()).hexdigest())
        self.assertIn("codigo_sha256", registro.manifiesto)
        self.client.logout()
        self.assertEqual(self.client.get(resp["Content-Location"]).status_code, 302)

    def test_clasificacion_no_hereda_un_epiteto_o_genero(self):
        from analisis.constants import clasificar_taxon
        self.assertEqual(clasificar_taxon("Bacillus subtilis", {"subtilis": "fitopatogeno"}, "species"),
                         "sin_clasificar")
        self.assertEqual(clasificar_taxon("Bacillus subtilis", {"bacillus": "fitopatogeno"}, "species"),
                         "sin_clasificar")


    def test_admin_error_al_persistir_restauracion_completa(self):
        from analisis.models import ArchivoMolecularRevision
        original = self.archivo.archivo.name
        url = reverse("admin:analisis_archivomolecular_change", args=[self.archivo.pk])
        with mock.patch("analisis.admin.ResultadoTaxonomico.objects.bulk_create",
                        side_effect=RuntimeError("fallo sintetico")), self.assertLogs("django.request", level="ERROR"):
            with self.assertRaises(RuntimeError):
                self.client.post(url, {
                    "muestra": self.muestra.pk, "tipo_analisis": "16S",
                    "archivo": SimpleUploadedFile("reemplazo.csv", CSV_VALIDO.encode()),
                    "_save": "Guardar",
                })
        self.archivo.refresh_from_db()
        self.assertEqual(self.archivo.archivo.name, original)
        self.assertEqual(self.archivo.resultados_taxonomicos.count(), 3)
        self.assertFalse(ArchivoMolecularRevision.objects.exists())
        self.assertTrue(self.archivo.archivo.storage.exists(original))
        self.assertFalse(any("reemplazo" in p.name for p in Path(self._media_tmp).rglob("*")))

    def test_reporte_sin_cobertura_no_declara_riesgo(self):
        from analisis.models import CatalogoMicroorganismo, ReporteArchivado
        CatalogoMicroorganismo.objects.all().delete()
        resp = self.client.post(reverse("analisis:generar_reporte"), {
            "tipo": "16S", "nivel": "genus", "top_n": 10, "formato": "pdf",
            "muestra_id": self.muestra.pk,
        })
        self.assertEqual(resp.status_code, 200)
        datos = ReporteArchivado.objects.get(pk=resp["X-Reporte-ID"]).manifiesto["datos"]
        self.assertIsNone(datos["indice_salud"])
        self.assertEqual(datos["nivel_salud"], "NO ESTIMABLE")

    def test_revision_conserva_lecturas_y_huella_del_original(self):
        from analisis.services.business.trazabilidad import archivar_revision
        import hashlib
        revision = archivar_revision(self.archivo)
        self.assertEqual(revision.sha256, hashlib.sha256(CSV_VALIDO.encode()).hexdigest())
        with self.captureOnCommitCallbacks(execute=True):
            self.archivo.delete()
        self.assertTrue(revision.archivo.storage.exists(revision.archivo.name))
        self.assertEqual(sum(r["num_hits"] for r in revision.resultados), 100)

    def test_reporte_corrupto_no_se_descarga(self):
        from analisis.models import ReporteArchivado
        reporte = ReporteArchivado.objects.create(
            formato="pdf", nombre="sintetico.pdf", sha256="0"*64, contenido=b"%PDF-sintetico")
        with self.assertLogs("analisis.views.reportes", level="ERROR"):
            resp = self.client.get(reverse("analisis:reporte_archivado", args=[reporte.pk]))
        self.assertEqual(resp.status_code, 500)


    def test_comparar_avisa_al_excluir_muestras_sin_asignacion(self):
        b = crear_muestra("AUD-SIN-ASIGNAR", self.cultivo, self.variedad,
                          taxa=[("Unclassified", "Unclassified", 100)])
        resp = self.client.get(reverse("analisis:comparar"), {
            "marcador": "16S", "nivel": "genus", "top_n": 10,
            "muestras": [self.muestra.pk, b.pk],
        })
        self.assertEqual(resp.status_code, 200)
        avisos = " ".join(str(m) for m in resp.context["messages"])
        self.assertIn("AUD-SIN-ASIGNAR", avisos)
        self.assertIn("Sin lecturas asignadas", avisos)
