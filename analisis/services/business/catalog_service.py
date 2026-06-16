from django.db.models import Q, QuerySet
from analisis.models import ResultadoTaxonomico, CatalogoMicroorganismo

TAXONOMIC_STOPWORDS = {
    'unclassified', 'unknown', 'uncultured', 'unidentified', 'sp', 'nan', 'bacterium',
    'unidentified bacterium', 'unidentified eubacterium', 'uncultured soil'
}

class CatalogService:
    
    @staticmethod
    def _limpiar(val):
        return str(val).strip().lower() if val is not None else ""

    @classmethod
    def obtener_catalogo_procesado(cls, queryset_resultados: QuerySet, clasificacion="", nivel=""):
        """
        Procesa el matching jerárquico recibiendo el QuerySet pre-filtrado de la vista.
        Resuelve definitivamente el error de tipos en Pylance.
        """
        # 1. Carga maestra para evitar N+1
        reglas = CatalogoMicroorganismo.objects.all()
        # Mapa: {(nivel, nombre): clasificacion}
        dicc_maestro = {(r.nivel.lower(), r.nombre.lower()): r.clasificacion for r in reglas}

        resultados = []
        stats = {"total": 0, "benefico": 0, "fitopatogeno": 0, "neutral": 0, "sin_clasificar": 0}

        # Procesamos el QuerySet que llega desde la vista
        for r in queryset_resultados:
            genus_limpio = cls._limpiar(r.genus)
            species_limpio = cls._limpiar(r.species)

            nombre = genus_limpio
            nivel_tax = "genus"
            tipo = None

            # Matching jerárquico adaptativo
            if species_limpio and species_limpio not in TAXONOMIC_STOPWORDS:
                if species_limpio.startswith(genus_limpio):
                    binomio = species_limpio
                else:
                    binomio = f"{genus_limpio} {species_limpio}"

                # 1. Intentar matching de especie
                tipo = dicc_maestro.get(("species", binomio))
                if tipo:
                    nivel_tax = "species"
                    nombre = binomio
                else:
                    # 2. Fallback a género
                    tipo = dicc_maestro.get(("genus", genus_limpio))
                    nivel_tax = "genus"
                    nombre = genus_limpio
            else:
                # Fallback directo a género
                tipo = dicc_maestro.get(("genus", genus_limpio))
                nivel_tax = "genus"
                nombre = genus_limpio

            # Si no hubo match en el catálogo maestro, asegurar "sin_clasificar"
            if not tipo:
                tipo = "sin_clasificar"

            # Aplicar filtros dinámicos en memoria (requerido porque 'tipo' no existe en la BD)
            if (clasificacion and clasificacion != tipo) or (nivel and nivel != nivel_tax):
                continue

            # Incremento de estadísticas tras clasificación final
            stats["total"] += 1
            stats[tipo] = stats.get(tipo, 0) + 1

            resultados.append({
                "id": r.id,
                "taxonomia": nombre,
                "nivel": nivel_tax,
                "producto": {
                    "tipo": r.archivo.tipo_analisis if hasattr(r.archivo, 'tipo_analisis') else "",
                    "nombre": r.archivo.muestra.codigo if hasattr(r.archivo, 'muestra') and hasattr(r.archivo.muestra, 'codigo') else "Muestra S/N"
                },
                "porcentaje_hits": r.porcentaje_hits,
                "clasificacion": tipo
            })

        # Adaptación de nombres de contadores para tu plantilla HTML
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
            genus_limpio = CatalogService._limpiar(res.genus)
            species_limpio = CatalogService._limpiar(res.species)

            if species_limpio and species_limpio not in TAXONOMIC_STOPWORDS:
                nombre = f"{genus_limpio} {species_limpio}".strip()
                nivel = "species"
            else:
                nombre = genus_limpio
                nivel = "genus"

            CatalogoMicroorganismo.objects.update_or_create(
                nombre__iexact=nombre, 
                nivel__iexact=nivel,
                defaults={
                    "nombre": nombre, 
                    "nivel": nivel, 
                    "clasificacion": nueva_clasificacion, 
                    "descripcion": descripcion
                }
            )
            return True
        except: 
            return False