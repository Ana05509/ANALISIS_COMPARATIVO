from django.db.models import Q
from analisis.models import ResultadoTaxonomico, CatalogoMicroorganismo

class CatalogService:
    @staticmethod
    def _limpiar(val):
        return str(val).strip().lower() if val else ""

    @staticmethod
    def obtener_catalogo_procesado(marcador="", clasificacion="", nivel="", busqueda=""):
        # 1. Carga maestra para evitar N+1
        reglas = CatalogoMicroorganismo.objects.all()
        # Mapa: {(nivel, nombre): clasificacion}
        dicc_maestro = {(r.nivel.lower(), r.nombre.lower()): r.clasificacion for r in reglas}

        # 2. Query de muestras de usuario
        qs = ResultadoTaxonomico.objects.select_related('archivo__muestra')
        if busqueda: qs = qs.filter(Q(genus__icontains=busqueda) | Q(species__icontains=busqueda))
        if marcador: qs = qs.filter(archivo__tipo_analisis__iexact=marcador)

        resultados = []
        stats = {"total": 0, "benefico": 0, "fitopatogeno": 0, "neutral": 0, "sin_clasificar": 0}

        for r in qs:
            nombre = CatalogService._limpiar(r.species) or CatalogService._limpiar(r.genus)
            nivel_tax = "species" if r.species else "genus"
            tipo = dicc_maestro.get((nivel_tax, nombre), "sin_clasificar")

            if (clasificacion and clasificacion != tipo) or (nivel and nivel != nivel_tax):
                continue

            stats["total"] += 1
            stats[tipo] = stats.get(tipo, 0) + 1
            
            resultados.append({
                "id": r.id,
                "taxonomia": nombre,
                "nivel": nivel_tax,
                "producto": {"tipo": r.archivo.tipo_analisis},
                "porcentaje_hits": r.porcentaje_hits,
                "clasificacion": tipo
            })
        
        # Adaptación de nombres para el HTML
        estadisticas = {
            "total": stats["total"],
            "total_beneficos": stats["benefico"],
            "total_fitopatogenos": stats["fitopatogeno"],
            "total_neutrales": stats["neutral"],
            "total_sin_clas": stats["sin_clasificar"]
        }
        return resultados, estadisticas

    @staticmethod
    def reclasificar_microorganismo(pk, nueva_clasificacion, descripcion):
        try:
            res = ResultadoTaxonomico.objects.get(pk=pk)
            nombre = res.species or res.genus
            nivel = "species" if res.species else "genus"
            CatalogoMicroorganismo.objects.update_or_create(
                nombre__iexact=nombre, nivel__iexact=nivel,
                defaults={"nombre": nombre, "nivel": nivel, "clasificacion": nueva_clasificacion, "descripcion": descripcion}
            )
            return True
        except: return False