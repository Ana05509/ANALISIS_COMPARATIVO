"""Ayudas compartidas por las pruebas con base de datos (no contiene pruebas)."""
import shutil
import tempfile

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings

from analisis import seguridad
from analisis.models import (
    ArchivoMolecular, CatalogoMicroorganismo, Cultivo, MuestraSuelo,
    ResultadoTaxonomico, Usuario, VariedadClon,
)

CSV_VALIDO = (
    "kingdom,phylum,class,order,family,genus,species,num_hits,%_hits\n"
    "Bacteria,Firmicutes,Bacilli,Bacillales,Bacillaceae,Bacillus,subtilis,60,60\n"
    "Bacteria,Proteobacteria,Gammaproteobacteria,Pseudomonadales,Pseudomonadaceae,Pseudomonas,putida,30,30\n"
    "Bacteria,Actinobacteria,Actinomycetia,Streptomycetales,Streptomycetaceae,Streptomyces,griseus,10,10\n"
)


def crear_usuario(username, rol, **extra):
    """Usuario con los Términos ya aceptados (si no, TerminosMiddleware redirige)."""
    usuario = Usuario.objects.create_user(
        username=username, email=f"{username}@utc.edu.ec", password="ClaveSegura.2026", rol=rol, **extra
    )
    LogEntry.objects.create(
        user_id=usuario.pk,
        content_type_id=ContentType.objects.get_for_model(Usuario).pk,
        object_id=str(usuario.pk),
        object_repr=seguridad._marca_aceptacion(),
        action_flag=ADDITION,
        change_message="aceptación (prueba)",
    )
    return usuario


def crear_muestra(codigo, cultivo, variedad, tipo="16S", taxa=None):
    """Muestra con un archivo molecular y sus resultados. taxa: [(genus, species, hits), ...]."""
    muestra = MuestraSuelo.objects.create(
        codigo=codigo, cultivo=cultivo, variedad_clon=variedad,
        localidad="Cotopaxi", finca_lote="Lote 1", altitud=2800,
    )
    archivo = ArchivoMolecular.objects.create(muestra=muestra, tipo_analisis=tipo, archivo=f"pruebas/{codigo}.csv")
    taxa = taxa or [("Bacillus", "subtilis", 60), ("Pseudomonas", "putida", 30), ("Streptomyces", "griseus", 10)]
    total = sum(h for _, _, h in taxa) or 1
    ResultadoTaxonomico.objects.bulk_create([
        ResultadoTaxonomico(
            archivo=archivo, kingdom="Bacteria", phylum="Phylum", tax_class="Clase", order="Orden",
            family=f"{g}aceae", genus=g, species=s, num_hits=h, porcentaje_hits=h / total * 100,
        )
        for g, s, h in taxa
    ])
    return muestra


class PruebaConMedia(TestCase):
    """TestCase con MEDIA_ROOT temporal: las cargas no tocan la carpeta media/ real."""

    @classmethod
    def setUpClass(cls):
        cls._media_tmp = tempfile.mkdtemp(prefix="biomicro_media_")
        cls._override_media = override_settings(MEDIA_ROOT=cls._media_tmp)
        cls._override_media.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override_media.disable()
        shutil.rmtree(cls._media_tmp, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.cultivo = Cultivo.objects.create(nombre="Cacao")
        cls.variedad = VariedadClon.objects.create(cultivo=cls.cultivo, nombre="CCN-51")
        CatalogoMicroorganismo.objects.bulk_create([
            CatalogoMicroorganismo(nombre="Bacillus", nivel="genus", marcador="16S", clasificacion="benefico"),
            CatalogoMicroorganismo(nombre="Pseudomonas", nivel="genus", marcador="16S", clasificacion="fitopatogeno"),
        ])
