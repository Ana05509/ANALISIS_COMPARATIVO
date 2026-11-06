"""Las optimizaciones de consultas dan exactamente los mismos resultados científicos."""
from django.db import connection
from django.db.models import Sum
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from analisis.constants import get_taxonomia_annotation
from analisis.models import ResultadoTaxonomico
from analisis.services.business import analysis_service as A
from analisis.utilidades_pruebas import PruebaConMedia, crear_muestra, crear_usuario

TAXA = [
    [("Bacillus", "subtilis", 60), ("Pseudomonas", "putida", 30), ("Streptomyces", "griseus", 10)],
    [("Bacillus", "cereus", 20), ("Pseudomonas", "putida", 50), ("Rhizobium", "etli", 30)],
    [("Bacillus", "subtilis", 5), ("Nitrospira", "moscoviensis", 80), ("Rhizobium", "etli", 15)],
    [("Streptomyces", "griseus", 40), ("Rhizobium", "etli", 40), ("Bacillus", "", 20)],
]


def _abundancias_anteriores(tipo, nivel, muestra_ids):
    """Implementación anterior (una consulta por muestra), como referencia."""
    expr = get_taxonomia_annotation(nivel)
    salida = {}
    for mid in muestra_ids:
        data = ResultadoTaxonomico.objects.filter(archivo__tipo_analisis=tipo, archivo__muestra_id=mid) \
            .values(t=expr).annotate(h=Sum("num_hits"))
        vec = {r["t"]: r["h"] for r in data if r["t"]}
        if vec:
            salida[mid] = vec
    return salida


class EquivalenciaCientificaTests(PruebaConMedia):

    def setUp(self):
        super().setUp()
        otro = self.cultivo.__class__.objects.create(nombre="Café")
        variedad_cafe = otro.variedades.create(nombre="Típica")
        self.ids = []
        for i, taxa in enumerate(TAXA):
            cultivo, variedad = (self.cultivo, self.variedad) if i % 2 == 0 else (otro, variedad_cafe)
            self.ids.append(crear_muestra(f"M-{i}", cultivo, variedad, taxa=taxa).id)

    def test_matriz_de_abundancias_igual_a_la_anterior(self):
        for nivel in ("genus", "species", "phylum"):
            with self.subTest(nivel=nivel):
                nueva = {mid: {t: h for t, h in filas if t}
                         for mid, filas in A._abundancias_por_muestra("16S", nivel, self.ids).items()}
                nueva = {k: v for k, v in nueva.items() if v}
                anterior = _abundancias_anteriores("16S", nivel, self.ids)
                self.assertEqual(nueva, anterior)
                self.assertEqual(list(nueva), list(anterior))  # mismo orden (afecta a PERMANOVA)

    def test_diversidad_por_muestra_igual_a_una_llamada_por_muestra(self):
        for nivel in ("genus", "species"):
            por_muestra = A.obtener_diversidad_por_muestra("16S", nivel, self.ids)
            for mid in self.ids:
                with self.subTest(nivel=nivel, muestra=mid):
                    self.assertEqual(por_muestra[mid], A.obtener_diversidad("16S", nivel, muestra_ids=[mid]))

    def test_permanova_y_beta_reproducibles(self):
        beta = A.obtener_diversidad_beta_inter("16S", "genus", self.ids)
        self.assertEqual(beta["n_muestras"], 4)
        permanova = A.obtener_permanova("16S", "genus", self.ids)
        self.assertEqual(permanova, A.obtener_permanova("16S", "genus", self.ids))  # semilla fija
        self.assertEqual(permanova["muestras_con_datos"], 4)


class ConsultasNoCrecenPorMuestraTests(PruebaConMedia):

    def setUp(self):
        super().setUp()
        self.client.force_login(crear_usuario("docente", "docente"))

    def _consultas_comparar(self, n):
        ids = [crear_muestra(f"N{n}-{i}", self.cultivo, self.variedad).id for i in range(n)]
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(reverse("analisis:comparar"),
                                   {"marcador": "16S", "nivel": "genus", "top_n": 10, "muestras": ids})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["alfa_por_muestra"])
        return len(ctx.captured_queries)

    def test_comparar_hace_las_mismas_consultas_con_3_o_6_muestras(self):
        self._consultas_comparar(2)  # calentamiento: la primera petición llena cachés internas
        self.assertEqual(self._consultas_comparar(3), self._consultas_comparar(6))


class MuestrasSinDatosDelMarcadorTests(PruebaConMedia):
    """Una muestra sin datos del marcador elegido no debe dejar en cero el core ni los dominantes."""

    def setUp(self):
        super().setUp()
        from analisis.models import MuestraSuelo
        self.client.force_login(crear_usuario("docente", "docente"))
        self.con_datos = [crear_muestra("BAC-1", self.cultivo, self.variedad).id,
                          crear_muestra("BAC-2", self.cultivo, self.variedad, taxa=TAXA[1]).id]
        self.sin_datos = [MuestraSuelo.objects.create(codigo=c, cultivo=self.cultivo, variedad_clon=self.variedad,
                                                      localidad="X", finca_lote="L").id
                          for c in ("HONGO-SIN-ARCHIVO", "OTRA-SIN-ARCHIVO")]

    def test_comparar_excluye_y_avisa(self):
        resp = self.client.get(reverse("analisis:comparar"), {
            "marcador": "16S", "nivel": "genus", "top_n": 10, "muestras": self.con_datos + self.sin_datos})
        self.assertEqual(resp.context["total_muestras"], 2)
        self.assertEqual(sorted(resp.context["compartidos"]), ["Bacillus", "Pseudomonas"])
        self.assertEqual(sorted(resp.context["dominantes"]), ["Bacillus", "Pseudomonas"])
        avisos = " ".join(str(m) for m in resp.context["messages"])
        self.assertIn("HONGO-SIN-ARCHIVO", avisos)

    def test_comparar_con_menos_de_dos_muestras_con_datos(self):
        resp = self.client.get(reverse("analisis:comparar"), {
            "marcador": "16S", "nivel": "genus", "top_n": 10, "muestras": self.con_datos[:1] + self.sin_datos})
        self.assertEqual(resp.context["tabla_comparativa"], [])
        self.assertIn("al menos dos muestras con datos 16S", " ".join(str(m) for m in resp.context["messages"]))

    def test_analisis_avanzado_excluye_y_avisa(self):
        resp = self.client.get(reverse("analisis:analisis_avanzado"), {
            "tipo": "16S", "nivel": "genus", "top_n": 10, "muestra_id": self.con_datos + self.sin_datos})
        self.assertEqual(resp.context["muestra_ids_seleccionados"], self.con_datos)
        self.assertIn("OTRA-SIN-ARCHIVO", " ".join(str(m) for m in resp.context["messages"]))
