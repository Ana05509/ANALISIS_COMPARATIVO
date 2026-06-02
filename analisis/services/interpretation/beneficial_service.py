# services/processing/beneficial_service.py
# Servicio de Clasificación Funcional y Biomarcadores Benéficos para Suelos Agrícolas.

import pandas as pd
from typing import List, Dict, Any
from analisis.models import ResultadoTaxonomico, CatalogoMicroorganismo

# Diccionarios de control de biomarcadores (16S para Bacterias, ITS para Hongos)
BENEFICOS_16S = {
    "rhizobium", "bradyrhizobium", "mesorhizobium", "sinorhizobium", "azotobacter",
    "azospirillum", "frankia", "azorhizobium", "bacillus", "pseudomonas", "burkholderia",
    "enterobacter", "serratia", "gluconacetobacter", "arthrobacter", "streptomyces",
    "paenibacillus", "microbacterium", "lysobacter", "stenotrophomonas",
}

BENEFICOS_ITS = {
    "glomus", "rhizophagus", "gigaspora", "scutellospora", "acaulospora",
    "diversispora", "claroideoglomus", "trichoderma", "beauveria", "metarhizium",
    "clonostachys", "aspergillus", "penicillium", "mortierella", "mucor",
}


class BeneficialMicroorganismsService:
    """Servicio bioinformático para la identificación, catalogación y reporte de microorganismos benéficos."""

    @staticmethod
    def es_benefico(nombre: Any, tipo: str = "16S") -> bool:
        """
        Determina si un taxón es benéfico basándose en su género biológico.
        Soporta nombres compuestos y protege el flujo contra valores nulos o vacíos.
        """
        if not nombre or not isinstance(nombre, str):
            return False

        tokens = nombre.strip().lower().split()
        if not tokens:
            return False

        genero = tokens[0]
        return genero in (BENEFICOS_ITS if tipo.upper() == "ITS" else BENEFICOS_16S)

    @staticmethod
    def obtener_beneficos_en_muestra(muestra_id: int, tipo: str = "16S") -> List[Dict[str, Any]]:
        """
        Extrae los microorganismos benéficos presentes en una muestra específica desde la base de datos.
        Alinea el diccionario resultante con el estándar analítico del pipeline.
        """
        tipo_analisis = tipo.upper() if tipo else "16S"

        # RESOLUCIÓN PYLANCE: Al evaluar con list() o tipar como List[Dict[str, Any]] 
        # forzamos a Pylance a aceptar la conversión del ValuesQuerySet a una lista nativa de Python.
        raw_data = ResultadoTaxonomico.objects.filter(
            archivo__muestra_id=muestra_id,
            archivo__tipo_analisis=tipo_analisis,
        ).values("genus", "porcentaje_hits", "num_hits")

        # Casteo seguro para el análisis estático
        qs: List[Dict[str, Any]] = list(raw_data)

        beneficos = []
        for item in qs:
            nombre_genus = item.get("genus")
            if nombre_genus and BeneficialMicroorganismsService.es_benefico(nombre_genus, tipo_analisis):
                # Estandarizar la clave porcentual para mantener consistencia con los módulos de Pandas
                item["%_hits"] = item.pop("porcentaje_hits")
                beneficos.append(item)

        return beneficos

    @staticmethod
    def marcar_beneficos_en_catalogo(nombres: List[str], nivel: str = "genus", tipo: str = "16S") -> int:
        """
        Optimiza la actualización del catálogo de microorganismos ejecutando una consulta masiva en lote.
        Elimina el antipadrón N+1 y acelera la indexación en base de datos.
        """
        if not nombres:
            return 0

        tipo_analisis = tipo.upper() if tipo else "16S"
        nivel_evaluado = nivel if nivel else "genus"

        nombres_filtrados = [
            nombre for nombre in nombres 
            if BeneficialMicroorganismsService.es_benefico(nombre, tipo_analisis)
        ]

        if not nombres_filtrados:
            return 0

        actualizados = CatalogoMicroorganismo.objects.filter(
            nombre__in=nombres_filtrados,
            nivel=nivel_evaluado
        ).update(clasificacion="benefico")

        return actualizados

    @staticmethod
    def calcular_indice_salud_suelo(df: pd.DataFrame, tipo: str = "16S") -> float:
        """
        Métrica analítica complementaria: Calcula el impacto porcentual total de los benéficos
        sobre la muestra total, insumo clave para el Dashboard Agronómico.
        """
        if df.empty or "%_hits" not in df.columns:
            return 0.0

        df_copy = df.copy()
        
        df_copy["es_benefico"] = df_copy["taxonomia"].apply(
            lambda x: BeneficialMicroorganismsService.es_benefico(x, tipo)
        )
        
        total_beneficos = df_copy[df_copy["es_benefico"]]["%_hits"].sum()
        return round(float(total_beneficos), 5)