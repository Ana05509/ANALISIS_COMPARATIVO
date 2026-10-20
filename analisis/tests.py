import importlib.util
import io
import itertools
import unittest
import warnings

import numpy as np
import pandas as pd
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from scipy.spatial.distance import braycurtis, pdist, squareform

from analisis.services.business.upload_service import leer_archivo
from analisis.services.business.visualization_service import VisualizationService
from analisis.services.processing.diversity import DiversityService
from analisis.views.comparison import _aviso_profundidad

SKBIO_DISPONIBLE = importlib.util.find_spec("skbio") is not None


def _bray_curtis_bucles(matriz):
    """Implementación anterior (bucles for) usada como referencia."""
    n = matriz.shape[0]
    dist = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = braycurtis(matriz[i], matriz[j])
            dist[i, j] = d
            dist[j, i] = d
    return dist


def _abundancias_aleatorias(n_muestras=6, n_taxa=20, semilla=42):
    rng = np.random.default_rng(semilla)
    matriz = rng.integers(0, 100, size=(n_muestras, n_taxa)).astype(float)
    return matriz / matriz.sum(axis=1, keepdims=True)


def _abundancias_dispersas(n_muestras=10, n_taxa=15, semilla=4):
    """Perfiles con ~70 % de ceros, como en datos reales: su Bray-Curtis da valores propios negativos."""
    rng = np.random.default_rng(semilla)
    matriz = rng.integers(0, 100, size=(n_muestras, n_taxa)).astype(float)
    matriz[matriz < 70] = 0
    return matriz / matriz.sum(axis=1, keepdims=True)


class PCoATests(SimpleTestCase):

    def test_puntos_en_el_plano_reproducen_distancias(self):
        puntos = np.array([[0.0, 0.0], [3.0, 0.0], [0.0, 4.0], [3.0, 4.0], [1.0, 1.5]])
        D = squareform(pdist(puntos))

        res = DiversityService.calcular_pcoa(D)

        self.assertEqual(res["coords"].shape, (5, 2))
        self.assertTrue(np.allclose(squareform(pdist(res["coords"])), D))
        self.assertAlmostEqual(sum(res["pct_varianza"]), 100.0, places=6)
        self.assertEqual(res["n_negativos"], 0)

    def test_bray_curtis_aleatorio_porcentajes_validos(self):
        D = squareform(pdist(_abundancias_aleatorias(), metric="braycurtis"))

        pct = DiversityService.calcular_pcoa(D)["pct_varianza"]

        self.assertTrue(all(p >= 0 for p in pct))
        self.assertGreaterEqual(pct[0], pct[1])
        self.assertLessEqual(sum(pct), 100.0 + 1e-9)

    def test_matriz_no_cuadrada(self):
        with self.assertRaises(ValueError):
            DiversityService.calcular_pcoa(np.zeros((3, 4)))

    def test_matriz_asimetrica(self):
        D = np.array([[0.0, 0.2, 0.5],
                      [0.3, 0.0, 0.4],
                      [0.5, 0.4, 0.0]])
        with self.assertRaises(ValueError):
            DiversityService.calcular_pcoa(D)

    def test_menos_de_tres_muestras(self):
        with self.assertRaises(ValueError):
            DiversityService.calcular_pcoa(np.array([[0.0, 0.5], [0.5, 0.0]]))

    @unittest.skipUnless(SKBIO_DISPONIBLE, "scikit-bio no está instalado (requirements-dev.txt)")
    def test_coincide_con_scikit_bio(self):
        from skbio import DistanceMatrix
        from skbio.stats.ordination import pcoa

        D = squareform(pdist(_abundancias_aleatorias(), metric="braycurtis"))

        propio = DiversityService.calcular_pcoa(D)["pct_varianza"]
        referencia = pcoa(DistanceMatrix(D)).proportion_explained.values[:2] * 100

        self.assertTrue(np.allclose(propio, referencia, atol=1e-6),
                        f"BioMicro={propio} vs scikit-bio={referencia.tolist()}")

    @unittest.skipUnless(SKBIO_DISPONIBLE, "scikit-bio no está instalado (requirements-dev.txt)")
    def test_coincide_con_scikit_bio_con_valores_propios_negativos(self):
        from skbio import DistanceMatrix
        from skbio.stats.ordination import pcoa

        D = squareform(pdist(_abundancias_dispersas(), metric="braycurtis"))
        res = DiversityService.calcular_pcoa(D)
        self.assertGreater(res["n_negativos"], 0, "el caso de prueba debe tener valores propios negativos")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            referencia = pcoa(DistanceMatrix(D)).proportion_explained.values[:2] * 100

        self.assertTrue(np.allclose(res["pct_varianza"], referencia, atol=1e-6),
                        f"BioMicro={res['pct_varianza']} vs scikit-bio={referencia.tolist()}")


class BrayCurtisVectorizadoTests(SimpleTestCase):

    def test_matriz_bray_curtis_igual_a_version_anterior(self):
        rng = np.random.default_rng(42)
        conteos = rng.integers(0, 500, size=(6, 20)).astype(float)
        conteos[3] = 0  # muestra sin lecturas: control sumas == 0

        # Versión anterior: normalización a proporciones + bucles for
        sumas = conteos.sum(axis=1, keepdims=True)
        sumas[sumas == 0] = 1
        esperado = _bray_curtis_bucles(conteos / sumas)

        self.assertTrue(np.allclose(DiversityService.matriz_bray_curtis(conteos), esperado))


class LecturaArchivoTests(SimpleTestCase):

    def _leer(self, nombre, contenido):
        return leer_archivo(SimpleUploadedFile(nombre, contenido))

    def _verificar(self, df):
        self.assertEqual(list(df.columns), ["genus", "num_hits", "%_hits"])
        self.assertEqual(df["genus"].tolist(), ["Bacillus", "Pseudomonas"])
        self.assertEqual(df["num_hits"].tolist(), [120, 80])

    def test_csv_con_coma(self):
        self._verificar(self._leer(
            "datos.csv", b"genus,num_hits,%_hits\nBacillus,120,60.0\nPseudomonas,80,40.0\n"))

    def test_csv_con_punto_y_coma(self):
        self._verificar(self._leer(
            "datos.csv", b"genus;num_hits;%_hits\nBacillus;120;60.0\nPseudomonas;80;40.0\n"))

    def test_tsv(self):
        self._verificar(self._leer(
            "datos.tsv", b"genus\tnum_hits\t%_hits\nBacillus\t120\t60.0\nPseudomonas\t80\t40.0\n"))

    def test_archivo_ilegible_lanza_value_error(self):
        with self.assertRaisesRegex(ValueError, "No se pudo leer el archivo"):
            self._leer("datos.xlsx", b"esto no es un libro de Excel")


class PermanovaTests(SimpleTestCase):

    @staticmethod
    def _grupos_en_plano(radio_a, radio_b):
        """Dos grupos de 6 puntos (cuadrados concéntricos de radio r y 2r) separados en el plano."""
        cuadrado = np.array([[1, 1], [1, -1], [-1, 1], [-1, -1]], dtype=float)
        base = np.vstack([cuadrado[:3], 2 * cuadrado[:3]])
        puntos = np.vstack([base * radio_a, base * radio_b + [50.0, 0.0]])
        return squareform(pdist(puntos)), ["A"] * 6 + ["B"] * 6

    def test_permdisp_dispersiones_iguales(self):
        D, grupos = self._grupos_en_plano(1.0, 1.0)
        res = DiversityService.calcular_permdisp(D, grupos)
        self.assertGreater(res["p_value"], 0.5)
        self.assertFalse(res["significativo"])

    def test_permdisp_dispersiones_distintas(self):
        D, grupos = self._grupos_en_plano(0.1, 5.0)
        res = DiversityService.calcular_permdisp(D, grupos)
        self.assertLess(res["p_value"], 0.05)
        self.assertTrue(res["significativo"])

    def test_permdisp_p_minimo_es_1_entre_permutaciones_mas_1(self):
        # Diferencia extrema: ninguna permutación iguala F, así que p = (0 + 1) / (9 + 1)
        D, grupos = self._grupos_en_plano(0.1, 5.0)
        res = DiversityService.calcular_permdisp(D, grupos, n_permutaciones=9)
        self.assertEqual(res["p_value"], 0.1)

    @unittest.skipUnless(SKBIO_DISPONIBLE, "scikit-bio no está instalado (requirements-dev.txt)")
    def test_estadisticos_f_coinciden_con_scikit_bio(self):
        from skbio import DistanceMatrix
        from skbio.stats.distance import permanova, permdisp

        D = squareform(pdist(_abundancias_dispersas(n_muestras=12), metric="braycurtis"))
        grupos = list("AAAABBBBCCCC")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            f_permanova = permanova(DistanceMatrix(D), grupos, permutations=0)["test statistic"]
            f_permdisp = permdisp(DistanceMatrix(D), grupos, test="centroid",
                                  permutations=0, dimensions=12)["test statistic"]

        self.assertAlmostEqual(DiversityService.calcular_permanova(D, grupos)["pseudo_f"], f_permanova, places=4)
        self.assertAlmostEqual(DiversityService.calcular_permdisp(D, grupos)["f"], f_permdisp, places=4)

    def test_reparticiones_igual_a_enumeracion(self):
        def fuerza_bruta(tamanos):
            etiquetas = [k for k, t in enumerate(tamanos) for _ in range(t)]
            return len({
                frozenset(frozenset(i for i, e in enumerate(perm) if e == k) for k in range(len(tamanos)))
                for perm in set(itertools.permutations(etiquetas))
            })
        for tamanos in [(3, 3), (2, 2, 2), (4, 2), (3, 3, 2), (2, 2, 1), (4, 4)]:
            self.assertEqual(DiversityService._contar_reparticiones(list(tamanos)), fuerza_bruta(tamanos), tamanos)

    def test_permdisp_excluye_grupos_de_una_muestra(self):
        D, grupos = self._grupos_en_plano(1.0, 1.0)
        # Se agrega una muestra aislada (grupo C): su distancia al centroide sería 0
        puntos_extra = np.vstack([D, np.full((1, D.shape[1]), 30.0)])
        D = np.hstack([puntos_extra, np.append(np.full(D.shape[0], 30.0), 0.0)[:, None]])
        res = DiversityService.calcular_permdisp(D, grupos + ["C"])
        self.assertNotIn("C", res["dispersion_por_grupo"])
        self.assertFalse(res["significativo"])

    def test_potencia_limitada_con_dos_grupos_de_tres(self):
        D = squareform(pdist(_abundancias_aleatorias(), metric="braycurtis"))
        res = DiversityService.calcular_permanova(D, ["A", "A", "A", "B", "B", "B"])
        self.assertTrue(res["potencia_limitada"])
        self.assertEqual(res["n_reparticiones"], 10)  # 6! / (3!·3!) / 2!
        self.assertIn("solo existen 10 reparticiones distintas", res["interpretacion"])

    def test_potencia_suficiente_con_dos_grupos_de_cinco(self):
        D = squareform(pdist(_abundancias_aleatorias(n_muestras=10), metric="braycurtis"))
        res = DiversityService.calcular_permanova(D, ["A"] * 5 + ["B"] * 5)
        self.assertFalse(res["potencia_limitada"])
        self.assertEqual(res["n_reparticiones"], 126)  # 10! / (5!·5!) / 2!


class DiversidadAlfaTests(SimpleTestCase):

    def setUp(self):
        self.df = pd.DataFrame({"%_hits": [50.0, 50.0]})

    def test_shannon(self):
        self.assertAlmostEqual(DiversityService.calcular_shannon(self.df), np.log(2), places=4)

    def test_simpson(self):
        self.assertAlmostEqual(DiversityService.calcular_simpson(self.df), 0.5, places=4)

    def test_pielou(self):
        self.assertAlmostEqual(DiversityService.calcular_equitatividad(self.df), 1.0, places=4)

    def test_proporciones_desiguales(self):
        # Con p = [0.5, 0.5], Simpson D y 1-D valen ambos 0.5; este caso sí los distingue.
        df = pd.DataFrame({"%_hits": [70.0, 20.0, 10.0]})
        p = np.array([0.7, 0.2, 0.1])
        shannon = -np.sum(p * np.log(p))  # 0.8018
        self.assertAlmostEqual(DiversityService.calcular_shannon(df), shannon, places=4)
        self.assertAlmostEqual(DiversityService.calcular_simpson(df), 1 - np.sum(p ** 2), places=4)  # 0.46
        self.assertAlmostEqual(DiversityService.calcular_equitatividad(df), shannon / np.log(3), places=4)


class GraficoPCoATests(SimpleTestCase):

    def _paquete(self, n_muestras):
        matriz = _abundancias_aleatorias(n_muestras=n_muestras)
        columnas = [f"M{i + 1}" for i in range(n_muestras)]
        df = pd.DataFrame(matriz.T * 100, columns=columnas)
        df.insert(0, "genus", [f"Taxon_{k}" for k in range(matriz.shape[1])])
        return VisualizationService.obtener_paquete_graficos_avanzados(df, columnas, "genus")

    def test_grafico_usa_pcoa(self):
        paquete = self._paquete(6)

        self.assertNotIn("error_pca", paquete)
        layout = paquete["grafico_pca"]["layout"]
        self.assertEqual(layout["title"]["text"], "PCoA — Disimilitud Bray-Curtis")
        self.assertRegex(layout["xaxis"]["title"]["text"], r"^PCo1 \(\d+,\d % de variación explicada\)$")
        self.assertRegex(layout["yaxis"]["title"]["text"], r"^PCo2 \(\d+,\d %\)$")
        self.assertIn("Variación explicada por PCo1 + PCo2", layout["annotations"][0]["text"])

    def test_minimo_tres_muestras(self):
        paquete = self._paquete(2)
        self.assertNotIn("grafico_pca", paquete)
        self.assertEqual(paquete["error_pca"], "Se requieren al menos 3 muestras para PCoA (Bray-Curtis).")


class AvisoProfundidadTests(SimpleTestCase):

    def test_sin_aviso_hasta_el_doble(self):
        self.assertEqual(_aviso_profundidad([100, 200]), "")

    def test_aviso_por_encima_del_doble(self):
        aviso = _aviso_profundidad([3071, 12401, 60090])
        self.assertIn("(3.071–60.090 lecturas)", aviso)
        self.assertIn("Schloss, 2024", aviso)
        self.assertNotEqual(_aviso_profundidad([100, 201]), "")

    def test_ignora_muestras_sin_lecturas(self):
        self.assertEqual(_aviso_profundidad([0, 100, 150]), "")


class ExportacionCatalogoTests(SimpleTestCase):

    FILAS = [
        {"nombre": "Bacillus", "nivel": "genus", "marcador": "16S", "clasificacion": "benefico",
         "descripcion": "Promotor del crecimiento", "referencia": ""},
        {"nombre": "Ralstonia", "nivel": "genus", "marcador": "16S", "clasificacion": "fitopatogeno",
         "descripcion": "=HYPERLINK(\"http://x\")", "referencia": "- Smith 2020"},
    ]

    def test_csv_reimportable_y_sin_formulas(self):
        from analisis.services.business.catalog_service import CatalogService
        contenido = CatalogService.exportar_csv(self.FILAS)

        self.assertTrue(contenido.startswith(b"\xef\xbb\xbf"))  # BOM: Excel muestra bien las tildes
        df = pd.read_csv(io.BytesIO(contenido), encoding="utf-8-sig", keep_default_na=False)
        self.assertEqual(list(df.columns), CatalogService.COLUMNAS_EXPORTACION)
        self.assertEqual(df.loc[1, "descripcion"], "'=HYPERLINK(\"http://x\")")
        # Al reimportar se quita el escape: ida y vuelta sin pérdida
        self.assertEqual(CatalogService._quitar_escape_formula(df.loc[1, "descripcion"]),
                         "=HYPERLINK(\"http://x\")")
        self.assertEqual(CatalogService._quitar_escape_formula(df.loc[1, "referencia"]), "- Smith 2020")

    def test_quitar_escape_no_toca_apostrofes_normales(self):
        from analisis.services.business.catalog_service import CatalogService
        self.assertEqual(CatalogService._quitar_escape_formula("'Candidatus' Solibacter"),
                         "'Candidatus' Solibacter")
        self.assertEqual(CatalogService._quitar_escape_formula("Bacillus"), "Bacillus")

    def test_excel_hojas_y_contenido(self):
        from analisis.services.business.catalog_service import CatalogService
        contenido = CatalogService.exportar_excel(self.FILAS)
        hojas = pd.read_excel(io.BytesIO(contenido), sheet_name=None, keep_default_na=False)

        # Sin filas ITS no se crea su hoja; la primera hoja (la que lee la importación) tiene todo
        self.assertEqual(list(hojas), ["Catálogo", "Bacterias (16S)"])
        self.assertEqual(list(hojas["Catálogo"].columns), CatalogService.COLUMNAS_EXPORTACION)
        self.assertEqual(hojas["Catálogo"]["nombre"].tolist(), ["Bacillus", "Ralstonia"])
