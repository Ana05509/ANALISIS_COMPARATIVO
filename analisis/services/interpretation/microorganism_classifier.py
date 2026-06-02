# Orquestador del Motor de Clasificación Funcional, Reglas de Precedencia Agronómica y Persistencia.

from typing import List, Dict, Any, Set
from django.db import transaction
from analisis.models import CatalogoMicroorganismo
# Importaciones relativas explícitas (Pylance las resuelve de inmediato usando el árbol local)
from .beneficial_service import BeneficialMicroorganismsService
from .pathogen_service import PathogenService

CLASIFICACIONES_VALIDAS = ("benefico", "fitopatogeno", "neutral", "sin_clasificar")


class MicroorganismClassificationService:
    """Servicio encargado de la unificación de criterios funcionales y la indexación masiva del catálogo microbiano."""

    @staticmethod
    def clasificar_microorganismo(nombre: Any, tipo: str = "16S") -> str:
        """
        Aplica las reglas de precedencia científica para etiquetar un taxón individual.
        Un fitopatógeno tiene prioridad absoluta de asignación debido al riesgo fitosanitario.
        """
        if not nombre or not isinstance(nombre, str):
            return "sin_clasificar"

        tipo_analisis = tipo.upper() if tipo else "16S"

        # REGLA DE PRECEDENCIA: Evaluar primero riesgo crítico de enfermedad
        if PathogenService.es_fitopatogeno(nombre, tipo_analisis):
            return "fitopatogeno"
            
        if BeneficialMicroorganismsService.es_benefico(nombre, tipo_analisis):
            return "benefico"
            
        return "sin_clasificar"

    @staticmethod
    def clasificar_y_persistir(nombres: List[str], nivel: str = "genus", tipo: str = "16S") -> Dict[str, int]:
        """
        Indexa y actualiza masivamente el catálogo eliminando el antipadrón N+1.
        Busca registros existentes en una única consulta y procesa las inserciones en un bloque atómico.
        """
        conteo = {"benefico": 0, "fitopatogeno": 0, "sin_clasificar": 0}
        if not nombres:
            return {**conteo, "total_procesados": 0}

        tipo_analisis = tipo.upper() if tipo else "16S"
        nivel_evaluado = nivel if nivel else "genus"

        # 1. Sanitizar la lista en memoria y remover duplicados redundantes del lote
        nombres_unicos: Set[str] = {str(n).strip() for n in nombres if n}

        # 2. RESOLUCIÓN N+1: Consultar qué microorganismos ya existen en la base de datos de un solo golpe
        registrados_qs = CatalogoMicroorganismo.objects.filter(
            nombre__in=nombres_unicos,
            nivel=nivel_evaluado
        ).values_list("nombre", flat=True)
        
        nombres_existentes: Set[str] = set(registrados_qs)

        nuevos_registros: List[CatalogoMicroorganismo] = []

        # 3. Procesar en memoria la clasificación sin tocar la base de datos en el bucle
        for nombre in nombres_unicos:
            clasificacion_final = MicroorganismClassificationService.clasificar_microorganismo(nombre, tipo_analisis)
            
            # Incrementar métricas del contador de lote
            if clasificacion_final in conteo:
                conteo[clasificacion_final] += 1

            # Si no existe, se encola para creación masiva
            if nombre not in nombres_existentes:
                nuevos_registros.append(
                    CatalogoMicroorganismo(
                        nombre=nombre,
                        nivel=nivel_evaluado,
                        clasificacion=clasificacion_final
                    )
                )

        # 4. Persistencia Atómica en Lote (Bulk Create)
        if nuevos_registros:
            with transaction.atomic():
                CatalogoMicroorganismo.objects.bulk_create(nuevos_registros, batch_size=500)

        return {**conteo, "total_procesados": len(nombres_unicos)}

    @staticmethod
    def reclasificar_microorganismo(
        pk: int, 
        nueva_clasificacion: str, 
        usuario: Any = None, 
        justificacion: str = ""
    ) -> Dict[str, Any]:
        """
        Permite a un analista o especialista forzar un cambio de clasificación basado en literatura local.
        Actualiza el registro utilizando escrituras optimizadas por campo de Django.
        """
        if nueva_clasificacion not in CLASIFICACIONES_VALIDAS:
            return {"ok": False, "error": f"La clasificación '{nueva_clasificacion}' no pertenece a los rangos permitidos."}

        try:
            catalogo = CatalogoMicroorganismo.objects.get(pk=pk)
        except CatalogoMicroorganismo.DoesNotExist:
            return {"ok": False, "error": f"No se encontró ningún microorganismo registrado con el ID primario {pk}."}

        clasificacion_anterior = catalogo.clasificacion
        catalogo.clasificacion = nueva_clasificacion
        catalogo.save(update_fields=["clasificacion"])

        return {
            "ok": True,
            "pk": pk,
            "nombre": catalogo.nombre,
            "clasificacion_anterior": clasificacion_anterior,
            "clasificacion_nueva": nueva_clasificacion,
            "usuario": str(usuario) if usuario else "Sistema",
            "justificacion": justificacion,
        }