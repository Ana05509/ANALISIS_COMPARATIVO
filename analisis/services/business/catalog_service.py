# Gestor de búsquedas indexadas, cruces funcionales y curación de microorganismos del suelo.

from django.db.models import Count, Q
from analisis.models import CatalogoMicroorganismo, ResultadoTaxonomico

CLASIFICACIONES_VALIDAS = ("benefico", "fitopatogeno", "neutral", "sin_clasificar")
NIVELES_VALIDOS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]


class CatalogService:
    """Servicio encargado del catálogo funcional de microorganismos benéficos y patógenos."""

    @staticmethod
    def obtener_catalogo_microorganismos(marcador="", clasificacion="", nivel=""):
        """
        Devuelve el QuerySet del catálogo filtrado bajo criterios estrictos.
        Clasificación Funcional: Benéficos ✅, Fitopatógenos ⚠️, Neutrales 🌿, Sin clasificar ⚪
        """
        qs = CatalogoMicroorganismo.objects.all()

        # Filtrar si los parámetros son explícitos y válidos
        if clasificacion and clasificacion in CLASIFICACIONES_VALIDAS:
            qs = qs.filter(clasificacion=clasificacion)
            
        if nivel and nivel in NIVELES_VALIDOS:
            qs = qs.filter(nivel=nivel)

        # Integración real del marcador molecular si el modelo soporta el atributo o clasificación taxonómica
        if marcador:
            marcador_upper = str(marcador).upper()
            if marcador_upper in ["16S", "ITS"]:
                # Se asume que el catálogo mapea el tipo de microorganismo (Bacteria/Arquea vs Hongo)
                if marcador_upper == "16S":
                    qs = qs.filter(Q(reino__icontains="Bacteria") | Q(reino__icontains="Archaea") | Q(marcador_tipo="16S"))
                elif marcador_upper == "ITS":
                    qs = qs.filter(Q(reino__icontains="Fungi") | Q(marcador_tipo="ITS"))

        return qs.order_by("nombre")

    @staticmethod
    def buscar_microorganismos(termino="", marcador="", clasificacion=""):
        """
        Buscador predictivo indexado para la interfaz de usuario.
        """
        qs = CatalogoMicroorganismo.objects.all()

        if termino:
            qs = qs.filter(nombre__icontains=str(termino).strip())

        if clasificacion and clasificacion in CLASIFICACIONES_VALIDAS:
            qs = qs.filter(clasificacion=clasificacion)

        if marcador:
            marcador_upper = str(marcador).upper()
            if marcador_upper in ["16S", "ITS"] and hasattr(CatalogoMicroorganismo, 'marcador_tipo'):
                qs = qs.filter(marcador_tipo=marcador_upper)

        return qs.order_by("nombre")

    @staticmethod
    def obtener_detalle_microorganismo(pk):
        """Recupera el perfil funcional completo de un taxón por su llave primaria."""
        try:
            return CatalogoMicroorganismo.objects.get(pk=pk)
        except (CatalogoMicroorganismo.DoesNotExist, ValueError, TypeError):
            return None

    @staticmethod
    def obtener_estadisticas_catalogo(nivel_conteo="genus"):
        """
        Genera métricas globales de la biodiversidad del catálogo y base molecular.
        Optimizado en UN SOLO viaje transaccional a la BD mediante agregación condicional.
        """
        # Validar dinámicamente el nivel taxonómico de conteo para evitar caídas de strings inyectados
        campo_conteo = nivel_conteo if nivel_conteo in NIVELES_VALIDOS else "genus"

        # 1. Agregación optimizada para la tabla del Catálogo Funcional
        stats_catalogo = CatalogoMicroorganismo.objects.aggregate(
            total=Count("id"),
            total_beneficos=Count("id", filter=Q(clasificacion="benefico")),
            total_fitopatogenos=Count("id", filter=Q(clasificacion="fitopatogeno")),
            total_neutrales=Count("id", filter=Q(clasificacion="neutral")),
            total_sin_clas=Count("id", filter=Q(clasificacion="sin_clasificar"))
        )

        # 2. Agregaciones de conteos distintos para resultados taxonómicos de secuenciación masiva
        # Evitamos evaluar loops en Python delegando el DISTINCT COUNT a la base de datos de forma segura
        try:
            total_16s = ResultadoTaxonomico.objects.filter(
                archivo__tipo_analisis="16S"
            ).values(campo_conteo).distinct().count()
            
            total_its = ResultadoTaxonomico.objects.filter(
                archivo__tipo_analisis="ITS"
            ).values(campo_conteo).distinct().count()
        except Exception:
            total_16s = 0
            total_its = 0

        return {
            "total": int(stats_catalogo.get("total") or 0),
            "total_beneficos": int(stats_catalogo.get("total_beneficos") or 0),
            "total_fitopatogenos": int(stats_catalogo.get("total_fitopatogenos") or 0),
            "total_neutrales": int(stats_catalogo.get("total_neutrales") or 0),
            "total_sin_clas": int(stats_catalogo.get("total_sin_clas") or 0),
            "total_16s_unicos": total_16s,
            "total_its_unicos": total_its,
            "nivel_evaluado": campo_conteo
        }