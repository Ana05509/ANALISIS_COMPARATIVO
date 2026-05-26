from analisis.models import ResultadoTaxonomico, CatalogoMicroorganismo

FITOPATOGENOS_16S = {
    "xanthomonas","ralstonia","erwinia","pectobacterium","dickeya",
    "clavibacter","acidovorax","agrobacterium",
}

FITOPATOGENOS_ITS = {
    "moniliophthora","phytophthora","ceratocystis","crinipellis","marasmius",
    "fusarium","rhizoctonia","sclerotinia","botrytis","alternaria",
    "colletotrichum","verticillium","pythium","puccinia","ustilago",
    "hemileia","mycena","armillaria",
}


def es_fitopatogeno(nombre: str, tipo: str = "16S") -> bool:
    nombre_lower = nombre.strip().lower()
    genero = nombre_lower.split()[0]
    pool = FITOPATOGENOS_ITS if tipo == "ITS" else FITOPATOGENOS_16S
    return genero in pool or nombre_lower in pool


def obtener_fitopatogenos_en_muestra(muestra_id: int, tipo: str = "16S") -> list:
    """README: Clasificación Funcional Fitopatógenos ⚠️"""
    qs = ResultadoTaxonomico.objects.filter(
        archivo__muestra_id=muestra_id,
        archivo__tipo_analisis=tipo,
    ).values("genus", "porcentaje_hits", "num_hits")
    return [item for item in qs if es_fitopatogeno(item["genus"], tipo)]


def marcar_fitopatogenos_en_catalogo(nombres: list, nivel: str = "genus", tipo: str = "16S") -> int:
    """Actualiza clasificacion en CatalogoMicroorganismo."""
    actualizados = 0
    for nombre in nombres:
        if es_fitopatogeno(nombre, tipo):
            CatalogoMicroorganismo.objects.filter(
                nombre__iexact=nombre, nivel=nivel
            ).update(clasificacion="fitopatogeno")
            actualizados += 1
    return actualizados