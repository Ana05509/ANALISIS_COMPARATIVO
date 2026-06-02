# services/interpretation/pathogen_service.py
# Servicio de Detección Fitosanitaria, Análisis de Riesgo y Alertas de Fitopatógenos.

import pandas as pd
from typing import List, Dict, Any
from analisis.models import ResultadoTaxonomico, CatalogoMicroorganismo

# Listas referenciales especializadas en amenazas agrícolas (Bacterias y Hongos)
FITOPATOGENOS_16S = {
    "xanthomonas", "ralstonia", "erwinia", "pectobacterium", "dickeya",
    "clavibacter", "acidovorax", "agrobacterium",
}

FITOPATOGENOS_ITS = {
    "moniliophthora", "phytophthora", "ceratocystis", "crinipellis", "marasmius",
    "fusarium", "rhizoctonia", "sclerotinia", "botrytis", "alternaria",
    "colletotrichum", "verticillium", "pythium", "puccinia", "ustilago",
    "hemileia", "mycena", "armillaria",
}


class PathogenService:
    """Servicio bioinformático encargado de aislar, catalogar y auditar riesgos de fitopatógenos en el suelo."""

    @staticmethod
    def es_fitopatogeno(nombre: Any, tipo: str = "16S") -> bool:
        """
        Evalúa si un taxón es un fitopatógeno de alto riesgo agrícola.
        Soporta búsquedas tanto por el género principal como por el nombre científico completo.
        """
        if not nombre or not isinstance(nombre, str):
            return False

        nombre_lower = nombre.strip().lower()
        tokens = nombre_lower.split()
        if not tokens:
            return False

        genero = tokens[0]
        pool = FITOPATOGENOS_ITS if tipo.upper() == "ITS" else FITOPATOGENOS_16S
        
        return genero in pool or nombre_lower in pool

    @staticmethod
    def obtener_fitopatogenos_en_muestra(muestra_id: int, tipo: str = "16S") -> List[Dict[str, Any]]:
        """
        Extrae las amenazas fitosanitarias identificadas en una muestra desde la base de datos.
        Alinea el diccionario resultante convirtiendo las métricas al estándar de Pandas (%_hits).
        """
        tipo_analisis = tipo.upper() if tipo else "16S"

        # Extraer datos crudos como diccionarios
        raw_data = ResultadoTaxonomico.objects.filter(
            archivo__muestra_id=muestra_id,
            archivo__tipo_analisis=tipo_analisis,
        ).values("genus", "porcentaje_hits", "num_hits")

        # RESOLUCIÓN PYLANCE: Forzar casteo a lista nativa para disolver el ValuesQuerySet de Django
        qs: List[Dict[str, Any]] = list(raw_data)

        fitopatogenos = []
        for item in qs:
            nombre_genus = item.get("genus")
            if nombre_genus and PathogenService.es_fitopatogeno(nombre_genus, tipo_analisis):
                # Sincronizar el nombre de la columna con el pipeline de Pandas
                item["%_hits"] = item.pop("porcentaje_hits")
                fitopatogenos.append(item)

        return fitopatogenos

    @staticmethod
    def marcar_fitopatogenos_en_catalogo(nombres: List[str], nivel: str = "genus", tipo: str = "16S") -> int:
        """
        Actualiza masivamente el catálogo de microorganismos ejecutando un único UPDATE en lote.
        Elimina de raíz el antipadrón N+1 y acelera los tiempos de persistencia.
        """
        if not nombres:
            return 0

        tipo_analisis = tipo.upper() if tipo else "16S"
        nivel_evaluado = nivel if nivel else "genus"

        # Filtrar la lista en memoria usando hashing ultrarrápido
        nombres_filtrados = [
            nombre for nombre in nombres 
            if PathogenService.es_fitopatogeno(nombre, tipo_analisis)
        ]

        if not nombres_filtrados:
            return 0

        # SOLUCIÓN DE RENDIMIENTO: Un único disparo SQL masivo usando el operador __in
        actualizados = CatalogoMicroorganismo.objects.filter(
            nombre__in=nombres_filtrados,
            nivel=nivel_evaluado
        ).update(clasificacion="fitopatogeno")

        return actualizados

    @staticmethod
    def calcular_carga_patogena_total(df: pd.DataFrame, tipo: str = "16S") -> float:
        """
        Métrica de Alerta Fitosanitaria: Suma la abundancia relativa total de patógenos en el suelo.
        Indispensable para calcular umbrales de riesgo epidemiológico en el dashboard.
        """
        if df.empty or "%_hits" not in df.columns:
            return 0.0

        df_copy = df.copy()
        
        # Evaluar la presencia de amenazas mediante máscaras optimizadas
        df_copy["es_patogeno"] = df_copy["taxonomia"].apply(
            lambda x: PathogenService.es_fitopatogeno(x, tipo)
        )
        
        total_patogenos = df_copy[df_copy["es_patogeno"]]["%_hits"].sum()
        return round(float(total_patogenos), 5)