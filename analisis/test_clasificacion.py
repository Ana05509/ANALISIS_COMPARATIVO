"""La ficha de muestra y la API clasifican igual que el resto del sistema (catálogo a nivel género)."""
from django.urls import reverse

from analisis.constants import clasificar_taxon
from analisis.models import CatalogoMicroorganismo
from analisis.services.business.analysis_service import obtener_lookup_catalogo
from analisis.utilidades_pruebas import PruebaConMedia, crear_muestra, crear_usuario


class ClasificacionUnificadaTests(PruebaConMedia):

    def setUp(self):
        super().setUp()
        self.client.force_login(crear_usuario("docente", "docente"))
        self.muestra = crear_muestra("M-CLAS", self.cultivo, self.variedad)
        # Mismo nombre en otro nivel con otra clasificación (lo permite unique nombre+nivel)
        CatalogoMicroorganismo.objects.create(nombre="Bacillus", nivel="species", marcador="16S",
                                              clasificacion="fitopatogeno")

    def _canonica(self, genero):
        return clasificar_taxon(genero, obtener_lookup_catalogo("16S", nivel="genus"), "genus")

    def test_ficha_de_muestra_usa_la_entrada_de_genero(self):
        resp = self.client.get(reverse("analisis:ver_producto", args=[self.muestra.pk]))
        clas = {r.genus: r.clasificacion for r in resp.context["analisis"]}
        self.assertEqual(clas["Bacillus"], "benefico")
        for genero, valor in clas.items():
            self.assertEqual(valor, self._canonica(genero))

    def test_api_usa_la_entrada_de_genero(self):
        resp = self.client.get(reverse("analisis:api_muestra_detalle", args=[self.muestra.pk]))
        self.assertEqual(resp.status_code, 200)
        clas = {t["taxonomia"]: t["clasificacion"] for t in resp.json()["data"]["taxonomia"]}
        self.assertEqual(clas["Bacillus"], "benefico")
        self.assertEqual(clas["Pseudomonas"], "fitopatogeno")
        self.assertEqual(clas["Streptomyces"], "sin_clasificar")


class ApiCompatibilidadTests(PruebaConMedia):
    """Forma de las respuestas y parámetros inválidos de la API v1 (sin cambios de contrato)."""

    def setUp(self):
        super().setUp()
        self.client.force_login(crear_usuario("docente", "docente"))
        self.muestra = crear_muestra("M-API", self.cultivo, self.variedad)

    def test_requiere_sesion(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("analisis:api_muestras")).status_code, 302)

    def test_muestras_y_filtros(self):
        datos = self.client.get(reverse("analisis:api_muestras")).json()
        self.assertTrue(datos["ok"])
        self.assertEqual([m["codigo"] for m in datos["data"]], ["M-API"])
        self.assertEqual(set(datos["data"][0]), {"id", "codigo", "cultivo", "variedad", "localidad",
                                                 "tipo_muestra", "altitud", "fecha"})
        resp = self.client.get(reverse("analisis:api_muestras"), {"cultivo_id": "abc"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.client.get(reverse("analisis:api_muestras"), {"q": "nada"}).json()["data"], [])

    def test_detalle_con_parametros_invalidos_usa_valores_por_defecto(self):
        resp = self.client.get(reverse("analisis:api_muestra_detalle", args=[self.muestra.pk]),
                               {"tipo": "XYZ", "top_n": "999"})
        datos = resp.json()["data"]
        self.assertEqual((datos["tipo"], datos["top_n"]), ("16S", 10))
        self.assertAlmostEqual(sum(t["porcentaje"] for t in datos["taxonomia"]), 100.0, places=1)

    def test_detalle_inexistente(self):
        resp = self.client.get(reverse("analisis:api_muestra_detalle", args=[999999]))
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.json()["ok"])

    def test_catalogo_paginacion_y_filtros(self):
        datos = self.client.get(reverse("analisis:api_catalogo"), {"page": "x", "clasificacion": "benefico"}).json()
        self.assertEqual(datos["data"]["page"], 1)
        self.assertEqual([r["nombre"] for r in datos["data"]["resultados"]], ["Bacillus"])

    def test_estadisticas(self):
        datos = self.client.get(reverse("analisis:api_estadisticas")).json()["data"]
        self.assertEqual(datos["muestras"], 1)
        self.assertEqual(datos["catalogo"]["beneficos"], 1)
