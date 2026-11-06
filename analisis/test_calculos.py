"""Correcciones de cálculo: lecturas sin asignar, índice de salud por abundancia,
altitud vacía, metadatos de muestras con varios marcadores y notación UFC."""
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.urls import reverse

from analisis.constants import es_taxon_asignado
from analisis.models import MuestraSuelo
from analisis.services.business.analysis_service import (
    obtener_diversidad, obtener_diversidad_beta_inter, obtener_diversidad_gamma,
)
from analisis.services.business.comparison_service import ejecutar_comparacion_clean
from analisis.services.business.upload_service import leer_altitud
from analisis.utilidades_pruebas import CSV_VALIDO, PruebaConMedia, crear_muestra, crear_usuario
from analisis.views.reportes import _construir_datos_reporte, calcular_indice_salud
from bioquimica.models import RecuentoUFC


class TaxonAsignadoTests(SimpleTestCase):

    def test_etiquetas_de_lecturas_sin_asignar(self):
        for nombre in ("Unclassified", "unclassified ", "Unknown", "Others", "nan", "", None):
            self.assertFalse(es_taxon_asignado(nombre), nombre)

    def test_taxones_reales_y_especie_sin_identificar(self):
        # "Bacillus Unclassified" equivale a "Bacillus sp.": es un taxón.
        for nombre in ("Bacillus", "Bacillus Unclassified", "Unclassified Bacillaceae"):
            self.assertTrue(es_taxon_asignado(nombre), nombre)


class DiversidadSinAsignarTests(PruebaConMedia):
    """'Unclassified' no cuenta como taxón en ningún índice; sí en la profundidad."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.a = crear_muestra("A", cls.cultivo, cls.variedad, taxa=[
            ("Bacillus", "subtilis", 50), ("Pseudomonas", "putida", 50), ("Unclassified", "Unclassified", 100),
        ])
        cls.b = crear_muestra("B", cls.cultivo, cls.variedad, taxa=[
            ("Streptomyces", "griseus", 100), ("Unclassified", "Unclassified", 100),
        ])

    def test_alfa_excluye_sin_asignar_pero_la_profundidad_no(self):
        div = obtener_diversidad(tipo="16S", nivel="genus", muestra_ids=[self.a.id])
        self.assertEqual(div["riqueza"], 2)
        self.assertAlmostEqual(div["shannon"], 0.6931, places=4)  # ln 2: dos géneros al 50 %
        self.assertEqual(div["lecturas_totales"][self.a.id], 200)

    def test_beta_no_comparte_unclassified(self):
        beta = obtener_diversidad_beta_inter(tipo="16S", nivel="genus", muestra_ids=[self.a.id, self.b.id])
        self.assertEqual(beta["n_core"], 0)
        self.assertEqual(beta["bc_promedio"], 1.0)
        self.assertEqual(beta["jaccard_promedio"], 0.0)

    def test_gamma_excluye_sin_asignar(self):
        gamma = obtener_diversidad_gamma(tipo="16S", nivel="genus", muestra_ids=[self.a.id, self.b.id])
        self.assertEqual(gamma["riqueza_gamma"], 3)

    def test_compartidos_y_exclusivos_sin_unclassified(self):
        res = ejecutar_comparacion_clean({"tipo": "16S", "nivel": "genus", "top_n": 10,
                                          "productos": [self.a, self.b]})
        self.assertEqual(res["compartidos"], [])
        self.assertNotIn("Unclassified", res["exclusivos"])
        # La tabla de composición sí conserva la fracción sin asignar
        self.assertIn("Unclassified", [f["taxonomia"] for f in res["tabla"]])

    def test_reporte_informa_fraccion_sin_asignar(self):
        datos = _construir_datos_reporte("16S", "genus", 10, muestra_ids=[self.a.id])
        self.assertEqual(datos["abundancia_clas"]["sin_asignar"], 50.0)
        self.assertEqual(sum(datos["totales_clas"].values()), 2)


class IndiceSaludTests(SimpleTestCase):

    def test_pondera_por_abundancia_no_por_numero_de_taxones(self):
        # Muchos patógenos escasos frente a benéficos abundantes: no es "en riesgo".
        indice, nivel = calcular_indice_salud(41.0, 5.4, shannon=2.61)
        self.assertEqual((indice, nivel), (84, "ÓPTIMO"))
        # Patógenos dominantes: crítico aunque haya pocos taxones.
        indice, nivel = calcular_indice_salud(2.0, 44.7, shannon=1.83)
        self.assertEqual((indice, nivel), (19, "CRÍTICO"))

    def test_sin_benéficos_ni_patógenos_es_neutro(self):
        self.assertEqual(calcular_indice_salud(0, 0, shannon=0), (None, "NO ESTIMABLE"))


class AltitudTests(SimpleTestCase):

    def test_vacia_es_none_no_cero(self):
        self.assertIsNone(leer_altitud(""))
        self.assertIsNone(leer_altitud(None))
        self.assertEqual(leer_altitud("0"), 0)
        self.assertEqual(leer_altitud("2800"), 2800)

    def test_fuera_de_rango_o_no_numerica(self):
        for valor in ("-5", "9000", "abc"):
            with self.assertRaises(ValueError):
                leer_altitud(valor)


class MetadatosVariosMarcadoresTests(PruebaConMedia):

    def setUp(self):
        super().setUp()
        self.client.force_login(crear_usuario("docente", "docente"))

    def _subir(self, tipo="16S", **extra):
        datos = {
            "nombre_producto": "M-001", "localidad": "Cotopaxi", "finca_lote": "Lote 1", "altitud": "2800",
            "cultivo": self.cultivo.pk, "variedad_clon": self.variedad.pk, "tipo": tipo,
            "archivo": SimpleUploadedFile("datos.csv", CSV_VALIDO.encode(), content_type="text/csv"),
        }
        datos.update(extra)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("analisis:subir_datos"), datos, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def test_altitud_vacia_se_guarda_como_null(self):
        self.assertEqual(self._subir(altitud="").status_code, 200)
        self.assertIsNone(MuestraSuelo.objects.get().altitud)

    def test_segundo_marcador_con_otros_datos_se_rechaza_sin_cambios(self):
        self._subir()
        resp = self._subir(tipo="ITS", localidad="Pichincha")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Localidad", resp.json()["error"])
        muestra = MuestraSuelo.objects.get()
        self.assertEqual(muestra.localidad, "Cotopaxi")
        self.assertEqual(list(muestra.archivos_moleculares.values_list("tipo_analisis", flat=True)), ["16S"])

    def test_segundo_marcador_con_campos_opcionales_vacios_conserva_los_guardados(self):
        self._subir()
        resp = self._subir(tipo="ITS", altitud="")  # la finca es obligatoria en el formulario
        self.assertEqual(resp.status_code, 200, resp.content)
        muestra = MuestraSuelo.objects.get()
        self.assertEqual(muestra.altitud, 2800)
        self.assertEqual(muestra.archivos_moleculares.count(), 2)

    def test_reemplazo_del_unico_marcador_puede_corregir_metadatos(self):
        self._subir()
        resp = self._subir(localidad="Pichincha", confirmar_sobrescritura="1")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(MuestraSuelo.objects.get().localidad, "Pichincha")


class NotacionUFCTests(SimpleTestCase):

    def test_exponentes_en_superindice(self):
        casos = [
            (Decimal("3"), 6, "3 × 10⁶ UFC/g"),
            (Decimal("2.5"), 12, "2.5 × 10¹² UFC/g"),
            (Decimal("4"), -2, "4 × 10⁻² UFC/g"),
            (Decimal("3"), 0, "3 UFC/g"),
        ]
        for coef, exp, esperado in casos:
            self.assertEqual(RecuentoUFC(coeficiente=coef, exponente=exp).valor_display, esperado)
