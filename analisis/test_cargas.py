"""Carga de archivos moleculares: válidas, inválidas, reemplazos, fallos parciales y archivos en disco."""
import os
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from analisis.models import ArchivoMolecular, Cultivo, MuestraSuelo, ResultadoTaxonomico, VariedadClon
from analisis.services.processing.pipeline import PipelineProcesamiento
from analisis.utilidades_pruebas import CSV_VALIDO, PruebaConMedia, crear_usuario

import pandas as pd

CSV_SIN_COLUMNAS = "genus,num_hits\nBacillus,10\n"


def _archivos_en_disco():
    raiz = os.path.join(settings.MEDIA_ROOT, "archivos_moleculares")
    if not os.path.isdir(raiz):
        return []
    return sorted(os.path.relpath(os.path.join(d, f), raiz).replace("\\", "/")
                  for d, _, fs in os.walk(raiz) for f in fs)


class CargaMolecularTests(PruebaConMedia):

    def setUp(self):
        super().setUp()
        self.client.force_login(crear_usuario("docente", "docente"))

    def _subir(self, contenido=CSV_VALIDO, nombre="datos.csv", codigo="m-001", **extra):
        datos = {
            "nombre_producto": codigo, "localidad": "Cotopaxi", "finca_lote": "Lote 1", "altitud": "2800",
            "cultivo": self.cultivo.pk, "variedad_clon": self.variedad.pk, "tipo": "16S",
            "archivo": SimpleUploadedFile(nombre, contenido.encode(), content_type="text/csv"),
        }
        datos.update(extra)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("analisis:subir_datos"), datos, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    # Cargas válidas

    def test_carga_valida_crea_muestra_archivo_y_resultados(self):
        resp = self._subir()
        self.assertEqual(resp.status_code, 200, resp.content)
        muestra = MuestraSuelo.objects.get(codigo="M-001")  # código normalizado a mayúsculas
        self.assertEqual(ArchivoMolecular.objects.filter(muestra=muestra).count(), 1)
        self.assertEqual(
            sorted(ResultadoTaxonomico.objects.values_list("genus", "num_hits")),
            [("Bacillus", 60), ("Pseudomonas", 30), ("Streptomyces", 10)],
        )
        self.assertEqual(len(_archivos_en_disco()), 1)

    # Cargas inválidas

    def test_columnas_faltantes_no_deja_registros(self):
        resp = self._subir(CSV_SIN_COLUMNAS)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["tipo"], "columnas")
        self.assertFalse(MuestraSuelo.objects.exists())
        self.assertEqual(_archivos_en_disco(), [])

    def test_archivo_invalido_no_crea_cultivo_ni_variedad_manual(self):
        resp = self._subir(CSV_SIN_COLUMNAS, cultivo="", variedad_clon="",
                           cultivo_manual="Maní", variedad_manual="INIAP-381")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Cultivo.objects.filter(nombre="Maní").exists())
        self.assertFalse(VariedadClon.objects.filter(nombre="INIAP-381").exists())

    def test_archivo_invalido_no_crea_variedad_manual_de_un_cultivo_existente(self):
        resp = self._subir(CSV_SIN_COLUMNAS, variedad_clon="", variedad_manual="Nacional")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(VariedadClon.objects.filter(nombre="Nacional").exists())

    def test_carga_valida_con_cultivo_y_variedad_manual(self):
        resp = self._subir(cultivo="", variedad_clon="", cultivo_manual="Maní", variedad_manual="INIAP-381")
        self.assertEqual(resp.status_code, 200, resp.content)
        muestra = MuestraSuelo.objects.get(codigo="M-001")
        self.assertEqual((muestra.cultivo.nombre, muestra.variedad_clon.nombre), ("Maní", "INIAP-381"))

    def test_carga_valida_con_variedad_manual_de_cultivo_existente(self):
        resp = self._subir(variedad_clon="", variedad_manual="Nacional")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(MuestraSuelo.objects.get().variedad_clon.nombre, "Nacional")

    # Reemplazos

    def test_duplicado_sin_confirmar_no_modifica_nada(self):
        self._subir()
        resp = self._subir(codigo="M-001", localidad="Otra")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(MuestraSuelo.objects.get().localidad, "Cotopaxi")
        self.assertEqual(len(_archivos_en_disco()), 1)

    def test_reemplazo_confirmado_borra_el_archivo_anterior_del_disco(self):
        self._subir(nombre="primero.csv")
        antes = _archivos_en_disco()
        csv2 = CSV_VALIDO.replace(",60,60", ",70,70")
        resp = self._subir(csv2, nombre="segundo.csv", confirmar_sobrescritura="1")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(ArchivoMolecular.objects.count(), 1)
        self.assertEqual(ResultadoTaxonomico.objects.get(genus="Bacillus").num_hits, 70)
        despues = _archivos_en_disco()
        self.assertEqual(len(despues), 1)
        self.assertNotEqual(antes, despues)
        self.assertIn("segundo", despues[0])

    # Fallos parciales

    def test_fallo_al_insertar_resultados_no_deja_archivo_ni_registros(self):
        self._subir(nombre="original.csv")
        original = _archivos_en_disco()
        with mock.patch("analisis.services.business.upload_service.ResultadoTaxonomico.objects.bulk_create",
                        side_effect=RuntimeError("fallo simulado")), \
                self.assertLogs("analisis.views.subir_datos", level="ERROR"):
            resp = self._subir(nombre="nuevo.csv", confirmar_sobrescritura="1")
        self.assertEqual(resp.status_code, 400)
        # Se conserva la carga anterior completa, en la base y en el disco
        self.assertEqual(ArchivoMolecular.objects.count(), 1)
        self.assertEqual(ResultadoTaxonomico.objects.count(), 3)
        self.assertEqual(_archivos_en_disco(), original)

    # Nombres y columnas con HTML

    def test_columnas_con_html_se_devuelven_como_datos(self):
        csv = '<img src=x onerror=alert(1)>,num_hits\nBacillus,10\n'
        resp = self._subir(csv, nombre='<script>x</script>.csv')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp["Content-Type"], "application/json")
        self.assertIn("<img src=x onerror=alert(1)>", resp.json()["recibidas"])

    def test_nombre_de_archivo_con_html_se_guarda_saneado(self):
        resp = self._subir(nombre='<b>raro</b>"datos".csv')
        self.assertEqual(resp.status_code, 200, resp.content)
        for nombre in _archivos_en_disco():
            self.assertNotIn("<", nombre)
            self.assertNotIn('"', nombre)


class PipelineEquivalenciaTests(PruebaConMedia):
    """La versión vectorizada produce exactamente los mismos registros que la de iterrows()."""

    @staticmethod
    def _version_anterior(df):
        df = df.copy()
        df.columns = df.columns.str.strip().str.lower()
        PipelineProcesamiento.validar_columnas(df)
        df = PipelineProcesamiento.limpiar_datos(df)
        df = df[df["num_hits"] > 0].reset_index(drop=True)
        return [{
            "kingdom": str(r["kingdom"]), "phylum": str(r["phylum"]), "tax_class": str(r["class"]),
            "order": str(r["order"]), "family": str(r["family"]), "genus": str(r["genus"]),
            "species": str(r["species"]), "num_hits": int(r["num_hits"]),
            "%_hits": round(float(r["%_hits"]), 5),
        } for _, r in df.iterrows()]

    def test_equivalencia_con_datos_sucios(self):
        df = pd.DataFrame({
            "Kingdom ": ["Bacteria", None, "Fungi", "Bacteria"],
            "phylum": ["Firmicutes", "nan", "Ascomycota", " Proteobacteria "],
            "class": ["Bacilli", "", None, "Gamma"],
            "order": ["Bacillales", "unknown", "Hypocreales", "Pseudomonadales"],
            "family": ["Bacillaceae", "Unclassified ", "Nectriaceae", "Pseudomonadaceae"],
            "genus": ["Bacillus", None, "Fusarium", "Pseudomonas"],
            "species": ["Bacillus_subtilis(AJ1)", "sp.", None, "putida"],
            "num_hits": ["10", 0, 3.0, "x"],
            "%_hits": ["12,5", 0, 0.123456789, None],
        })
        nuevo = PipelineProcesamiento.procesar_archivo_df(df)
        self.assertEqual(nuevo["data"], self._version_anterior(df))
        self.assertEqual(nuevo["total_registros"], len(nuevo["data"]))
        for fila in nuevo["data"]:
            self.assertIs(type(fila["num_hits"]), int)
            self.assertIs(type(fila["%_hits"]), float)
