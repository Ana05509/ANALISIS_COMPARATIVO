from analisis.models import CatalogoMicroorganismo
from .beneficial_service import es_benefico
from .pathogen_service import es_fitopatogeno

CLASIFICACIONES_VALIDAS = ("benefico", "fitopatogeno", "neutral", "sin_clasificar")


def clasificar_microorganismo(nombre: str, tipo: str = "16S") -> str:
    """
    Clasifica un microorganismo individual.
    Fitopatógeno tiene precedencia. README: "Clasificación Funcional ✅ ⚠️ ⚪"
    """
    if es_fitopatogeno(nombre, tipo):
        return "fitopatogeno"
    if es_benefico(nombre, tipo):
        return "benefico"
    return "sin_clasificar"


def clasificar_y_persistir(nombres: list, nivel: str = "genus", tipo: str = "16S") -> dict:
    """
    Crea o actualiza registros en CatalogoMicroorganismo para los nombres dados.
    README: "Nota Científica: basado en bases de datos referenciales 16S e ITS"
    """
    conteo = {"benefico": 0, "fitopatogeno": 0, "sin_clasificar": 0}

    for nombre in nombres:
        clas = clasificar_microorganismo(nombre, tipo)
        CatalogoMicroorganismo.objects.get_or_create(
            nombre=nombre,
            nivel=nivel,
            defaults={"clasificacion": clas}
        )
        conteo[clas] = conteo.get(clas, 0) + 1

    return {**conteo, "total_procesados": len(nombres)}


def reclasificar_microorganismo(pk: int, nueva_clasificacion: str,
                                 usuario=None, justificacion: str = "") -> dict:
    """
    Permite al Analista Especialista actualizar la clasificación de un
    microorganismo en CatalogoMicroorganismo.
    README: "Rol Analista Especialista: edita clasificación según literatura"
    """
    if nueva_clasificacion not in CLASIFICACIONES_VALIDAS:
        return {"ok": False, "error": f"Clasificación inválida: '{nueva_clasificacion}'."}

    try:
        catalogo = CatalogoMicroorganismo.objects.get(pk=pk)
    except CatalogoMicroorganismo.DoesNotExist:
        return {"ok": False, "error": f"Microorganismo con pk={pk} no encontrado."}

    anterior = catalogo.clasificacion
    catalogo.clasificacion = nueva_clasificacion
    catalogo.save(update_fields=["clasificacion"])

    return {
        "ok":                    True,
        "pk":                    pk,
        "nombre":                catalogo.nombre,
        "clasificacion_anterior": anterior,
        "clasificacion_nueva":   nueva_clasificacion,
        "usuario":               str(usuario) if usuario else "Sistema",
        "justificacion":         justificacion,
    }