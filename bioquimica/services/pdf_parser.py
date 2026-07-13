"""
Parser de reportes PDF del Laboratorio de Microbiología Agrícola (DISErLAB-PUCE).

Soporta dos tipos de reporte:
  - MAg-XXX (Recuento): tablas UFC/g por tipo de microorganismo
  - MAg-XXX (Aislamiento e Identificación): pruebas bioquímicas + taxonomía
"""
import re
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


# ─── Utilidades ──────────────────────────────────────────────────────────────

def _celda(c) -> str:
    return (c or '').strip().replace('\n', ' ')


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


# ─── API pública ─────────────────────────────────────────────────────────────

def parsear_pdf(archivo) -> dict:
    """
    Parsea un PDF de reporte de laboratorio.
    Retorna:
      {
        'tipo':   'recuento' | 'aislamiento',
        'header': {codigo, nombre_muestra, etiqueta, fechas, temp, humedad},
        'datos':  [lista de recuentos u organismos aislados]
      }
    """
    with pdfplumber.open(archivo) as pdf:
        tipo   = _detectar_tipo(pdf)
        header = _extraer_header(pdf)
        datos  = _parsear_recuento(pdf) if tipo == 'recuento' else _parsear_aislamiento(pdf)

    return {'tipo': tipo, 'header': header, 'datos': datos}
