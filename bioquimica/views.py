import json
import re
from decimal import Decimal, InvalidOperation
from typing import cast

import plotly.graph_objects as go
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render, get_object_or_404

from .forms import EnsayoManualForm
from .models import (
    EnsayoMicrobiologico, RecuentoUFC, ParametroRecuento,
    MicroorganismoAislado, PruebaBioquimica,
)
from analisis.audit import registrar_accion
from django.contrib.admin.models import ADDITION


def _grafico_recuento(ensayo):
    # Filas sin valor UFC estándar (tipo_organismo='otro', o cualquier fila
    # cargada solo con ParametroRecuento libres) no tienen nada que graficar
    # en escala logarítmica — antes caían igual con valor_numerico=0 (piso
    # artificial de 0.1 más abajo) y aparecían como una barra fantasma con
    # etiqueta "—". Se descartan acá, no en el JS: sus datos reales se ven
    # en la tabla de detalle, no en este gráfico.
    recuentos = [r for r in ensayo.recuentos.all() if r.menor_que_limite or r.coeficiente is not None]
    if not recuentos:
        return None

    nombres = [r.nombre for r in recuentos]
    valores = [max(r.valor_numerico, 0.1) for r in recuentos]
    etiquetas = [r.valor_display for r in recuentos]
    colores = ['#1D9E75' if r.tipo_organismo == 'bacteria' else '#F5A623' for r in recuentos]
    # tipo_organismo por punto — el cliente lo usa para recolorear en modo
    # Escala de grises sin perder la agrupación bacteria/hongo (ver
    # ChartTheme en detalle.html); no afecta el color/valor mostrado en modo Color.
    tipos = [r.tipo_organismo for r in recuentos]

    fig = go.Figure(go.Bar(
        x=nombres,
        y=valores,
        text=etiquetas,
        textposition='outside',
        marker_color=colores,
        customdata=tipos,
        hovertemplate='<b>%{x}</b><br>%{text}<extra></extra>',
    ))

    fig.update_layout(
        yaxis_type='log',
        yaxis_title='UFC/g (escala logarítmica)',
        xaxis_title='Microorganismo',
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(family='Inter, sans-serif', size=12),
        margin=dict(t=20, b=120, l=60, r=20),
        xaxis=dict(tickangle=-35),
        showlegend=False,
        height=420,
    )

    # fig.to_json() no está anotado en los stubs de plotly y Pylance infiere
    # un retorno "str | Any | None" — en runtime, para una Figure ya armada
    # con datos (como acá) siempre devuelve el JSON como str; el cast no
    # cambia nada en tiempo de ejecución, solo se lo aclara al chequeador.
    return json.loads(cast(str, fig.to_json()))


# ─── Gráficas para filas "Otro/Mixto" con Parámetros Adicionales ──────────
#
# Los recuentos importados del formato CIPAL (ver
# bioquimica/services/pdf_parser.py::_parsear_tabla_cipal) no tienen un
# valor UFC en el propio RecuentoUFC — viven como ParametroRecuento por
# columna (Bacterias, Hongos…, o Colonización/Densidad, o Esporas). Por eso
# _grafico_recuento() de arriba no los grafica: estas funciones arman esas
# gráficas aparte, a partir de los parámetros en vez del campo
# coeficiente/exponente. También sirven para ensayos cargados a mano con los
# mismos nombres de parámetro (ver placeholder en ingreso_manual.html).

_MICRO_SERIES = [
    'Bacterias', 'Hongos', 'Actinomicetes',
    'Solubilizadores de Fósforo', 'Celulolíticos', 'Fijadores de N de vida libre',
]
_SERIE_COLONIZACION = 'Colonización (%)'
_SERIE_DENSIDAD     = 'Densidad de endófito (/47.5%)'
_SERIE_ESPORAS      = 'Esporas viables /100 gss'

_PARAM_CIENTIFICO = re.compile(r'^([\d.]+)\s*×\s*10\^(-?\d+)')


def _valor_numerico_parametro(texto):
    """Extrae el número de un ParametroRecuento.valor para graficar — cubre
    "9.7 × 10^5 UFC/gss" (formato CIPAL de recuento) y números simples con
    coma decimal ("48,48", "171"). None si no es un valor numérico (ej.
    "Glomus, Acaulospora")."""
    if not texto:
        return None
    t = texto.strip()
    m = _PARAM_CIENTIFICO.match(t)
    if m:
        try:
            return float(m.group(1)) * (10 ** int(m.group(2)))
        except ValueError:
            return None
    try:
        return float(t.replace(',', '.'))
    except ValueError:
        return None


def _parametros_por_nombre(filas):
    """[(recuento, {parametro.nombre: parametro.valor}), …] para filas
    'Otro/Mixto' — asume que `filas` ya trae los parámetros precargados
    (prefetch_related('parametros')).

    Se devuelve una lista, no un dict indexado por `recuento.nombre`:
    RecuentoUFC.nombre no tiene restricción de unicidad, y el ingreso
    manual permite crear dos tarjetas 'Otro/Mixto' con el mismo nombre de
    muestra por error de tipeo — indexar por nombre colapsaría esas dos
    filas en una sola entrada, perdiendo los datos de la primera sin avisar."""
    return [(r, {p.nombre: p.valor for p in r.parametros.all()}) for r in filas]


def _grafico_cipal_series(filas, series_nombres, titulo_y, log=False):
    """Gráfico de barras (agrupadas si `series_nombres` trae más de una) a
    partir de los Parámetros Adicionales de filas 'Otro/Mixto'. None si
    ninguna fila trae ninguna de las series pedidas."""
    datos = _parametros_por_nombre(filas)
    muestras_datos = [
        (r.nombre, params) for r, params in datos
        if any(s in params for s in series_nombres)
    ]
    if not muestras_datos:
        return None

    # Si el mismo nombre de muestra aparece más de una vez (ver docstring de
    # _parametros_por_nombre), se numeran las etiquetas del eje X para que
    # ambas barras se vean por separado en vez de superponerse en una sola.
    conteo = {}
    for nombre, _ in muestras_datos:
        conteo[nombre] = conteo.get(nombre, 0) + 1
    vistos = {}
    muestras = []
    datos_por_muestra = {}
    for nombre, params in muestras_datos:
        if conteo[nombre] > 1:
            vistos[nombre] = vistos.get(nombre, 0) + 1
            etiqueta = f'{nombre} ({vistos[nombre]})'
        else:
            etiqueta = nombre
        muestras.append(etiqueta)
        datos_por_muestra[etiqueta] = params

    # Piso de 0.1 en escala logarítmica: ni un valor ausente ni uno realmente
    # cero (pasa de verdad en datos reales — ej. "Solubilizadores de
    # Fósforo: 0.0 × 10^0 UFC/gss" cuando esa muestra no dio ningún colonia
    # de ese grupo funcional) se pueden ubicar en un eje log (Plotly lo
    # descarta o lo dibuja mal) — mismo problema que resuelve el piso en
    # _grafico_recuento() de arriba con max(valor, 0.1). El texto del hover
    # (`y_txt`) sigue mostrando el valor real ("0.0 × 10^0 UFC/gss"), solo la
    # altura de la barra se pisa. En escala lineal (Colonización/Densidad/
    # Esporas) un 0 sí se grafica sin distorsión, así que el piso solo
    # aplica con log=True.
    traces = []
    for serie in series_nombres:
        y_num, y_txt, tiene_dato = [], [], False
        for m in muestras:
            texto = datos_por_muestra.get(m, {}).get(serie)
            valor = _valor_numerico_parametro(texto)
            if valor is not None:
                tiene_dato = True
            if valor is None:
                y_num.append(0.1 if log else 0)
            elif log and valor <= 0:
                y_num.append(0.1)
            else:
                y_num.append(valor)
            y_txt.append(texto or '—')
        if not tiene_dato:
            continue
        traces.append(go.Bar(
            name=serie, x=muestras, y=y_num, text=y_txt,
            hovertemplate='<b>%{x}</b><br>' + serie + ': %{text}<extra></extra>',
        ))
    if not traces:
        return None

    fig = go.Figure(data=traces)
    fig.update_layout(
        barmode='group',
        yaxis_type='log' if log else 'linear',
        yaxis_title=titulo_y,
        xaxis_title='Muestra',
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(family='Inter, sans-serif', size=12),
        margin=dict(t=20, b=120, l=60, r=20),
        xaxis=dict(tickangle=-35),
        showlegend=len(traces) > 1,
        legend=dict(orientation='h', y=1.15) if len(traces) > 1 else {},
        height=440,
    )
    return json.loads(cast(str, fig.to_json()))


def _grafico_heatmap_pruebas(ensayo):
    aislados = list(ensayo.aislados.prefetch_related('pruebas').filter(pruebas__isnull=False).distinct())
    if not aislados:
        return None

    # Collect all unique test names (union across all organisms)
    todas_pruebas = []
    vistas = set()
    for org in aislados:
        for p in org.pruebas.all():
            if p.nombre_prueba not in vistas:
                todas_pruebas.append(p.nombre_prueba)
                vistas.add(p.nombre_prueba)

    if not todas_pruebas:
        return None

    organismos = [o.nombre_cientifico for o in aislados]

    # Build matrix: 1=positive, -1=negative, 0=neutral/text
    matriz = []
    textos = []
    for org in aislados:
        pruebas_dict = {p.nombre_prueba: p.resultado for p in org.pruebas.all()}
        fila_val = []
        fila_txt = []
        for nombre in todas_pruebas:
            res = pruebas_dict.get(nombre, '—')
            fila_txt.append(res)
            r = res.strip().lower()
            if r in ('+', 'c', 'crecimiento'):
                fila_val.append(1)
            elif r in ('-', 'nc', 'no hay crecimiento'):
                fila_val.append(-1)
            else:
                fila_val.append(0)
        matriz.append(fila_val)
        textos.append(fila_txt)

    fig = go.Figure(go.Heatmap(
        z=matriz,
        x=todas_pruebas,
        y=organismos,
        text=textos,
        texttemplate='%{text}',
        colorscale=[
            [0.0, '#FDBA74'],   # naranja-300 → negativo
            [0.5, '#E5E7EB'],   # gris-200    → neutro
            [1.0, '#86EFAC'],   # verde-300   → positivo
        ],
        showscale=False,
        hovertemplate='<b>%{y}</b><br>%{x}: <b>%{text}</b><extra></extra>',
        zmin=-1, zmax=1,
    ))

    fig.update_layout(
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(family='Inter, sans-serif', size=11),
        margin=dict(t=20, b=140, l=160, r=20),
        xaxis=dict(tickangle=-40, side='bottom'),
        height=max(300, len(organismos) * 60 + 180),
    )

    # fig.to_json() no está anotado en los stubs de plotly y Pylance infiere
    # un retorno "str | Any | None" — en runtime, para una Figure ya armada
    # con datos (como acá) siempre devuelve el JSON como str; el cast no
    # cambia nada en tiempo de ejecución, solo se lo aclara al chequeador.
    return json.loads(cast(str, fig.to_json()))


@login_required
def lista_ensayos(request):
    tipo_filtro = request.GET.get('tipo', '')
    # 'cipal' es un filtro sintético (no existe como valor de `tipo` en la
    # base — EnsayoMicrobiologico.tipo solo distingue recuento/aislamiento,
    # ver comentario en detalle_ensayo) que usa el campo real es_cipal para
    # separar los reportes CIPAL de los recuentos UFC/g "de verdad": antes
    # quedaban mezclados bajo un solo conteo de "Recuento".
    qs = EnsayoMicrobiologico.objects.all()
    if tipo_filtro == 'cipal':
        qs = qs.filter(es_cipal=True)
    elif tipo_filtro == 'recuento':
        qs = qs.filter(tipo='recuento', es_cipal=False)
    elif tipo_filtro == 'aislamiento':
        qs = qs.filter(tipo='aislamiento')

    base = EnsayoMicrobiologico.objects
    context = {
        'ensayos': qs,
        'tipo_filtro': tipo_filtro,
        'total_recuento': base.filter(tipo='recuento', es_cipal=False).count(),
        'total_cipal': base.filter(es_cipal=True).count(),
        'total_aislamiento': base.filter(tipo='aislamiento').count(),
    }
    return render(request, 'bioquimica/lista.html', context)


def _clasificacion_catalogo(aislados):
    """
    Retorna un dict {aislado.pk: clasificacion} consultando CatalogoMicroorganismo
    con el marcador correcto según el tipo de organismo (bacteria→16S, hongo→ITS).
    """
    from analisis.models import CatalogoMicroorganismo

    TIPO_A_MARCADOR = {'bacteria': '16S', 'hongo': 'ITS'}

    # Agrupar PKs por marcador para hacer solo 2 queries al catálogo como máximo
    pks_por_marcador = {'16S': [], 'ITS': []}
    genero_por_pk = {}
    for a in aislados:
        marcador = TIPO_A_MARCADOR.get(a.tipo, '16S')
        pks_por_marcador[marcador].append(a.pk)
        genero_por_pk[a.pk] = (a.genero or '').strip().lower()

    resultado = {}
    for marcador, pks in pks_por_marcador.items():
        if not pks:
            continue
        lookup = {
            obj.nombre.lower(): obj.clasificacion
            for obj in CatalogoMicroorganismo.objects.filter(nivel='genus', marcador=marcador)
        }
        for pk in pks:
            genero = genero_por_pk.get(pk, '')
            resultado[pk] = lookup.get(genero, 'sin_clasificar') if genero else 'sin_clasificar'

    return resultado


@login_required
def detalle_ensayo(request, pk):
    ensayo = get_object_or_404(EnsayoMicrobiologico, pk=pk)

    grafico_recuento_json = None
    grafico_heatmap_json = None
    grafico_micro_json = None
    grafico_colonizacion_json = None
    grafico_densidad_json = None
    grafico_esporas_json = None
    lista_otros = []

    if ensayo.tipo == 'recuento':
        datos = _grafico_recuento(ensayo)
        grafico_recuento_json = json.dumps(datos) if datos else None

        lista_otros = list(ensayo.recuentos.filter(tipo_organismo='otro').prefetch_related('parametros'))
        if lista_otros:
            d = _grafico_cipal_series(lista_otros, _MICRO_SERIES, 'UFC/gss (escala logarítmica)', log=True)
            grafico_micro_json = json.dumps(d) if d else None
            d = _grafico_cipal_series(lista_otros, [_SERIE_COLONIZACION], 'Colonización (%)')
            grafico_colonizacion_json = json.dumps(d) if d else None
            d = _grafico_cipal_series(lista_otros, [_SERIE_DENSIDAD], 'Densidad de endófito (/47.5%)')
            grafico_densidad_json = json.dumps(d) if d else None
            d = _grafico_cipal_series(lista_otros, [_SERIE_ESPORAS], 'Esporas viables /100 gss')
            grafico_esporas_json = json.dumps(d) if d else None
    else:
        datos = _grafico_heatmap_pruebas(ensayo)
        grafico_heatmap_json = json.dumps(datos) if datos else None

    aislados_con_pruebas = None
    aislados_sin_pruebas = None
    clasificacion_por_pk = {}
    if ensayo.tipo == 'aislamiento':
        aislados_con_pruebas = list(
            ensayo.aislados.filter(pruebas__isnull=False).distinct().prefetch_related('pruebas')
        )
        aislados_sin_pruebas = list(ensayo.aislados.filter(pruebas__isnull=True))
        todos_aislados = aislados_con_pruebas + aislados_sin_pruebas
        clasificacion_por_pk = _clasificacion_catalogo(todos_aislados)
        for a in todos_aislados:
            a.clasificacion_catalogo = clasificacion_por_pk.get(a.pk, 'sin_clasificar')

    context = {
        'ensayo': ensayo,
        'grafico_recuento_json': grafico_recuento_json,
        'grafico_heatmap_json': grafico_heatmap_json,
        'grafico_micro_json': grafico_micro_json,
        'grafico_colonizacion_json': grafico_colonizacion_json,
        'grafico_densidad_json': grafico_densidad_json,
        'grafico_esporas_json': grafico_esporas_json,
        'recuentos_hongos': ensayo.recuentos.filter(tipo_organismo='hongo').prefetch_related('parametros') if ensayo.tipo == 'recuento' else None,
        'recuentos_bacterias': ensayo.recuentos.filter(tipo_organismo='bacteria').prefetch_related('parametros') if ensayo.tipo == 'recuento' else None,
        'recuentos_otros': lista_otros or None,
        'aislados_con_pruebas': aislados_con_pruebas,
        'aislados_sin_pruebas': aislados_sin_pruebas,
    }
    return render(request, 'bioquimica/detalle.html', context)


@login_required
def ver_pdf(request, pk):
    """Sirve el PDF original adjunto a un ensayo — SOLO Docente/staff.
    No usar `ensayo.archivo_pdf.url` (el /media/... crudo) en ningún
    template: esa URL la sirve Django sin ningún control de acceso (ver
    config/urls.py), cualquiera que la conozca puede bajarla sin sesión.
    Esta vista es el único camino con permiso real hacia el archivo — el
    original trae membrete, logo y datos de contacto del laboratorio y del
    cliente, así que no se expone a estudiantes ni a un futuro público
    anónimo si el sistema se abre (ver conversación sobre nombres de
    laboratorio)."""
    if _bloquear_si_estudiante(request):
        return redirect('bioquimica:detalle', pk=pk)

    ensayo = get_object_or_404(EnsayoMicrobiologico, pk=pk)
    if not ensayo.archivo_pdf:
        raise Http404("Este ensayo no tiene un PDF original adjunto.")

    try:
        archivo_abierto = ensayo.archivo_pdf.open('rb')
    except (FileNotFoundError, OSError, ValueError):
        # El registro en la base dice que hay un PDF, pero el archivo ya no
        # está en el disco del servidor — pasa cuando el almacenamiento de
        # media/ es local al contenedor (sin Volume persistente en Railway):
        # cada redeploy empieza con un disco vacío, así que cualquier PDF
        # subido antes del último redeploy queda "perdido" aunque el
        # ensayo y sus datos sigan intactos en la base. No es un error de
        # este ensayo en particular, así que se explica en vez de un 500.
        messages.error(
            request,
            f"El PDF original de «{ensayo.codigo}» ya no está disponible en el servidor "
            "(el archivo se perdió, probablemente en una actualización del sistema). "
            "Los datos ya extraídos del ensayo siguen intactos abajo; si necesita el "
            "PDF, vuelva a subirlo."
        )
        return redirect('bioquimica:detalle', pk=pk)

    return FileResponse(
        archivo_abierto,
        content_type='application/pdf',
        filename=f"{ensayo.codigo}.pdf",
    )


def _fecha(valor):
    """None si el PDF no traía fecha o no se pudo interpretar — antes caía
    a date.today(), lo que mostraba la fecha de IMPORTACIÓN como si fuera
    la del análisis. _guardar_ensayo es quien decide qué hacer con un None
    (dejar el campo sin fecha + anotarlo en Observaciones)."""
    if not valor:
        return None
    try:
        from datetime import datetime
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _guardar_ensayo(archivo, request):
    """
    Parsea y guarda un PDF. Retorna (ensayo, msg_ok) o lanza ValueError/Exception.
    Raises ValueError con mensaje amigable para duplicados y errores de validación.
    """
    from .services.pdf_parser import parsear_pdf

    if not archivo.name.lower().endswith('.pdf'):
        raise ValueError(f"«{archivo.name}» no es un PDF.")
    if archivo.size > 20 * 1024 * 1024:
        raise ValueError(f"«{archivo.name}» supera el máximo de 20 MB.")

    try:
        resultado = parsear_pdf(archivo)
    except Exception as e:
        raise ValueError(f"No se pudo leer «{archivo.name}»: {e}")

    header = resultado['header']
    codigo = header.get('codigo')
    if not codigo:
        raise ValueError(f"«{archivo.name}»: no se encontró código MAg-XXX-XXXX.")

    if EnsayoMicrobiologico.objects.filter(codigo=codigo).exists():
        existing = EnsayoMicrobiologico.objects.get(codigo=codigo)
        raise _DuplicadoError(codigo, existing.pk)

    fecha_recepcion = _fecha(header.get('fecha_recepcion'))
    fecha_ejecucion = _fecha(header.get('fecha_ejecucion'))
    fecha_reporte   = _fecha(header.get('fecha_reporte'))

    observaciones = ''
    if fecha_recepcion is None and fecha_ejecucion is None and fecha_reporte is None:
        observaciones = 'En el informe no se encuentra esta información (fecha del análisis).'

    with transaction.atomic():
        ensayo = EnsayoMicrobiologico(
            codigo=codigo,
            tipo=resultado['tipo'],
            es_cipal=resultado.get('formato') == 'cipal',
            nombre_muestra=header.get('nombre_muestra', 'Muestra'),
            etiqueta=header.get('etiqueta', ''),
            fecha_recepcion=fecha_recepcion,
            fecha_ejecucion=fecha_ejecucion,
            fecha_reporte=fecha_reporte,
            temp_ambiental=header.get('temp_ambiental'),
            humedad_ambiental=header.get('humedad_ambiental'),
            observaciones=observaciones,
            registrado_por=request.user,
        )
        archivo.seek(0)
        ensayo.archivo_pdf.save(archivo.name, archivo, save=False)
        ensayo.save()

        if resultado['tipo'] == 'recuento':
            # No se usa bulk_create: el formato CIPAL trae "Parámetros
            # Adicionales" por fila (ver pdf_parser._parsear_tabla_cipal) y
            # esas filas hijas necesitan el pk del RecuentoUFC ya guardado —
            # mismo patrón que ingreso_manual más abajo. El formato MAg-XXX
            # no trae 'parametros' (pop devuelve []) así que no cambia nada.
            for i, d in enumerate(resultado['datos']):
                d = dict(d)
                parametros = d.pop('parametros', [])
                d.setdefault('orden', i)
                r = RecuentoUFC(ensayo=ensayo, **d)
                r.save()
                if parametros:
                    ParametroRecuento.objects.bulk_create([
                        ParametroRecuento(recuento=r, **p) for p in parametros
                    ])
        else:
            for org_data in resultado['datos']:
                taxonomia = org_data.pop('taxonomia', {})
                pruebas   = org_data.pop('pruebas', [])
                org = MicroorganismoAislado(ensayo=ensayo, **org_data, **taxonomia)
                org.save()
                if pruebas:
                    PruebaBioquimica.objects.bulk_create([
                        PruebaBioquimica(microorganismo=org, **p) for p in pruebas
                    ])

    return ensayo


class _DuplicadoError(Exception):
    def __init__(self, codigo, pk):
        self.codigo = codigo
        self.pk = pk


def _bloquear_si_estudiante(request):
    """True (y ya dejó el mensaje de error) si el usuario no tiene permiso
    para registrar ensayos — Subir PDF e Ingreso manual son exclusivos de
    Docente/Investigador (y Admin); Estudiante puede ver los ensayos ya
    cargados pero no cargar nuevos."""
    if request.user.rol == 'estudiante':
        messages.error(
            request,
            "Su nivel de cuenta no dispone de permisos para registrar ensayos. "
            "Si es docente o investigador, contacte al administrador del sistema para actualizar su rol."
        )
        return True
    return False


@login_required
def subir_pdf(request):
    if _bloquear_si_estudiante(request):
        return redirect('bioquimica:lista')

    if request.method != 'POST':
        return render(request, 'bioquimica/subir_pdf.html')

    archivos = request.FILES.getlist('archivos')
    if not archivos:
        messages.error(request, "Debe seleccionar al menos un archivo PDF.")
        return render(request, 'bioquimica/subir_pdf.html')

    creados = []      # [(codigo, pk), ...]
    duplicados = []   # [codigo, ...]
    errores = []      # [mensaje, ...]

    for archivo in archivos:
        try:
            ensayo = _guardar_ensayo(archivo, request)
            registrar_accion(
                request, ensayo,
                f"Ensayo importado desde PDF ({archivo.name}).",
                accion=ADDITION,
            )
            creados.append((ensayo.codigo, ensayo.pk))
        except _DuplicadoError as e:
            duplicados.append(e.codigo)
        except Exception as e:
            # Exception a secas: cubre tanto el ValueError "amigable" de
            # _guardar_ensayo (PDF ilegible, sin código, etc.) como cualquier
            # otro fallo inesperado del parser — un solo PDF con problemas no
            # debe frenar la carga masiva del resto de archivos seleccionados.
            errores.append(str(e))

    if creados:
        lista = ', '.join(c for c, _ in creados)
        messages.success(request, f"{len(creados)} ensayo(s) importado(s): {lista}.")
    if duplicados:
        lista = ', '.join(duplicados)
        messages.warning(request, f"{len(duplicados)} ya existente(s) omitido(s): {lista}.")
    for msg in errores:
        messages.error(request, msg)

    if len(creados) == 1 and not duplicados and not errores:
        return redirect('bioquimica:detalle', pk=creados[0][1])

    if not creados and not duplicados and not errores:
        return render(request, 'bioquimica/subir_pdf.html')

    return redirect('bioquimica:lista')


# ─── Ingreso manual (alternativa a subir PDF) ──────────────────────────────
#
# Para reportes cuya estructura no coincide con la que espera pdf_parser.py
# (otro formato de laboratorio, PDF escaneado sin capa de texto, etc.): en
# vez de intentar leer el documento, la persona transcribe los valores a
# mano en un formulario con los mismos campos que ya usa el sistema. El PDF
# original se puede adjuntar igual como respaldo (campo archivo_pdf), pero
# ya no es la fuente de la que se extraen los datos.

def _decimal_o_none(valor):
    valor = (valor or '').strip().replace(',', '.')
    if not valor:
        return None
    try:
        return Decimal(valor)
    except InvalidOperation:
        return None


def _int_o_none(valor):
    valor = (valor or '').strip()
    if not valor:
        return None
    try:
        return int(valor)
    except ValueError:
        return None


def _parsear_recuento_manual(post):
    """
    Filas de recuento UFC/g ingresadas a mano. Cada fila tiene sus campos
    fijos sufijados por índice (rec_nombre_0, rec_coeficiente_0, …) y sus
    parámetros adicionales libres en arrays paralelos sufijados con el mismo
    índice (recparam_nombre_0[], recparam_valor_0[], …) — mismo patrón
    indexado que _parsear_aislamiento_manual usa para organismo/pruebas,
    generado por el JS del template al agregar/quitar tarjetas y parámetros.
    """
    filas = []
    i = 0
    while f'rec_nombre_{i}' in post:
        nombre = (post.get(f'rec_nombre_{i}') or '').strip()
        if not nombre:
            i += 1
            continue

        menor = post.get(f'rec_menor_{i}', 'no') == 'si'
        fila = {
            'tipo_organismo':   post.get(f'rec_tipo_{i}', 'bacteria'),
            'nombre':           nombre,
            'coeficiente':      None if menor else _decimal_o_none(post.get(f'rec_coeficiente_{i}', '')),
            'exponente':        None if menor else _int_o_none(post.get(f'rec_exponente_{i}', '')),
            'menor_que_limite': menor,
        }

        numeros = post.getlist(f'recparam_numero_{i}[]')
        nombres_p = post.getlist(f'recparam_nombre_{i}[]')
        valores_p = post.getlist(f'recparam_valor_{i}[]')
        parametros = []
        siguiente = 1
        for j, nombre_param in enumerate(nombres_p):
            nombre_param = (nombre_param or '').strip()
            if not nombre_param:
                continue
            valor = (valores_p[j] or '').strip() if j < len(valores_p) else ''
            numero = _int_o_none(numeros[j] if j < len(numeros) else '') or siguiente
            parametros.append({'numero': numero, 'nombre': nombre_param, 'valor': valor or '—'})
            siguiente += 1
        fila['parametros'] = parametros

        # Una fila con nombre pero sin ningún dato real (ni coeficiente/
        # exponente, ni "<1 UFC/g", ni un solo Parámetro Adicional) no tiene
        # nada que graficar ni que mostrar — mismo criterio que ya aplica
        # pdf_parser._parsear_tabla_cipal para no guardar una fila fantasma.
        # Acá no se descarta en el momento: se marca y el llamador decide
        # (avisarle al usuario cuáles se omitieron, en vez de borrarlas en
        # silencio como hace el importador de PDF).
        fila['sin_datos'] = not (menor or fila['coeficiente'] is not None or parametros)

        filas.append(fila)
        i += 1

    return filas


def _parsear_aislamiento_manual(post):
    """
    Organismos aislados ingresados a mano. Cada organismo tiene sus campos
    de taxonomía sufijados por índice (org_nombre_0, org_dominio_0, …) y sus
    pruebas bioquímicas en arrays paralelos sufijados con el mismo índice
    (prueba_nombre_0[], prueba_resultado_0[], …), generados por el JS del
    template al agregar/quitar organismos y pruebas dinámicamente.
    """
    organismos = []
    i = 0
    while f'org_nombre_{i}' in post:
        nombre = (post.get(f'org_nombre_{i}') or '').strip()
        if not nombre:
            i += 1
            continue

        org_data = {
            'tipo':              post.get(f'org_tipo_{i}', 'bacteria'),
            'nombre_cientifico': nombre,
            'dominio':           (post.get(f'org_dominio_{i}') or '').strip(),
            'filo':              (post.get(f'org_filo_{i}') or '').strip(),
            'clase':             (post.get(f'org_clase_{i}') or '').strip(),
            'orden_taxonomico':  (post.get(f'org_orden_{i}') or '').strip(),
            'familia':           (post.get(f'org_familia_{i}') or '').strip(),
            'genero':            (post.get(f'org_genero_{i}') or '').strip(),
            'especie':           (post.get(f'org_especie_{i}') or '').strip(),
        }

        numeros    = post.getlist(f'prueba_numero_{i}[]')
        nombres_p  = post.getlist(f'prueba_nombre_{i}[]')
        resultados = post.getlist(f'prueba_resultado_{i}[]')
        pruebas = []
        siguiente = 1
        for j, nombre_prueba in enumerate(nombres_p):
            nombre_prueba = (nombre_prueba or '').strip()
            if not nombre_prueba:
                continue
            resultado = (resultados[j] or '').strip() if j < len(resultados) else ''
            numero = _int_o_none(numeros[j] if j < len(numeros) else '') or siguiente
            pruebas.append({'numero': numero, 'nombre_prueba': nombre_prueba, 'resultado': resultado or '—'})
            siguiente += 1
        org_data['pruebas'] = pruebas

        organismos.append(org_data)
        i += 1

    return organismos


def _contexto_formulario_previo(request, form):
    """Contexto para volver a renderizar ingreso_manual.html después de un
    error (formulario inválido, código duplicado, fila sin datos…) SIN
    perder las tarjetas de Recuento/Organismo que el usuario ya había
    completado. El JS del template solo tenía una ruta: arrancar con una
    tarjeta vacía — cualquier error de validación borraba todo lo tipeado y
    obligaba a empezar de nuevo. Se reaprovechan los mismos parsers que
    arman los datos para guardar (_parsear_recuento_manual /
    _parsear_aislamiento_manual) para reconstruir esas tarjetas en el
    navegador."""
    filas = _parsear_recuento_manual(request.POST)
    for f in filas:
        f.pop('sin_datos', None)
        if f.get('coeficiente') is not None:
            f['coeficiente'] = str(f['coeficiente'])  # Decimal no es serializable a JSON

    return {
        'form': form,
        'filas_previas_json': json.dumps(filas),
        'organismos_previos_json': json.dumps(_parsear_aislamiento_manual(request.POST)),
    }


@login_required
def ingreso_manual(request):
    if _bloquear_si_estudiante(request):
        return redirect("bioquimica:lista")

    if request.method != 'POST':
        return render(request, 'bioquimica/ingreso_manual.html', {'form': EnsayoManualForm()})

    form = EnsayoManualForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, 'bioquimica/ingreso_manual.html', _contexto_formulario_previo(request, form))

    codigo = form.cleaned_data['codigo']
    if EnsayoMicrobiologico.objects.filter(codigo=codigo).exists():
        form.add_error('codigo', 'Ya existe un ensayo con este código.')
        return render(request, 'bioquimica/ingreso_manual.html', _contexto_formulario_previo(request, form))

    tipo = form.cleaned_data['tipo']
    omitidas = []

    try:
        with transaction.atomic():
            ensayo = EnsayoMicrobiologico(
                codigo=codigo,
                tipo=tipo,
                nombre_muestra=form.cleaned_data['nombre_muestra'],
                etiqueta=form.cleaned_data.get('etiqueta') or '',
                fecha_recepcion=form.cleaned_data['fecha_recepcion'],
                fecha_ejecucion=form.cleaned_data['fecha_ejecucion'],
                fecha_reporte=form.cleaned_data['fecha_reporte'],
                temp_ambiental=form.cleaned_data.get('temp_ambiental'),
                humedad_ambiental=form.cleaned_data.get('humedad_ambiental'),
                observaciones=form.cleaned_data.get('observaciones') or '',
                registrado_por=request.user,
            )
            archivo_pdf = form.cleaned_data.get('archivo_pdf')
            if archivo_pdf:
                ensayo.archivo_pdf = archivo_pdf
            ensayo.save()

            if tipo == 'recuento':
                filas = _parsear_recuento_manual(request.POST)
                if not filas:
                    raise ValueError("Agrega al menos un microorganismo con su recuento UFC/g.")
                filas_validas = [f for f in filas if not f.get('sin_datos')]
                omitidas = [f['nombre'] for f in filas if f.get('sin_datos')]
                if not filas_validas:
                    raise ValueError(
                        "Ninguna fila tiene datos para guardar: completá Coeficiente/× 10^, "
                        "marcá «<1 UFC/g», o agregá al menos un Parámetro Adicional."
                    )
                for i, f in enumerate(filas_validas):
                    f.pop('sin_datos', None)
                    parametros = f.pop('parametros')
                    r = RecuentoUFC(ensayo=ensayo, orden=i, **f)
                    r.save()
                    if parametros:
                        ParametroRecuento.objects.bulk_create([
                            ParametroRecuento(recuento=r, **p) for p in parametros
                        ])
            else:
                organismos = _parsear_aislamiento_manual(request.POST)
                if not organismos:
                    raise ValueError("Agrega al menos un microorganismo aislado.")
                for org_data in organismos:
                    pruebas = org_data.pop('pruebas')
                    org = MicroorganismoAislado(ensayo=ensayo, **org_data)
                    org.save()
                    if pruebas:
                        PruebaBioquimica.objects.bulk_create([
                            PruebaBioquimica(microorganismo=org, **p) for p in pruebas
                        ])
    except ValueError as e:
        messages.error(request, str(e))
        return render(request, 'bioquimica/ingreso_manual.html', _contexto_formulario_previo(request, form))

    registrar_accion(request, ensayo, "Ensayo registrado manualmente (sin PDF).", accion=ADDITION)
    if omitidas:
        messages.warning(request, f"Se omitieron {len(omitidas)} fila(s) sin datos: {', '.join(omitidas)}.")
    messages.success(request, f"Ensayo {ensayo.codigo} registrado manualmente.")
    return redirect('bioquimica:detalle', pk=ensayo.pk)
