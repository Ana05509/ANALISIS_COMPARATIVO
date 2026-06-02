# services/data/metadata_service.py
# Componente de Infraestructura para el Registro Estructurado y Trazabilidad Agrícola.

import csv
import io
from pathlib import Path
from typing import List, Dict, Any, Tuple, Union, Sequence
from django.db import transaction
from django.db.models import Count
from analisis.models import Cultivo, VariedadClon, MuestraSuelo, ArchivoMolecular


class MetadataService:
    """Servicio encargado de la gestión, validación e ingesta masiva de metadatos de muestras de suelo."""

    @staticmethod
    def obtener_o_crear_cultivo(nombre: str, descripcion: str = "") -> Cultivo:
        """Devuelve un Cultivo existente o lo crea, normalizando el nombre a Title Case."""
        if not nombre:
            raise ValueError("El nombre del cultivo no puede estar vacío.")
        
        nombre_normalizado = nombre.strip().title()
        cultivo, _ = Cultivo.objects.get_or_create(
            nombre=nombre_normalizado,
            defaults={"descripcion": descripcion}
        )
        return cultivo

    @staticmethod
    def obtener_o_crear_variedad(cultivo: Cultivo, nombre: str, descripcion: str = "") -> VariedadClon:
        """Devuelve una Variedad/Clon asociada a un cultivo, normalizando el nombre a Upper Case."""
        if not nombre:
            raise ValueError("El nombre de la variedad/clon no puede estar vacío.")
            
        nombre_normalizado = nombre.strip().upper()
        variedad, _ = VariedadClon.objects.get_or_create(
            cultivo=cultivo,
            nombre=nombre_normalizado,
            defaults={"descripcion": descripcion}
        )
        return variedad

    @staticmethod
    def registrar_muestra(
        codigo_muestra: str, 
        variedad: VariedadClon, 
        finca: str = "", 
        lote: str = ""
    ) -> Tuple[MuestraSuelo, bool]:
        """Registra o actualiza una muestra de suelo específica asegurando la unicidad de su código."""
        if not codigo_muestra:
            raise ValueError("El código de la muestra es mandatorio para la trazabilidad.")

        codigo_clean = codigo_muestra.strip().upper()
        muestra, creado = MuestraSuelo.objects.get_or_create(
            codigo=codigo_clean,
            defaults={
                "variedad": variedad,
                "finca": finca.strip(),
                "lote": lote.strip()
            }
        )
        return muestra, creado

    @staticmethod
    def importar_metadatos_csv(contenido_csv: Union[str, bytes, io.StringIO]) -> Dict[str, int]:
        """
        RESOLUCIÓN DE RENDIMIENTO (Anti N+1) E INTEGRIDAD: Ingesta masiva de muestras agrícolas.
        Usa cachés locales para evitar consultas repetitivas y envuelve todo en una transacción atómica.
        
        Espera columnas: codigo, cultivo, variedad, finca, lote
        """
        resumen = {"cultivos_creados": 0, "variedades_creadas": 0, "muestras_registradas": 0}
        
        # Normalizar el flujo de entrada a un lector de strings de Python
        if isinstance(contenido_csv, bytes):
            stream = io.StringIO(contenido_csv.decode("utf-8"))
        elif isinstance(contenido_csv, str):
            stream = io.StringIO(contenido_csv)
        else:
            stream = contenido_csv

        lector = csv.DictReader(stream)
        if not lector.fieldnames:
            return resumen

        # Sanitizar nombres de columnas del CSV a minúsculas
        lector.fieldnames = [col.strip().lower() for col in lector.fieldnames]

        # Cachés en memoria para demoler el problema N+1
        cache_cultivos: Dict[str, Cultivo] = {}
        cache_variedades: Dict[Tuple[int, str], VariedadClon] = {}

        # Forzar operación atómica: O se carga todo el lote de muestras perfecto, o no se guarda nada
        with transaction.atomic():
            for fila in lector:
                col_codigo = fila.get("codigo", "").strip()
                col_cultivo = fila.get("cultivo", "").strip()
                col_variedad = fila.get("variedad", "").strip()
                col_finca = fila.get("finca", "").strip()
                col_lote = fila.get("lote", "").strip()

                if not col_codigo or not col_cultivo or not col_variedad:
                    continue  # Ignorar filas incompletas de forma defensiva

                # 1. Resolver Cultivo usando la caché en memoria
                cultivo_key = col_cultivo.title()
                if cultivo_key not in cache_cultivos:
                    cultivo = MetadataService.obtener_o_crear_cultivo(cultivo_key)
                    cache_cultivos[cultivo_key] = cultivo
                    resumen["cultivos_creados"] += 1
                else:
                    cultivo = cache_cultivos[cultivo_key]

                # 2. Resolver Variedad usando la caché estructurada (ID_Cultivo, Nombre_Variedad)
                variedad_key = (cultivo.id, col_variedad.upper())
                if variedad_key not in cache_variedades:
                    variedad = MetadataService.obtener_o_crear_variedad(cultivo, col_variedad)
                    cache_variedades[variedad_key] = variedad
                    resumen["variedades_creadas"] += 1
                else:
                    variedad = cache_variedades[variedad_key]

                # 3. Registrar Muestra de suelo
                _, creado = MetadataService.registrar_muestra(
                    codigo_muestra=col_codigo,
                    variedad=variedad,
                    finca=col_finca,
                    lote=col_lote
                )
                if creado:
                    resumen["muestras_registradas"] += 1

        return resumen

    @staticmethod
    def listar_archivos_de_muestra(muestra_id: int) -> Sequence[Dict[str, Any]]:
        """
        RESOLUCIÓN DE TIPADO: Retorna el historial de archivos moleculares de una muestra.
        Usa Sequence[Dict[str, Any]] ya que Django garantiza que las llaves de values() son strings,
        satisfaciendo la invarianza de tipos de Pylance sin falsos positivos.
        """
        qs = ArchivoMolecular.objects.filter(muestra_id=muestra_id).values(
            "id", "tipo_analisis", "archivo", "fecha_carga"
        ).order_by("-fecha_carga")
        
        return list(qs)

    @staticmethod
    def resumen_metadatos_dashboard() -> Dict[str, Any]:
        """Genera los indicadores cuantitativos consolidados para el Dashboard principal de la UI."""
        por_tipo = (
            ArchivoMolecular.objects.values("tipo_analisis")
            .annotate(total=Count("id"))
        )
        
        # Mapear QuerySet a un diccionario nativo ágil
        tipo_dict = {str(item["tipo_analisis"]): int(item["total"]) for item in por_tipo}

        return {
            "total_muestras": int(MuestraSuelo.objects.count()),
            "total_cultivos": int(Cultivo.objects.count()),
            "total_variedades": int(VariedadClon.objects.count()),
            "total_archivos": int(ArchivoMolecular.objects.count()),
            "por_tipo_analisis": {
                "16S": tipo_dict.get("16S", 0),
                "ITS": tipo_dict.get("ITS", 0)
            },
        }
    