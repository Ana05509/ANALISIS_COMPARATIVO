from analisis.models import ResultadoTaxonomico, CatalogoMicroorganismo

BENEFICOS_16S = {
    "rhizobium","bradyrhizobium","mesorhizobium","sinorhizobium","azotobacter",
    "azospirillum","frankia","azorhizobium","bacillus","pseudomonas","burkholderia",
    "enterobacter","serratia","gluconacetobacter","arthrobacter","streptomyces",
    "paenibacillus","microbacterium","lysobacter","stenotrophomonas",
}

BENEFICOS_ITS = {
    "glomus","rhizophagus","gigaspora","scutellospora","acaulospora",
    "diversispora","claroideoglomus","trichoderma","beauveria","metarhizium",
    "clonostachys","aspergillus","penicillium","mortierella","mucor",
}


def es_benefico(nombre: str, tipo: str = "16S") -> bool:
    genero = nombre.strip().lower().split()[0]
    return genero in (BENEFICOS_ITS if tipo == "ITS" else BENEFICOS_16S)


def obtener_beneficos_en_muestra(muestra_id: int, tipo: str = "16S") -> list:
    """README: Clasificación Funcional Benéficos ✅"""
    qs = ResultadoTaxonomico.objects.filter(
        archivo__muestra_id=muestra_id,
        archivo__tipo_analisis=tipo,
    ).values("genus", "porcentaje_hits", "num_hits")
    return [item for item in qs if es_benefico(item["genus"], tipo)]


def marcar_beneficos_en_catalogo(nombres: list, nivel: str = "genus", tipo: str = "16S") -> int:
    """Actualiza clasificacion en CatalogoMicroorganismo."""
    actualizados = 0
    for nombre in nombres:
        if es_benefico(nombre, tipo):
            CatalogoMicroorganismo.objects.filter(
                nombre__iexact=nombre, nivel=nivel
            ).update(clasificacion="benefico")
            actualizados += 1
    return actualizados