import io
import unicodedata
import pandas as pd
from analisis.models import CatalogoMicroorganismo

class CatalogService:
    
    @staticmethod
    def _quitar_tildes(texto: str) -> str:
        nfkd = unicodedata.normalize('NFD', texto)
        return ''.join(c for c in nfkd if unicodedata.category(c) != 'Mn')

    @classmethod
    def _normalizar_nivel(cls, valor: str) -> str:
        """
        Acepta variantes en español e inglés (con/sin tilde, mayúsculas, abreviaturas)
        y retorna el valor canónico: genus | species | family | order | class | phylum.
        Si no reconoce el valor devuelve 'genus' como fallback seguro.
        """
        clave = cls._quitar_tildes(str(valor).strip().lower())
        MAPA = {
            # genus
            'genus': 'genus', 'genero': 'genus', 'gen': 'genus', 'g': 'genus',
            # species
            'species': 'species', 'especie': 'species', 'specie': 'species',
            'sp': 'species', 'spp': 'species',
            # family
            'family': 'family', 'familia': 'family', 'fam': 'family',
            # order
            'order': 'order', 'orden': 'order', 'ord': 'order',
            # class
            'class': 'class', 'clase': 'class', 'cls': 'class',
            # phylum
            'phylum': 'phylum', 'filo': 'phylum', 'division': 'phylum',
        }
        return MAPA.get(clave, 'genus')

    @classmethod
    def _normalizar_clasificacion(cls, valor: str) -> str:
        """
        Acepta cualquier variante legible del Excel y la mapea al código interno.
        Maneja acentos, mayúsculas, sinónimos en español e inglés.
        """
        v = cls._quitar_tildes(str(valor).strip().lower())
        MAPA = {
            # benéfico
            'benefico':            'benefico',
            'beneficioso':         'benefico',
            'beneficial':          'benefico',
            'promotor':            'benefico',
            'aliado':              'benefico',
            # fitopatógeno
            'fitopatogeno':        'fitopatogeno',
            'potencial fitopatogeno': 'fitopatogeno',
            'patogeno':            'fitopatogeno',
            'patogeno potencial':  'fitopatogeno',
            'pathogen':            'fitopatogeno',
            'riesgo':              'fitopatogeno',
            # neutral
            'neutral':             'neutral',
            'neutro':              'neutral',
            # sin clasificar
            'sin_clasificar':      'sin_clasificar',
            'sin clasificar':      'sin_clasificar',
            'desconocido':         'sin_clasificar',
            'unknown':             'sin_clasificar',
            'nd':                  'sin_clasificar',
            'n/d':                 'sin_clasificar',
            '':                    'sin_clasificar',
            'nan':                 'sin_clasificar',
            'none':                'sin_clasificar',
        }
        return MAPA.get(v, 'sin_clasificar')

    @staticmethod
    def importar_desde_archivo(archivo) -> tuple:
        """
        Lee un CSV/Excel y crea o actualiza registros en CatalogoMicroorganismo.
        Columnas requeridas: nombre, nivel, marcador (16S/ITS), clasificacion.
        Columnas opcionales: descripcion, referencia.
        Retorna (creados, actualizados, errores).
        """
        nombre_archivo = archivo.name.lower()
        if nombre_archivo.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(archivo)
        else:
            archivo.seek(0)
            raw = archivo.read()
            try:
                df = pd.read_csv(io.BytesIO(raw))
            except Exception:
                df = pd.read_csv(io.BytesIO(raw), sep='\t')

        df.columns = [str(c).strip().lower() for c in df.columns]

        required = {'nombre', 'nivel', 'marcador', 'clasificacion'}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(
                f"Columnas requeridas faltantes: {', '.join(sorted(missing))}. "
                "El archivo debe tener: nombre, nivel, marcador, clasificacion "
                "(opcionales: descripcion, referencia)"
            )

        MARCADORES = {'16S', 'ITS'}
        _nan = {'nan', 'none', ''}

        creados = actualizados = errores = 0

        for _, row in df.iterrows():
            nombre = CatalogService._quitar_escape_formula(str(row.get('nombre', '')).strip())
            nivel  = CatalogService._normalizar_nivel(row.get('nivel', 'genus'))

            if not nombre or nombre.lower() in _nan:
                errores += 1
                continue

            marcador = str(row.get('marcador', '16S')).strip().upper()
            if marcador not in MARCADORES:
                marcador = '16S'

            # Normalización robusta: acepta tildes y sinónimos del Excel
            clasificacion = CatalogService._normalizar_clasificacion(
                row.get('clasificacion', 'sin_clasificar')
            )

            _nan_set = _nan
            def _clean(val):
                s = CatalogService._quitar_escape_formula(str(val).strip())
                return '' if s.lower() in _nan_set else s

            descripcion = _clean(row.get('descripcion', '')) if 'descripcion' in df.columns else ''
            referencia  = _clean(row.get('referencia',  '')) if 'referencia'  in df.columns else ''

            try:
                # Django 5.x: update_or_create no acepta __iexact en kwargs no-defaults.
                # Usamos filter().first() para la búsqueda case-insensitive y luego
                # create/save explícito para la escritura.
                obj = CatalogoMicroorganismo.objects.filter(
                    nombre__iexact=nombre,
                    nivel__iexact=nivel,
                ).first()

                if obj:
                    obj.marcador      = marcador
                    obj.clasificacion = clasificacion
                    obj.descripcion   = descripcion or obj.descripcion
                    obj.referencia    = referencia  or obj.referencia
                    obj.save()
                    actualizados += 1
                else:
                    CatalogoMicroorganismo.objects.create(
                        nombre=nombre,
                        nivel=nivel,
                        marcador=marcador,
                        clasificacion=clasificacion,
                        descripcion=descripcion,
                        referencia=referencia,
                    )
                    creados += 1
            except Exception:
                errores += 1

        return creados, actualizados, errores

    # EXPORTACIÓN

    # Mismas columnas (y mismo orden) que exige importar_desde_archivo, para
    # que un archivo exportado se pueda volver a importar tal cual.
    COLUMNAS_EXPORTACION = ['nombre', 'nivel', 'marcador', 'clasificacion', 'descripcion', 'referencia']

    @staticmethod
    def _quitar_escape_formula(texto: str) -> str:
        """
        Revierte el apóstrofe que la exportación antepone a textos que Excel
        interpretaría como fórmula ('=…, '+…, '-…, '@…), para que exportar y
        volver a importar no altere los datos.
        """
        from analisis.services.business.export_service import _EXCEL_FORMULA_TRIGGERS
        if texto.startswith("'") and texto[1:2] and texto[1:].startswith(_EXCEL_FORMULA_TRIGGERS):
            return texto[1:]
        return texto

    @staticmethod
    def _dataframe_exportacion(filas) -> pd.DataFrame:
        """filas: iterable de dicts con las COLUMNAS_EXPORTACION (p. ej. queryset.values(...))."""
        from analisis.services.business.export_service import _excel_safe_df
        df = pd.DataFrame(list(filas), columns=CatalogService.COLUMNAS_EXPORTACION).fillna('')
        return _excel_safe_df(df)

    @staticmethod
    def exportar_csv(filas) -> bytes:
        """CSV UTF-8 con BOM (para que Excel muestre bien las tildes), reimportable."""
        df = CatalogService._dataframe_exportacion(filas)
        return df.to_csv(index=False).encode('utf-8-sig')

    @staticmethod
    def exportar_excel(filas) -> bytes:
        """
        Libro con una hoja «Catálogo» (todas las filas; es la que lee la
        importación, que toma la primera hoja) y una hoja por marcador.
        """
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        df = CatalogService._dataframe_exportacion(filas)
        verde = PatternFill('solid', fgColor='0F6E56')
        insignias = {
            'benefico':       ('D4EDDA', '14532D'),
            'fitopatogeno':   ('FADBD8', '7F1D1D'),
            'neutral':        ('D6E4F0', '1E3A5F'),
            'sin_clasificar': ('E5E7EB', '374151'),
        }
        anchos = {'nombre': 38, 'nivel': 10, 'marcador': 10, 'clasificacion': 16,
                  'descripcion': 60, 'referencia': 50}
        col_clasif = CatalogService.COLUMNAS_EXPORTACION.index('clasificacion') + 1

        wb = Workbook()
        wb.remove(wb.worksheets[0])
        hojas = [('Catálogo', df)] + [
            (titulo, df[df['marcador'] == marcador])
            for marcador, titulo in (('16S', 'Bacterias (16S)'), ('ITS', 'Hongos (ITS)'))
        ]
        for titulo, datos in hojas:
            if titulo != 'Catálogo' and datos.empty:
                continue
            ws = wb.create_sheet(titulo)
            ws.append(CatalogService.COLUMNAS_EXPORTACION)
            for fila in datos.itertuples(index=False):
                ws.append(list(fila))

            for j, col in enumerate(CatalogService.COLUMNAS_EXPORTACION, start=1):
                celda = ws.cell(row=1, column=j)
                celda.fill = verde
                celda.font = Font(bold=True, color='FFFFFF')
                celda.alignment = Alignment(horizontal='center', vertical='center')
                ws.column_dimensions[get_column_letter(j)].width = anchos[col]
            for (celda,) in ws.iter_rows(min_row=2, min_col=col_clasif, max_col=col_clasif):
                bg, fg = insignias.get(celda.value, insignias['sin_clasificar'])
                celda.fill = PatternFill('solid', fgColor=bg)
                celda.font = Font(bold=True, color=fg)
            ws.freeze_panes = 'A2'
            ws.auto_filter.ref = ws.dimensions

        salida = io.BytesIO()
        wb.save(salida)
        return salida.getvalue()

