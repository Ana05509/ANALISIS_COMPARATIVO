"""
Parser de reportes PDF de laboratorios de microbiología agrícola.

Soporta dos formatos:
  - MAg-XXX: tablas UFC/g por tipo de microorganismo (Recuento), o
    pruebas bioquímicas + taxonomía (Aislamiento e Identificación).
  - CIPAL (Nº de muestra tipo "088-107"): tabla "Reporte de Poblaciones" de
    un "Diagnóstico Microbiológico" (Bacterias/Hongos/Actinomicetes +
    grupos funcionales) o "Diagnóstico Micorrízico" (Colonización/Densidad
    de endófito, o Esporas viables). Cada fila (m1, m2, t1…) se guarda como
    un Recuento tipo "Otro/Mixto" con sus columnas como Parámetros
    Adicionales — mismo mecanismo que usa el ingreso manual para este caso.
"""
import re
import unicodedata
from decimal import Decimal

import pdfplumber


# ─── Patrones de extracción ───────────────────────────────────────────────────

_UFC_CIENTIFICO = re.compile(r'(\d+(?:[.,]\d+)?)\s*[xX×]\s*10\s*(\d+)', re.IGNORECASE)
_UFC_SIMPLE     = re.compile(r'(\d+(?:[.,]\d+)?)\s*UFC', re.IGNORECASE)
_UFC_MENOR      = re.compile(r'<\s*1', re.IGNORECASE)

_CODIGO    = re.compile(r'(MAg-\d+-\d{4})', re.IGNORECASE)
_FECHA     = re.compile(r'(\d{4}-\d{2}-\d{2})')
_TEMP      = re.compile(r'Temperatura[:\s]+(\d+[.,]\d+)')
_HUMEDAD   = re.compile(r'Humedad[:\s]+(\d+[.,]\d+)')
_MUESTRA   = re.compile(r'(Suelo\s*#?\s*\d+)', re.IGNORECASE)

_ORG_HEADING = re.compile(
    r'(?:Bacteria\s+(?:aislada|Identificada)|Hongo\s+aislado)[:\s]+(.+)',
    re.IGNORECASE
)

_TAXON_MAP = {
    'dominio': 'dominio', 'filo': 'filo', 'clase': 'clase',
    'orden': 'orden_taxonomico', 'familia': 'familia',
    'género': 'genero', 'genero': 'genero', 'especie': 'especie',
}

# Marcadores de portada que identifican el formato CIPAL (distinto del MAg-XXX
# de arriba): código de muestra tipo "088-107" en vez de "MAg-225-2023".
_CIPAL_MICRO_MARCA     = re.compile(r'DIAGN[OÓ]STICO\s+MICROBIOL[OÓ]GICO', re.IGNORECASE)
_CIPAL_MICORRIZA_MARCA = re.compile(r'DIAGN[OÓ]STICO\s+MICORR[IÍ]ZICO', re.IGNORECASE)
_CIPAL_CODIGO          = re.compile(r'\b(\d{2,4}-\d{2,4})\b')


# ─── Utilidades ──────────────────────────────────────────────────────────────

def _celda(c) -> str:
    return (c or '').strip().replace('\n', ' ')


def _norm(s: str) -> str:
    """Mayúsculas y sin acentos — para comparar encabezados de tabla sin
    preocuparse de "Fósforo" vs "FOSFORO" vs "Fosforo"."""
    s = unicodedata.normalize('NFKD', s or '')
    return ''.join(c for c in s if not unicodedata.combining(c)).upper()


def _parsear_ufc(texto: str):
    """Retorna (coeficiente, exponente, menor_que_limite)."""
    t = (texto or '').strip()
    if not t:
        return None, None, False
    if _UFC_MENOR.search(t):
        return None, None, True
    m = _UFC_CIENTIFICO.search(t)
    if m:
        coef = float(m.group(1).replace(',', '.'))
        exp  = int(m.group(2))
        return Decimal(str(coef)), exp, False
    m = _UFC_SIMPLE.search(t)
    if m:
        coef = float(m.group(1).replace(',', '.'))
        return Decimal(str(coef)), 0, False
    return None, None, False


# ─── Cabecera ────────────────────────────────────────────────────────────────

def _extraer_header(pdf) -> dict:
    texto = '\n'.join(p.extract_text() or '' for p in pdf.pages[:2])
    h = {}

    m = _CODIGO.search(texto)
    if m:
        h['codigo'] = m.group(1)

    fechas = _FECHA.findall(texto)
    if fechas:
        h['fecha_recepcion'] = fechas[0]
        h['fecha_ejecucion'] = fechas[1] if len(fechas) > 1 else fechas[0]
        h['fecha_reporte']   = fechas[2] if len(fechas) > 2 else fechas[-1]

    m = _TEMP.search(texto)
    if m:
        h['temp_ambiental'] = float(m.group(1).replace(',', '.'))

    m = _HUMEDAD.search(texto)
    if m:
        h['humedad_ambiental'] = float(m.group(1).replace(',', '.'))

    m = _MUESTRA.search(texto)
    h['nombre_muestra'] = m.group(1).strip() if m else 'Muestra'

    # Etiqueta: líneas después de "Etiqueta:"
    etiqueta_lineas = []
    capturando = False
    for linea in texto.split('\n'):
        if re.search(r'Etiqueta\s*:', linea, re.IGNORECASE):
            capturando = True
            val = re.sub(r'Etiqueta\s*:\s*', '', linea, flags=re.IGNORECASE).strip().strip('"')
            if val:
                etiqueta_lineas.append(val)
        elif capturando:
            limpia = linea.strip().strip('"')
            if limpia and not any(k in limpia.upper() for k in ('TRANSCRITO', 'VISTO', 'LA INFO')):
                etiqueta_lineas.append(limpia)
            else:
                break
    if etiqueta_lineas:
        h['etiqueta'] = '\n'.join(etiqueta_lineas)

    return h


# ─── Tipo de reporte ─────────────────────────────────────────────────────────

def _detectar_tipo(pdf) -> str:
    texto = pdf.pages[0].extract_text() or ''
    if re.search(r'RECUENTO\s+DE\s+MICRO', texto, re.IGNORECASE):
        return 'recuento'
    if re.search(r'AISLAMIENTO', texto, re.IGNORECASE):
        return 'aislamiento'
    return 'recuento'


# ─── Parser de Recuento (MAg-225) ────────────────────────────────────────────

def _parsear_recuento(pdf) -> list:
    resultados = []
    orden = 0

    for pagina in pdf.pages:
        for tabla in (pagina.extract_tables() or []):
            if not tabla or len(tabla) < 2:
                continue

            cabecera = ' '.join(_celda(c).upper() for c in tabla[0])

            if 'HONGO' in cabecera:
                tipo = 'hongo'
            elif 'BACTERIA' in cabecera:
                tipo = 'bacteria'
            else:
                continue

            for fila in tabla[1:]:
                if not fila or all(not c for c in fila):
                    continue

                celdas = [_celda(c) for c in fila]

                # Columnas: [identificación_muestra, nombre_organismo, ufc/g]
                if len(celdas) >= 3:
                    nombre  = celdas[1]
                    ufc_str = celdas[2]
                elif len(celdas) == 2:
                    nombre  = celdas[0]
                    ufc_str = celdas[1]
                else:
                    continue

                if not nombre or 'IDENTIFICACI' in nombre.upper() or nombre.upper() in ('HONGOS', 'BACTERIA', 'BACTERIAS', 'HONGO'):
                    continue

                coef, exp, menor = _parsear_ufc(ufc_str)

                # Fila de encabezado/sección sin UFC real (p. ej. "TOTAL HONGOS"
                # u otra variante no cubierta por la lista de nombres exactos de
                # arriba): una fila de datos genuina siempre trae un valor
                # numérico o "<1"; si no se pudo parsear ninguno, no es un
                # microorganismo real y se descarta en vez de guardarse como
                # una barra fantasma sin valor.
                if coef is None and not menor:
                    continue

                resultados.append({
                    'tipo_organismo':   tipo,
                    'nombre':           nombre,
                    'coeficiente':      coef,
                    'exponente':        exp,
                    'menor_que_limite': menor,
                    'orden':            orden,
                })
                orden += 1

    return resultados


# ─── Parser de Aislamiento (MAg-226) ─────────────────────────────────────────

def _parsear_aislamiento(pdf) -> list:
    organismos = []
    org_actual = None

    for pagina in pdf.pages:
        texto  = pagina.extract_text() or ''
        tablas = pagina.extract_tables() or []

        # Detectar encabezados de organismo en el texto
        for linea in texto.split('\n'):
            m = _ORG_HEADING.search(linea)
            if m:
                nombre = m.group(1).strip()
                tipo   = 'bacteria' if re.search(r'bacteria', linea, re.IGNORECASE) else 'hongo'
                org_actual = {
                    'tipo':             tipo,
                    'nombre_cientifico': nombre,
                    'taxonomia':        {},
                    'pruebas':          [],
                }
                organismos.append(org_actual)

        for tabla in tablas:
            if not tabla or len(tabla) < 2:
                continue

            contenido = ' '.join(
                _celda(c).upper() for fila in tabla for c in fila if c
            )

            # Tabla de taxonomía
            if 'TAXONOM' in contenido and org_actual:
                for fila in tabla:
                    if len(fila) >= 2:
                        clave = _celda(fila[0]).lower().rstrip(':').strip()
                        valor = _celda(fila[1]).strip()
                        # Tablas de 3 columnas tienen columna vacía en el medio
                        if not valor and len(fila) >= 3:
                            valor = _celda(fila[2]).strip()
                        campo = _TAXON_MAP.get(clave)
                        if campo and valor and 'TAXONOM' not in valor.upper():
                            org_actual['taxonomia'][campo] = valor
                continue

            # Tabla de pruebas bioquímicas
            if ('PRUEBA' in contenido or 'BIOQUÍM' in contenido) and org_actual:
                for fila in tabla[1:]:
                    if not fila or len(fila) < 3:
                        continue
                    num_str = _celda(fila[0])
                    prueba  = _celda(fila[1])
                    result  = _celda(fila[2])
                    try:
                        num = int(num_str)
                    except (ValueError, TypeError):
                        continue
                    if prueba and 'PRUEBA' not in prueba.upper() and 'N°' not in prueba:
                        org_actual['pruebas'].append({
                            'numero':       num,
                            'nombre_prueba': prueba,
                            'resultado':    result,
                        })

    return organismos


# ─── Parser CIPAL (Diagnóstico Microbiológico / Micorrízico) ────────────────
#
# Reportes "Nº de muestra: 088-107" del laboratorio de microbiología de CIPAL
# (ANCUPA): no traen un organismo puntual por fila como el MAg-XXX de arriba,
# sino una fila por muestra (m1, m2…, t1, t2…) con varias columnas de
# resultado a la vez. Cada fila se guarda como un Recuento tipo "Otro/Mixto"
# y sus columnas van como Parámetros Adicionales — el mismo mecanismo que ya
# usa el ingreso manual para este caso (ver RecuentoUFC/ParametroRecuento en
# models.py). Se reconocen tres variantes de la tabla "Reporte de
# Poblaciones", según qué columnas trae:
#   - Microbiológico de suelo: Bacterias/Hongos/Actinomicetes + grupos
#     funcionales (Solubilizadores de P, Celulolíticos, Fijadores de N).
#   - Micorrízico (colonización): Colonización (%) y Densidad de endófito.
#   - Micorrízico (esporas): Esporas viables, Morfoespecies, Observaciones.

_CIPAL_KEYWORDS_MICRO = {
    'BACTERIA':      'Bacterias',
    'HONGO':         'Hongos',
    'ACTINOMICETE':  'Actinomicetes',
    'SOLUBILIZADOR': 'Solubilizadores de Fósforo',
    'CELULOL':       'Celulolíticos',
    'FIJADOR':       'Fijadores de N de vida libre',
}
_CIPAL_KEYWORDS_COLONIZACION = {
    'COLONIZACION': 'Colonización (%)',
    'DENSIDAD':     'Densidad de endófito (/47.5%)',
}
_CIPAL_KEYWORDS_ESPORAS = {
    'ESPORA':        'Esporas viables /100 gss',
    'MORFOESPECIE':  'Morfoespecies sugeridas',
    'OBSERVACION':   'Observaciones',
}

_MESES_ES = {
    'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4, 'MAYO': 5, 'JUNIO': 6,
    'JULIO': 7, 'AGOSTO': 8, 'SEPTIEMBRE': 9, 'SETIEMBRE': 9, 'OCTUBRE': 10,
    'NOVIEMBRE': 11, 'DICIEMBRE': 12,
}
# "30-Agosto-2012", "9-Septiembre-2012", "28-Octubre-2011" (a veces sin
# separador entre el mes y el año, ej. "28-Octubre2011", por eso los `\s*-?\s*`
# quedan opcionales en vez de exigir un separador fijo).
_FECHA_ES_CIPAL  = re.compile(
    r'(\d{1,2})\s*-?\s*(?:de\s+)?([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s*-?\s*(?:de\s+)?(\d{4})'
)
_FECHA_NUM_CIPAL = re.compile(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})')

_CIPAL_ETIQUETA_PREFIJO = re.compile(r'^[^:]{0,45}:\s*')
_CIPAL_CIENTIFICO       = re.compile(r'(\d+(?:[.,]\d+)?)\s*[eE]\s*([+-]?\d+)')
_CIPAL_DECIMAL          = re.compile(r'^-?\d+(?:[.,]\d+)?$')


def _quitar_etiqueta(texto: str) -> str:
    """De una celda tipo "Fecha: 30-Agosto-2012" (etiqueta y valor pegados,
    como vienen en la tabla de cabecera de los reportes "Microbiológico")
    devuelve solo "30-Agosto-2012". Si la celda no tiene etiqueta (caso de
    los reportes "Micorrízico", donde la tabla de cabecera trae la fila de
    etiquetas y la fila de valores por separado) la deja intacta."""
    return _CIPAL_ETIQUETA_PREFIJO.sub('', texto, count=1).strip()


def _extraer_fecha_cipal(texto):
    """Retorna 'YYYY-MM-DD' o None. Nunca lanza — un formato de fecha que no
    se reconoce queda como None, igual que una fecha ausente: `_fecha()` en
    views.py deja el campo sin fecha y lo anota en Observaciones, en vez de
    inventar una."""
    t = (texto or '').strip()
    if not t:
        return None
    m = _FECHA_ES_CIPAL.search(t)
    if m:
        dia, mes_txt, anio = m.groups()
        mes = _MESES_ES.get(_norm(mes_txt))
        if mes:
            return f"{int(anio):04d}-{mes:02d}-{int(dia):02d}"
    m = _FECHA_NUM_CIPAL.search(t)
    if m:
        dia, mes, anio = (int(x) for x in m.groups())
        if anio < 100:
            anio += 2000 if anio < 70 else 1900
        return f"{anio:04d}-{mes:02d}-{dia:02d}"
    return None


def _valor_columna_cipal(tabla, idx_fila, idx_col):
    """Valor de la celda [idx_fila][idx_col] de la tabla de cabecera CIPAL.
    Cubre las dos variantes vistas: "Etiqueta:\\nValor" en una sola fila
    (reportes Microbiológico), o etiquetas y valores en filas separadas
    (reportes Micorrízico) — en ese segundo caso, si la celda de la fila de
    la etiqueta no trae valor pegado, se toma la misma columna de la fila
    siguiente."""
    if idx_col is None or idx_fila >= len(tabla):
        return ''
    fila = tabla[idx_fila]
    valor = _quitar_etiqueta(_celda(fila[idx_col])) if idx_col < len(fila) else ''
    if valor:
        return valor
    if idx_fila + 1 < len(tabla):
        fila_sig = tabla[idx_fila + 1]
        if idx_col < len(fila_sig):
            return _quitar_etiqueta(_celda(fila_sig[idx_col]))
    return ''


def _extraer_header_cipal(pdf, texto_p0=None) -> dict:
    h = {}
    pagina0 = pdf.pages[0]

    for tabla in (pagina0.extract_tables() or []):
        idx_fila = None
        idx_col_codigo = None
        idx_col_fecha = None
        for ri, fila in enumerate(tabla):
            for ci, celda in enumerate(fila):
                txt = _norm(_celda(celda))
                if 'MUESTRA' in txt:
                    idx_col_codigo = ci
                if 'FECHA' in txt:
                    idx_col_fecha = ci
            if idx_col_codigo is not None:
                idx_fila = ri
                break
        if idx_fila is None:
            continue

        m = _CIPAL_CODIGO.search(_valor_columna_cipal(tabla, idx_fila, idx_col_codigo))
        if m:
            h['codigo_base'] = m.group(1)

        fecha_iso = _extraer_fecha_cipal(_valor_columna_cipal(tabla, idx_fila, idx_col_fecha))
        if fecha_iso:
            h['fecha_recepcion'] = h['fecha_ejecucion'] = h['fecha_reporte'] = fecha_iso
        break

    if texto_p0 is None:
        texto_p0 = pagina0.extract_text() or ''
    if 'codigo_base' not in h:
        # Último recurso si no hubo tabla reconocible: el código es lo
        # primero con forma "NNN-NNN" en la portada.
        m = _CIPAL_CODIGO.search(texto_p0)
        if m:
            h['codigo_base'] = m.group(1)

    m = re.search(r'Nombre:\s*(.+)', texto_p0)
    if m:
        h['cliente'] = m.group(1).strip()

    return h


def _mapear_columnas(celdas_norm, keywords):
    """Empareja cada columna de un encabezado de tabla con su nombre bonito
    según `keywords` (ej. {'BACTERIA': 'Bacterias'}). Retorna
    (columnas_id, mapeo) — columnas_id son los índices previos a la primera
    columna reconocida (código/identificación de la muestra) — o None si
    ninguna palabra clave apareció en esta fila."""
    mapeo = {}
    for idx, celda in enumerate(celdas_norm):
        for kw, bonito in keywords.items():
            if kw in celda:
                mapeo[idx] = bonito
                break
    # Se exigen al menos 2 columnas reconocidas: una sola coincidencia no
    # alcanza para llamarla encabezado de la tabla de resultados — la celda
    # "Tipo de Análisis: Colonización en raíces" de la tabla de cabecera
    # (portada) también contiene la palabra "Colonización" y produciría un
    # falso positivo de una sola columna si se aceptara.
    if len(mapeo) < 2:
        return None
    return list(range(min(mapeo))), mapeo


def _formatear_valor_cipal(texto):
    """Normaliza el valor de una celda de datos a texto legible. Retorna
    None si la celda no contiene un número reconocible (ej. está vacía, o es
    la fila de unidades "UFC / gss")."""
    t = (texto or '').strip()
    if not t:
        return None
    m = _CIPAL_CIENTIFICO.search(t)
    if m:
        coef = m.group(1).replace(',', '.')
        exp = int(m.group(2))
        return f"{coef} × 10^{exp} UFC/gss"
    if _CIPAL_DECIMAL.match(t.replace(',', '.')):
        return t
    return None


def _parsear_tabla_cipal(pdf, keywords) -> list:
    """Busca la tabla "Reporte de Poblaciones" cuyo encabezado matchea
    `keywords` y arma una fila RecuentoUFC (tipo_organismo='otro') por cada
    fila de datos, con sus columnas como ParametroRecuento. El mapeo de
    columnas, una vez encontrado, se reutiliza para las tablas siguientes —
    los reportes de 40 muestras parten la tabla en dos páginas y la
    continuación (m39/m40, t39/t40…) no repite el encabezado."""
    resultados = []
    orden = 0
    columnas_id = None
    mapeo = None

    for pagina in pdf.pages:
        for tabla in (pagina.extract_tables() or []):
            if not tabla:
                continue

            filas = tabla
            if mapeo is None:
                idx_header = None
                for ri, fila in enumerate(tabla):
                    celdas_norm = [_norm(_celda(c)) for c in fila]
                    res = _mapear_columnas(celdas_norm, keywords)
                    if res:
                        columnas_id, mapeo = res
                        idx_header = ri
                        break
                if mapeo is None:
                    continue
                filas = tabla[idx_header + 1:]

            for fila in filas:
                if not fila or all(not c for c in fila):
                    continue
                celdas = [_celda(c) for c in fila]

                parametros = []
                num = 1
                tiene_valor = False
                for idx, nombre_param in mapeo.items():
                    if idx >= len(celdas) or not celdas[idx]:
                        continue
                    valor_fmt = _formatear_valor_cipal(celdas[idx])
                    if valor_fmt is not None:
                        tiene_valor = True
                    else:
                        valor_fmt = celdas[idx]  # texto libre: morfoespecies, observaciones…
                    parametros.append({'numero': num, 'nombre': nombre_param, 'valor': valor_fmt})
                    num += 1

                # Fila sin ningún valor numérico real (encabezado repetido,
                # fila de unidades "UFC / gss", fila en blanco de relleno):
                # se descarta en vez de guardarse como una muestra fantasma.
                if not tiene_valor:
                    continue

                id_partes = [celdas[i] for i in columnas_id if i < len(celdas) and celdas[i]]
                nombre = ' - '.join(id_partes) if id_partes else f'Muestra {orden + 1}'

                resultados.append({
                    'tipo_organismo':   'otro',
                    'nombre':           nombre,
                    'coeficiente':      None,
                    'exponente':        None,
                    'menor_que_limite': False,
                    'orden':            orden,
                    'parametros':       parametros,
                })
                orden += 1

    return resultados


def _parsear_cipal(pdf, texto_p0=None) -> dict:
    header_raw = _extraer_header_cipal(pdf, texto_p0)
    codigo_base = header_raw.get('codigo_base')
    if not codigo_base:
        raise ValueError(
            "No se encontró el código de muestra (ej. 088-107) en el reporte CIPAL."
        )

    datos = None
    sufijo = nombre_reporte = None
    for keywords, suf, nombre in (
        (_CIPAL_KEYWORDS_MICRO,         'MICRO',     'Diagnóstico Microbiológico de Suelo'),
        (_CIPAL_KEYWORDS_COLONIZACION,  'MICORRIZA', 'Diagnóstico Micorrízico — Colonización'),
        (_CIPAL_KEYWORDS_ESPORAS,       'ESPORAS',   'Diagnóstico Micorrízico — Esporas'),
    ):
        encontrados = _parsear_tabla_cipal(pdf, keywords)
        if encontrados:
            datos, sufijo, nombre_reporte = encontrados, suf, nombre
            break

    if not datos:
        raise ValueError(
            "No se reconoció la tabla «Reporte de Poblaciones» del formato CIPAL "
            "(se esperaban columnas de Bacterias/Hongos, Colonización/Densidad, o Esporas)."
        )

    # El mismo rango de muestra (ej. "088-107") se reutiliza entre el
    # reporte microbiológico y el micorrízico de un mismo envío — el sufijo
    # por tipo evita que choquen contra el código único de EnsayoMicrobiologico.
    #
    # Si el PDF no trae fecha en el campo "Fecha:" (pasa en varios reportes
    # CIPAL — no es un fallo del parser, el campo está vacío en el propio
    # documento), `fecha_recepcion` queda en None acá: _guardar_ensayo en
    # views.py es quien decide qué hacer con eso (dejar el campo sin fecha
    # y anotarlo en Observaciones, en vez de inventar una fecha).
    header = {
        'codigo':          f"{codigo_base}-{sufijo}",
        'nombre_muestra':  nombre_reporte,
        'etiqueta':        f"Cliente: {header_raw['cliente']}" if header_raw.get('cliente') else '',
        'fecha_recepcion': header_raw.get('fecha_recepcion'),
        'fecha_ejecucion': header_raw.get('fecha_ejecucion'),
        'fecha_reporte':   header_raw.get('fecha_reporte'),
    }
    return {'tipo': 'recuento', 'header': header, 'datos': datos, 'formato': 'cipal'}


# ─── API pública ─────────────────────────────────────────────────────────────

def parsear_pdf(archivo) -> dict:
    """
    Parsea un PDF de reporte de laboratorio.
    Retorna:
      {
        'tipo':   'recuento' | 'aislamiento',
        'header': {codigo, nombre_muestra, etiqueta, fechas, temp, humedad},
        'datos':  [lista de recuentos u organismos aislados],
        'formato': 'cipal' | 'mag',
      }
    'formato' es la marca que _guardar_ensayo (views.py) usa para poner
    EnsayoMicrobiologico.es_cipal — no confundir con 'tipo': un reporte
    CIPAL siempre es 'tipo'='recuento' por dentro (ver _parsear_cipal), pero
    no es un recuento UFC/g "de verdad" tipo MAg-XXX.
    """
    with pdfplumber.open(archivo) as pdf:
        texto_p1 = pdf.pages[0].extract_text() or ''
        if _CIPAL_MICRO_MARCA.search(texto_p1) or _CIPAL_MICORRIZA_MARCA.search(texto_p1):
            # Se reutiliza el texto de la página 0 ya extraído arriba —
            # _extraer_header_cipal necesita ese mismo texto para el nombre
            # del cliente y, como respaldo, el código de muestra.
            return _parsear_cipal(pdf, texto_p0=texto_p1)

        tipo   = _detectar_tipo(pdf)
        header = _extraer_header(pdf)
        datos  = _parsear_recuento(pdf) if tipo == 'recuento' else _parsear_aislamiento(pdf)

    return {'tipo': tipo, 'header': header, 'datos': datos, 'formato': 'mag'}
